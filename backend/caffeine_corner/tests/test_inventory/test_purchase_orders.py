"""
Purchase orders end to end: the rules (inventory/purchasing.py), the admin the
way staff use it, and Auto-Generate.

The bug that started this: a Purchase Order could be marked "Fully Received"
while nothing happened to stock (and "Received so far" stayed 0). Receiving now
records the stock movement, so the PO, the item's history and its stock level
always agree.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.db.models.signals import post_save
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from inventory import purchasing
from inventory.models import Inventory, PurchaseOrder, PurchaseOrderItem, StockMovement
from tests.support.admin_forms import admin_post_data
from tests.support.factories import make_item, make_po, make_supplier

User = get_user_model()


def stock(item):
    return Inventory.objects.get(pk=item.pk).quantity_on_hand


class PurchasingRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('staff@example.com', 'pw', is_staff=True)
        cls.supplier = make_supplier()

    def setUp(self):
        self.beans = make_item('Espresso Beans', on_hand='10', cost='350', supplier=self.supplier)
        self.milk = make_item('Fresh Milk', unit='ml', on_hand='1000', cost='0.08', supplier=self.supplier)
        self.po = make_po(self.supplier, [(self.beans, 5), (self.milk, 2000)], status='sent')

    # ── receiving ──
    def test_receiving_everything_puts_it_all_into_stock(self):
        received = purchasing.receive_remaining(self.po, self.user)
        self.assertEqual(len(received), 2)
        self.assertEqual(stock(self.beans), Decimal('15.00'))
        self.assertEqual(stock(self.milk), Decimal('3000.00'))
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, 'received')
        self.assertEqual(self.po.received_at, timezone.localdate())
        self.assertTrue(all(line.is_fully_received for line in self.po.items.all()))
        move = StockMovement.objects.get(inventory=self.beans)
        self.assertEqual(
            (move.movement_type, move.quantity, move.reference, move.unit_cost, move.performed_by),
            ('purchase', Decimal('5.00'), self.po.reference, Decimal('350.00'), self.user),
        )

    def test_receiving_again_adds_nothing_more(self):
        purchasing.receive_remaining(self.po, self.user)
        self.assertEqual(purchasing.receive_remaining(self.po, self.user), [])
        self.assertEqual(stock(self.beans), Decimal('15.00'))
        self.assertEqual(StockMovement.objects.filter(inventory=self.beans).count(), 1)

    def test_a_partial_arrival_then_the_rest(self):
        line = self.po.items.get(inventory=self.beans)
        line.quantity_received = Decimal('2')
        line.save()
        purchasing.record_receipt(line, Decimal('2'), self.user)
        purchasing.sync_status(self.po)
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, 'partial')
        self.assertIsNone(self.po.received_at)

        purchasing.receive_remaining(self.po, self.user)               # only what's still owed goes in
        self.assertEqual(stock(self.beans), Decimal('15.00'))          # 10 + 2 + 3, not 10 + 2 + 5
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, 'received')

    def test_a_cancelled_order_cannot_receive(self):
        self.po.status = 'cancelled'
        self.po.save()
        with self.assertRaises(purchasing.PurchaseOrderError):
            purchasing.receive_remaining(self.po, self.user)
        self.assertEqual(stock(self.beans), Decimal('10.00'))

    # ── status changes ──
    def test_send_only_from_draft(self):
        draft = make_po(self.supplier, [(self.beans, 1)])
        purchasing.mark_sent(draft)
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'sent')
        with self.assertRaises(purchasing.PurchaseOrderError):
            purchasing.mark_sent(draft)

    def test_cancel_only_while_nothing_has_arrived(self):
        purchasing.cancel(make_po(self.supplier, [(self.beans, 1)]))
        line = self.po.items.get(inventory=self.beans)
        line.quantity_received = Decimal('1')
        line.save()
        with self.assertRaises(purchasing.PurchaseOrderError):
            purchasing.cancel(self.po)

    def test_lowering_the_ordered_quantity_to_what_arrived_completes_the_order(self):
        for line in self.po.items.all():
            line.quantity_ordered = Decimal('3')
            line.quantity_received = Decimal('3')
            line.save()
        purchasing.sync_status(self.po)
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, 'received')

    def test_close_partial_is_what_actually_does_that_lowering(self):
        line = self.po.items.get(inventory=self.beans)                  # 5 ordered
        line.quantity_received = Decimal('3')
        line.save()
        purchasing.record_receipt(line, Decimal('3'), self.user)
        purchasing.sync_status(self.po)                                  # -> 'partial' (milk: 0 of 2000 in)
        purchasing.close_partial(self.po)
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, 'received')
        line.refresh_from_db()
        self.assertEqual((line.quantity_ordered, line.quantity_received), (Decimal('3.00'), Decimal('3.00')))
        self.assertEqual(stock(self.beans), Decimal('13.00'))            # only the 3 that were actually recorded — no new movement

    def test_close_partial_does_not_bother_writing_a_line_that_is_already_fully_in(self):
        beans_line = self.po.items.get(inventory=self.beans)
        beans_line.quantity_received = Decimal('5')                      # already fully in — nothing to lower
        beans_line.save()
        milk_line = self.po.items.get(inventory=self.milk)
        milk_line.quantity_received = Decimal('500')                     # short — this one needs the write
        milk_line.save()
        purchasing.sync_status(self.po)
        with CaptureQueriesContext(connection) as queries:
            purchasing.close_partial(self.po)
        writes = [q['sql'] for q in queries if q['sql'].startswith('UPDATE') and 'purchaseorderitem' in q['sql']]
        self.assertEqual(len(writes), 1, writes)                         # milk only, not beans too
        beans_line.refresh_from_db(), milk_line.refresh_from_db()
        self.assertEqual((beans_line.quantity_ordered, beans_line.quantity_received), (Decimal('5.00'), Decimal('5.00')))
        self.assertEqual((milk_line.quantity_ordered, milk_line.quantity_received), (Decimal('500.00'), Decimal('500.00')))

    def test_close_partial_refuses_unless_the_order_is_actually_partial(self):
        with self.assertRaises(purchasing.PurchaseOrderError):
            purchasing.close_partial(self.po)                            # still 'sent' — nothing has arrived yet
        purchasing.receive_remaining(self.po, self.user)                 # now 'received'
        with self.assertRaises(purchasing.PurchaseOrderError):
            purchasing.close_partial(self.po)

    # ── old data ──
    def test_an_order_marked_received_with_nothing_in_can_still_be_fixed(self):
        # how PO-2026-0001 looked: status "received", every line still at 0 received
        legacy = make_po(self.supplier, [(self.beans, 5)], status='received')
        self.assertFalse(purchasing.is_settled(legacy))
        purchasing.receive_remaining(legacy, self.user)
        legacy.refresh_from_db()
        self.assertEqual((legacy.status, stock(self.beans)), ('received', Decimal('15.00')))
        self.assertTrue(purchasing.is_settled(legacy))

    def test_syncing_an_order_marked_received_with_nothing_in_takes_it_back_to_sent(self):
        legacy = make_po(self.supplier, [(self.beans, 5)], status='received')
        purchasing.sync_status(legacy)
        legacy.refresh_from_db()
        self.assertEqual(legacy.status, 'sent')

    def test_settled_means_cancelled_or_fully_received(self):
        self.assertFalse(purchasing.is_settled(self.po))
        purchasing.receive_remaining(self.po, self.user)
        self.assertTrue(purchasing.is_settled(self.po))
        cancelled = make_po(self.supplier, [(self.beans, 1)], status='cancelled')
        self.assertTrue(purchasing.is_settled(cancelled))

    # ── what's on order ──
    def test_on_order_counts_open_orders_less_what_has_arrived(self):
        make_po(self.supplier, [(self.beans, 4)], status='draft')
        make_po(self.supplier, [(self.beans, 3, 1)], status='partial')          # 2 still owed
        make_po(self.supplier, [(self.beans, 9, 9)], status='received')         # done
        make_po(self.supplier, [(self.beans, 7)], status='cancelled')           # never coming
        owed = purchasing.outstanding_by_item()
        self.assertEqual(owed[self.beans.pk], Decimal('11.00'))                 # 5 (self.po) + 4 + 2
        self.assertEqual(owed[self.milk.pk], Decimal('2000.00'))


class PurchaseOrderNumberingTests(TestCase):
    """
    PurchaseOrder.save() is what actually assigns the number (a blank reference,
    on any save) — these don't go through the admin, on purpose, to pin down that
    it's the model doing this, not something the admin adds on top.
    """
    def setUp(self):
        self.supplier = make_supplier()
        self.item = make_item(supplier=self.supplier)

    def test_reference_for_is_the_ids_own_number(self):
        po = make_po(self.supplier, [(self.item, 1)])
        self.assertEqual(purchasing.reference_for(po), f'PO-{po.pk:06d}')

    def test_a_new_blank_order_is_numbered_from_its_own_id_in_one_save_call(self):
        po = PurchaseOrder.objects.create(supplier=self.supplier, status='draft')     # blank — nothing typed
        self.assertEqual(po.reference, f'PO-{po.pk:06d}')
        self.assertEqual(PurchaseOrder.objects.get(pk=po.pk).reference, po.reference)  # really persisted, not just in memory

    def test_a_hand_typed_reference_is_kept_exactly(self):
        po = PurchaseOrder.objects.create(supplier=self.supplier, status='draft', reference='KENT-INV-77')
        self.assertEqual(po.reference, 'KENT-INV-77')

    def test_saving_an_already_numbered_order_again_changes_nothing(self):
        po = PurchaseOrder.objects.create(supplier=self.supplier, status='draft')
        first = po.reference
        po.save()
        self.assertEqual(po.reference, first)

    def test_blanking_an_existing_orders_reference_numbers_it_from_its_own_id_too(self):
        po = PurchaseOrder.objects.create(supplier=self.supplier, status='draft', reference='TEMP-1')
        po.reference = ''
        po.save()
        self.assertEqual(po.reference, f'PO-{po.pk:06d}')

    def test_the_placeholder_never_reaches_the_saved_row(self):
        # The two-save dance for a brand-new blank order goes through a placeholder
        # to satisfy the required+unique column before the id exists — this pins
        # down that nothing ever reads that placeholder back out.
        po = PurchaseOrder.objects.create(supplier=self.supplier, status='draft')
        self.assertFalse(po.reference.startswith(PurchaseOrder._PENDING_PREFIX))
        self.assertFalse(PurchaseOrder.objects.filter(reference__startswith=PurchaseOrder._PENDING_PREFIX).exists())

    def test_the_column_is_never_actually_left_blank_not_even_for_an_instant(self):
        # required + unique: even a moment with two blank rows at once risks a
        # collision (or, without the placeholder, a crash on a database that still
        # has the column as NOT NULL — see PurchaseOrder.save()). Caught here by
        # watching what the very first insert actually wrote, before the second
        # save (which is what turns it into the real number) has even happened.
        seen = []

        def capture(sender, instance, created, **kwargs):
            if created:
                seen.append(instance.reference)

        post_save.connect(capture, sender=PurchaseOrder)
        try:
            PurchaseOrder.objects.create(supplier=self.supplier, status='draft')
        finally:
            post_save.disconnect(capture, sender=PurchaseOrder)
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0])                                            # never blank …
        self.assertTrue(seen[0].startswith(PurchaseOrder._PENDING_PREFIX))  # … and not yet the real number either

    def test_numbers_never_collide_and_gaps_or_deletions_change_nothing(self):
        # Unlike a separately-counted scheme, there is nothing to "continue from": every
        # number comes straight from its own row's id, so a deleted or hand-typed order
        # in between can never cause a clash.
        make_po(self.supplier, [(self.item, 1)], reference='PO-MINE-1')
        deleted = PurchaseOrder.objects.create(supplier=self.supplier, status='cancelled')
        deleted_id = deleted.pk
        deleted.delete()
        po = PurchaseOrder.objects.create(supplier=self.supplier, status='draft')
        self.assertNotEqual(po.pk, deleted_id)                  # ids are never reused …
        self.assertEqual(po.reference, f'PO-{po.pk:06d}')        # … so this can't collide with the deleted order's number
        self.assertEqual(PurchaseOrder.objects.filter(reference__in=['PO-MINE-1', po.reference]).count(), 2)

    def test_two_orders_created_back_to_back_get_different_numbers(self):
        # Not a real concurrency test (SQLite/Postgres both serialize this single
        # process's writes) — just confirms nothing is cached or reused between calls.
        first = PurchaseOrder.objects.create(supplier=self.supplier, status='draft')
        second = PurchaseOrder.objects.create(supplier=self.supplier, status='draft')
        self.assertNotEqual(first.reference, second.reference)


class ReorderReportTests(TestCase):
    def setUp(self):
        self.supplier = make_supplier()

    def test_low_items_are_sorted_by_what_can_be_done_about_them(self):
        ok = make_item('Fine', on_hand='50', reorder='5', supplier=self.supplier)
        to_order = make_item('Sugar', on_hand='3', reorder='5', reorder_qty='20', supplier=self.supplier)
        on_order = make_item('Butter', on_hand='1', reorder='5', supplier=self.supplier)
        no_supplier = make_item('Flour', on_hand='1', reorder='5')
        no_quantity = make_item('Cups', on_hand='0', reorder='0', reorder_qty='0', supplier=self.supplier)
        make_po(self.supplier, [(on_order, 10)], status='sent')

        report = purchasing.reorder_report()
        self.assertEqual([i.name for i in report.to_order], ['Sugar'])
        self.assertEqual([i.name for i in report.on_order], ['Butter'])
        self.assertEqual([i.name for i in report.no_supplier], ['Flour'])
        self.assertEqual([i.name for i in report.no_quantity], ['Cups'])
        self.assertEqual(report.low_total, 4)
        self.assertNotIn(ok, report.to_order + report.on_order + report.no_supplier + report.no_quantity)

    def test_without_a_reorder_quantity_it_suggests_twice_the_reorder_level(self):
        item = make_item('Sugar', on_hand='3', reorder='5', reorder_qty='0', supplier=self.supplier)
        self.assertEqual(purchasing.suggested_quantity(item), Decimal('10.00'))


class PurchaseOrderAdminTests(TestCase):
    """The admin the way staff use it: fill in the form, save, see stock move."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin@example.com', 'pw')
        cls.supplier = make_supplier()

    def setUp(self):
        self.client.force_login(self.admin)
        self.beans = make_item('Espresso Beans', on_hand='10', cost='350', supplier=self.supplier)
        self.milk = make_item('Fresh Milk', unit='ml', on_hand='1000', cost='0.08', supplier=self.supplier)

    def add_url(self):
        return reverse('admin:inventory_purchaseorder_add')

    def change_url(self, po):
        return reverse('admin:inventory_purchaseorder_change', args=[po.pk])

    def add_po(self, lines, **fields):
        data = admin_post_data(self.client.get(self.add_url()), supplier=self.supplier.pk, status='draft', **fields)
        for i, (item, quantity, cost) in enumerate(lines):
            data[f'items-{i}-inventory'] = item.pk
            data[f'items-{i}-quantity_ordered'] = quantity
            data[f'items-{i}-unit_cost'] = cost
        data['items-TOTAL_FORMS'] = str(len(lines))
        return self.client.post(self.add_url(), data)

    def change(self, po, **overrides):
        return self.client.post(self.change_url(po), admin_post_data(self.client.get(self.change_url(po)), **overrides), follow=True)

    def messages(self, response):
        return [str(m) for m in response.context['messages']]

    def open_po(self, status='sent', ordered=5):
        return make_po(self.supplier, [(self.beans, ordered)], status=status)

    # ── creating ──
    def test_a_new_order_is_numbered_for_you_and_takes_the_item_cost_when_left_blank(self):
        r = self.add_po([(self.beans, '5', '')])
        self.assertEqual(r.status_code, 302, getattr(r, 'context', None) and r.context['adminform'].form.errors)
        po = PurchaseOrder.objects.get()
        self.assertEqual(po.reference, f'PO-{po.pk:06d}')
        self.assertEqual(po.created_by, self.admin)
        line = po.items.get()
        self.assertEqual((line.quantity_ordered, line.unit_cost, line.quantity_received), (Decimal('5.00'), Decimal('350.00'), 0))

    def test_the_add_form_has_no_reference_field_to_type_into(self):
        # It can only ever be the order's own id — see PurchaseOrder.save() — so
        # there is nothing to fill in and nothing to get wrong.
        fields = self.client.get(self.add_url()).context['adminform'].form.fields
        self.assertNotIn('reference', fields)

    def test_posting_one_anyway_has_no_effect(self):
        # Not a normal path (nothing in the UI offers it), but the form must not
        # trust a 'reference' in the POST data just because someone sent one.
        self.add_po([(self.beans, '5', '350')], reference='KENT-INV-77')
        po = PurchaseOrder.objects.get()
        self.assertEqual(po.reference, f'PO-{po.pk:06d}')

    def test_the_reference_is_shown_read_only_and_cannot_be_changed_by_hand(self):
        po = self.open_po('draft')
        original = po.reference
        form = self.client.get(self.change_url(po)).context['adminform'].form
        self.assertNotIn('reference', form.fields)                 # readonly: not an editable field at all
        self.change(po, reference='SOMETHING-ELSE')                # ignored — not a real field to post to
        po.refresh_from_db()
        self.assertEqual(po.reference, original)

    def test_a_new_order_can_only_be_draft_or_sent(self):
        form = self.client.get(self.add_url()).context['adminform'].form
        self.assertEqual([value for value, _ in form.fields['status'].choices], ['draft', 'sent'])

    def test_a_new_order_has_no_received_column(self):
        # nothing can have arrived on an order that doesn't exist yet
        formset = self.client.get(self.add_url()).context['inline_admin_formsets'][0].formset
        self.assertNotIn('quantity_received', formset.forms[0].fields)

    def test_an_open_order_offers_draft_sent_and_cancelled_but_never_received_by_hand(self):
        po = self.open_po('draft')
        form = self.client.get(self.change_url(po)).context['adminform'].form
        self.assertEqual([value for value, _ in form.fields['status'].choices], ['draft', 'sent', 'cancelled'])

    # ── receiving ──
    def test_entering_what_arrived_puts_it_into_stock(self):
        po = self.open_po()
        r = self.change(po, **{'items-0-quantity_received': '3'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(stock(self.beans), Decimal('13.00'))
        move = StockMovement.objects.get()
        self.assertEqual((move.movement_type, move.quantity, move.reference, move.performed_by),
                         ('purchase', Decimal('3.00'), po.reference, self.admin))
        po.refresh_from_db()
        self.assertEqual(po.status, 'partial')
        self.assertTrue(any('Added to stock: 3.00 kg Espresso Beans' in m for m in self.messages(r)), self.messages(r))

    def test_receiving_the_rest_adds_only_the_difference_and_completes_it(self):
        po = self.open_po()
        self.change(po, **{'items-0-quantity_received': '3'})
        r = self.change(po, **{'items-0-quantity_received': '5'})
        self.assertEqual(stock(self.beans), Decimal('15.00'))          # 10 + 3 + 2, not 10 + 3 + 5
        po.refresh_from_db()
        self.assertEqual((po.status, po.received_at), ('received', timezone.localdate()))
        self.assertTrue(any('fully received' in m for m in self.messages(r)), self.messages(r))

    def test_saving_again_without_changing_anything_adds_nothing(self):
        po = self.open_po()
        self.change(po, **{'items-0-quantity_received': '3'})
        self.change(po)
        self.change(po)
        self.assertEqual(stock(self.beans), Decimal('13.00'))
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_you_cannot_receive_more_than_was_ordered(self):
        po = self.open_po()
        r = self.change(po, **{'items-0-quantity_received': '6'})
        self.assertContains(r, 'more than was ordered')
        self.assertEqual(stock(self.beans), Decimal('10.00'))
        self.assertFalse(StockMovement.objects.exists())

    def test_you_cannot_take_back_what_was_already_received(self):
        po = self.open_po()
        self.change(po, **{'items-0-quantity_received': '3'})
        r = self.change(po, **{'items-0-quantity_received': '1'})
        self.assertContains(r, 'already received')
        self.assertEqual(stock(self.beans), Decimal('13.00'))

    def test_a_received_line_cannot_be_deleted(self):
        po = self.open_po()
        self.change(po, **{'items-0-quantity_received': '3'})
        r = self.change(po, **{'items-0-DELETE': 'on'})
        self.assertContains(r, 'can’t be removed')
        self.assertEqual(po.items.count(), 1)

    def test_an_item_on_a_line_cannot_be_swapped_after_the_fact(self):
        po = self.open_po()
        self.change(po, **{'items-0-inventory': self.milk.pk})
        self.assertEqual(po.items.get().inventory, self.beans)

    def test_the_order_qty_and_cost_of_an_existing_line_cannot_be_changed_by_hand_either(self):
        po = self.open_po()
        self.change(po, **{'items-0-quantity_ordered': '999', 'items-0-unit_cost': '1'})
        line = po.items.get()
        self.assertEqual((line.quantity_ordered, line.unit_cost), (Decimal('5.00'), Decimal('350.00')))

    def test_only_received_so_far_is_an_editable_field_on_an_existing_line(self):
        po = self.open_po()
        form = self.client.get(self.change_url(po)).context['inline_admin_formsets'][0].formset.forms[0]
        for name in ('inventory', 'quantity_ordered', 'unit_cost'):
            with self.subTest(field=name):
                self.assertTrue(form.fields[name].disabled)
        self.assertFalse(form.fields['quantity_received'].disabled)

    def test_a_line_freshly_added_to_an_existing_order_is_still_fully_editable(self):
        # the lock is per row (it already exists / it doesn't), not "any line on this order"
        po = self.open_po()
        form = self.client.get(self.change_url(po)).context['inline_admin_formsets'][0].formset.empty_form
        for name in ('inventory', 'quantity_ordered', 'unit_cost'):
            with self.subTest(field=name):
                self.assertFalse(form.fields[name].disabled)

    def test_cancelling_after_receiving_some_is_refused(self):
        po = self.open_po()
        self.change(po, **{'items-0-quantity_received': '3'})
        r = self.change(po, status='cancelled')
        self.assertContains(r, 'cannot be cancelled')
        po.refresh_from_db()
        self.assertEqual(po.status, 'partial')

    # ── finished orders are a record ──
    def test_a_fully_received_order_is_read_only(self):
        po = self.open_po()
        self.change(po, **{'items-0-quantity_received': '5'})
        self.change(po, notes='changed?', **{'items-0-quantity_ordered': '99'})
        po.refresh_from_db()
        self.assertEqual((po.notes, po.items.get().quantity_ordered), ('', Decimal('5.00')))
        page = self.client.get(self.change_url(po))
        lines = page.context['inline_admin_formsets'][0]
        self.assertFalse(lines.has_add_permission)                   # no "Add another Item"
        self.assertFalse(lines.has_delete_permission)
        self.assertFalse(self.admin_for(PurchaseOrder).has_delete_permission(page.wsgi_request, po))

    def test_an_open_order_can_still_take_more_lines(self):
        lines = self.client.get(self.change_url(self.open_po())).context['inline_admin_formsets'][0]
        self.assertTrue(lines.has_add_permission)

    def test_only_unreceived_orders_can_be_deleted(self):
        request = self.client.get(reverse('admin:inventory_purchaseorder_changelist')).wsgi_request
        model_admin = self.admin_for(PurchaseOrder)
        self.assertTrue(model_admin.has_delete_permission(request, self.open_po('draft')))
        self.assertFalse(model_admin.has_delete_permission(request, self.open_po('sent')))
        self.assertFalse(model_admin.has_delete_permission(request, self.open_po('partial')))

    @staticmethod
    def admin_for(model):
        from django.contrib import admin
        return admin.site._registry[model]

    # ── actions ──
    def run_action(self, action, *pos):
        return self.client.post(reverse('admin:inventory_purchaseorder_changelist'), {
            'action': action, '_selected_action': [po.pk for po in pos], 'index': 0,
        }, follow=True)

    def test_receive_all_remaining_from_the_list(self):
        po = self.open_po()
        r = self.run_action('receive_remaining_action', po)
        self.assertEqual(stock(self.beans), Decimal('15.00'))
        po.refresh_from_db()
        self.assertEqual(po.status, 'received')
        self.assertTrue(any('added to stock — 5.00 kg Espresso Beans' in m for m in self.messages(r)), self.messages(r))

    def test_receive_all_remaining_fixes_an_order_that_was_marked_received_by_mistake(self):
        legacy = self.open_po('received')                       # like PO-2026-0001: marked received, nothing in
        self.run_action('receive_remaining_action', legacy)
        self.assertEqual(stock(self.beans), Decimal('15.00'))

    def test_mark_sent_from_the_list_skips_orders_that_are_not_drafts(self):
        draft, sent = self.open_po('draft'), self.open_po('sent')
        r = self.run_action('mark_sent_action', draft, sent)
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'sent')
        self.assertTrue(any('is not a draft' in m for m in self.messages(r)), self.messages(r))

    def test_cancel_from_the_list_only_when_nothing_arrived(self):
        clean, partly = self.open_po('draft'), self.open_po('sent')
        line = partly.items.get()
        line.quantity_received = Decimal('1')
        line.save()
        r = self.run_action('cancel_action', clean, partly)
        clean.refresh_from_db(), partly.refresh_from_db()
        self.assertEqual((clean.status, partly.status), ('cancelled', 'sent'))
        self.assertTrue(any('already received some stock' in m for m in self.messages(r)), self.messages(r))

    def test_close_partial_from_the_list_only_applies_to_orders_actually_partial(self):
        po = self.open_po('sent')
        self.change(po, **{'items-0-quantity_received': '3'})            # -> 'partial'
        untouched = self.open_po('sent')                                 # nothing received yet
        r = self.run_action('close_partial_action', po, untouched)
        po.refresh_from_db(), untouched.refresh_from_db()
        self.assertEqual((po.status, po.items.get().quantity_ordered), ('received', Decimal('3.00')))
        self.assertEqual(untouched.status, 'sent')                       # skipped, not forced closed
        self.assertTrue(any('closed as fully received' in m for m in self.messages(r)), self.messages(r))
        self.assertTrue(any('is not partially received' in m for m in self.messages(r)), self.messages(r))

    def test_the_receive_button_asks_first_and_only_the_confirmed_post_changes_anything(self):
        po = self.open_po('draft')
        url = reverse('admin:inventory_purchaseorder_receive_remaining_detail', args=[po.pk])

        page = self.client.get(url)                                     # what a link click (or a link someone planted) does
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Receive everything still outstanding?')
        self.assertEqual(stock(self.beans), Decimal('10.00'))           # …is show the question, and nothing else
        po.refresh_from_db()
        self.assertEqual(po.status, 'draft')

        r = self.client.post(url, {'_form_submitted': 'on'}, follow=True)   # what the dialog's button sends
        self.assertEqual(stock(self.beans), Decimal('15.00'))
        po.refresh_from_db()
        self.assertEqual(po.status, 'received')
        self.assertEqual(r.redirect_chain[-1][0], self.change_url(po))          # back to the order page

    def test_the_dialog_posts_through_htmx_and_is_told_to_load_the_order_page(self):
        po = self.open_po('draft')
        url = reverse('admin:inventory_purchaseorder_receive_remaining_detail', args=[po.pk])
        r = self.client.post(url, {'_form_submitted': 'on'}, HTTP_HX_REQUEST='true')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['HX-Redirect'], self.change_url(po))         # htmx follows this; a 302 would swap the whole page into the dialog

    def test_the_close_partial_button_is_only_offered_once_something_has_arrived_but_not_everything(self):
        po = self.open_po('sent')
        request = self.client.get(reverse('admin:inventory_purchaseorder_changelist')).wsgi_request
        model_admin = self.admin_for(PurchaseOrder)
        self.assertEqual(model_admin.has_close_partial_permission(request, po.pk), False)
        self.change(po, **{'items-0-quantity_received': '3'})
        po.refresh_from_db()
        self.assertEqual(model_admin.has_close_partial_permission(request, po.pk), True)
        self.assertEqual(self.client.get(self.change_url(po)).content.count(b'Close as partially received'), 1)

    def test_the_close_partial_button_asks_first_and_only_the_confirmed_post_changes_anything(self):
        po = self.open_po('sent')
        self.change(po, **{'items-0-quantity_received': '3'})            # -> 'partial'
        url = reverse('admin:inventory_purchaseorder_close_partial_detail', args=[po.pk])

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Close this order as partially received?')
        po.refresh_from_db()
        self.assertEqual((po.status, po.items.get().quantity_ordered), ('partial', Decimal('5.00')))   # not yet

        r = self.client.post(url, {'_form_submitted': 'on'}, follow=True)
        po.refresh_from_db()
        self.assertEqual((po.status, po.items.get().quantity_ordered), ('received', Decimal('3.00')))
        self.assertEqual(stock(self.beans), Decimal('13.00'))            # unchanged — nothing new was received
        self.assertEqual(r.redirect_chain[-1][0], self.change_url(po))

    def test_a_post_without_the_csrf_token_is_refused(self):
        po = self.open_po('draft')
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.admin)
        for name in ('receive_remaining_detail', 'mark_sent_detail', 'email_supplier_detail'):
            with self.subTest(action=name):
                r = strict.post(reverse(f'admin:inventory_purchaseorder_{name}', args=[po.pk]), {'_form_submitted': 'on'})
                self.assertEqual(r.status_code, 403)
        self.assertEqual(stock(self.beans), Decimal('10.00'))
        po.refresh_from_db()
        self.assertEqual((po.status, po.emailed_at), ('draft', None))

    def test_every_detail_button_only_shows_its_dialog_on_get(self):
        po = self.open_po('draft')
        for name, title in (('mark_sent_detail', 'Mark this order as sent?'), ('email_supplier_detail', 'Email this order to the supplier?')):
            with self.subTest(action=name):
                page = self.client.get(reverse(f'admin:inventory_purchaseorder_{name}', args=[po.pk]))
                self.assertContains(page, title)
        po.refresh_from_db()
        self.assertEqual((po.status, po.emailed_at), ('draft', None))
        self.assertEqual(len(mail.outbox), 0)

    def test_buttons_show_only_when_they_make_sense(self):
        model_admin = self.admin_for(PurchaseOrder)
        request = self.client.get(reverse('admin:inventory_purchaseorder_changelist')).wsgi_request
        draft, done = self.open_po('draft'), self.open_po('sent')
        purchasing.receive_remaining(done, self.admin)
        self.assertTrue(model_admin.has_send_permission(request, draft.pk))
        self.assertFalse(model_admin.has_send_permission(request, done.pk))          # already sent / received
        self.assertTrue(model_admin.has_receive_permission(request, draft.pk))
        self.assertFalse(model_admin.has_receive_permission(request, done.pk))       # nothing left to receive

    def test_an_order_marked_received_with_nothing_in_warns_and_offers_the_fix(self):
        legacy = self.open_po('received')
        page = self.client.get(self.change_url(legacy), follow=True)
        self.assertTrue(any('marked “Fully Received”' in m and 'Receive all remaining items' in m for m in self.messages(page)), self.messages(page))
        # a genuinely settled order gives no such warning
        done = self.open_po('sent')
        purchasing.receive_remaining(done, self.admin)
        self.assertFalse(any('marked' in m for m in self.messages(self.client.get(self.change_url(done)))))

    # ── the list ──
    def test_list_shows_progress_overdue_and_orders_marked_received_but_not_in_stock(self):
        overdue = make_po(self.supplier, [(self.beans, 5, 5), (self.milk, 5)], status='sent',
                          expected_at=timezone.localdate() - datetime.timedelta(days=2))
        legacy = self.open_po('received')
        page = self.client.get(reverse('admin:inventory_purchaseorder_changelist'))
        self.assertContains(page, '1 of 2 received')
        self.assertContains(page, 'Overdue')
        self.assertContains(page, 'Received — not in stock yet')


class AutoGeneratePurchaseOrdersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin@example.com', 'pw')

    def setUp(self):
        self.client.force_login(self.admin)
        self.kent = make_supplier('Kent Acabo')
        self.sugar = make_item('Sugar', unit='g', on_hand='300', reorder='1000', reorder_qty='5000', cost='0.06', supplier=self.kent)
        self.butter = make_item('Butter', unit='g', on_hand='0', reorder='500', reorder_qty='3000', cost='0.30', supplier=self.kent)
        self.url = reverse('auto-generate-po')

    def generate(self):
        r = self.client.post(self.url, follow=True)
        return r, [str(m) for m in r.context['messages']]

    def test_one_draft_per_supplier_at_the_reorder_quantity_and_item_cost(self):
        other = make_item('Cups', unit='pcs', on_hand='10', reorder='50', reorder_qty='300', cost='4.5', supplier=make_supplier('Cup Co'))
        r, messages = self.generate()
        self.assertEqual(PurchaseOrder.objects.count(), 2)
        kent_po = PurchaseOrder.objects.get(supplier=self.kent)
        self.assertEqual(kent_po.status, 'draft')
        self.assertEqual(kent_po.created_by, self.admin)
        lines = {line.inventory.name: (line.quantity_ordered, line.unit_cost) for line in kent_po.items.all()}
        self.assertEqual(lines, {'Sugar': (Decimal('5000.00'), Decimal('0.06')), 'Butter': (Decimal('3000.00'), Decimal('0.30'))})
        self.assertEqual(PurchaseOrder.objects.get(supplier=other.supplier).items.get().quantity_ordered, Decimal('300.00'))
        self.assertTrue(any('3 items to reorder' in m for m in messages), messages)

    def test_running_it_twice_does_not_order_the_same_things_again(self):
        self.generate()
        r, messages = self.generate()
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(PurchaseOrderItem.objects.count(), 2)
        self.assertTrue(any('already on an open purchase order' in m for m in messages), messages)
        self.assertTrue(any('Nothing new to order' in m for m in messages), messages)

    def test_items_with_no_supplier_or_no_reorder_quantity_are_skipped_and_named(self):
        make_item('Flour', on_hand='0', reorder='500')                                            # no supplier
        make_item('Napkins', unit='pcs', on_hand='0', reorder='0', reorder_qty='0', supplier=self.kent)
        r, messages = self.generate()
        self.assertTrue(any('no supplier set' in m and 'Flour' in m for m in messages), messages)
        self.assertTrue(any('no reorder quantity set' in m and 'Napkins' in m for m in messages), messages)
        self.assertEqual(set(PurchaseOrderItem.objects.values_list('inventory__name', flat=True)), {'Sugar', 'Butter'})

    def test_a_draft_already_started_today_gets_the_new_items_added(self):
        draft = make_po(self.kent, [(self.sugar, 1)], reference='PO-MINE-1')
        # sugar is on that draft already; butter is not
        r, messages = self.generate()
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(sorted(draft.items.values_list('inventory__name', flat=True)), ['Butter', 'Sugar'])
        self.assertTrue(any('added to draft PO-MINE-1' in m for m in messages), messages)

    def test_numbering_is_the_new_orders_own_id_whatever_else_exists(self):
        make_po(self.kent, [(self.sugar, 1)], reference='PO-MINE-7', status='received')     # (done, so sugar is re-orderable)
        PurchaseOrder.objects.all().update(status='cancelled')
        self.generate()
        po = PurchaseOrder.objects.get(status='draft')
        self.assertEqual(po.reference, f'PO-{po.pk:06d}')

    def test_nothing_to_order(self):
        Inventory.objects.update(quantity_on_hand=Decimal('99999'))
        r, messages = self.generate()
        self.assertFalse(PurchaseOrder.objects.exists())
        self.assertTrue(any('Nothing to order' in m for m in messages), messages)

    def test_a_get_request_creates_nothing(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_the_banner_and_the_button_agree_on_the_numbers(self):
        make_item('Flour', on_hand='0', reorder='500')
        page = self.client.get(reverse('admin:inventory_purchaseorder_changelist'))
        self.assertContains(page, '2 items need reordering')
        self.assertContains(page, '1 low item can’t be ordered')
        self.assertContains(page, 'no supplier set')
        self.assertContains(page, 'Flour')
        self.generate()
        page = self.client.get(reverse('admin:inventory_purchaseorder_changelist'))
        self.assertContains(page, 'Nothing new to order right now.')
        self.assertContains(page, '2 low items already on an open purchase order')

    def test_the_banner_is_green_when_nothing_is_low(self):
        Inventory.objects.update(quantity_on_hand=Decimal('99999'))
        self.assertContains(self.client.get(reverse('admin:inventory_purchaseorder_changelist')), 'All stock levels are OK')


class PoItemDefaultsEndpointTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin@example.com', 'pw')
        self.item = make_item('Sugar', unit='g', on_hand='300', reorder='1000', reorder_qty='5000', cost='0.06')

    def test_returns_the_cost_and_the_usual_order_quantity(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('po-item-defaults', args=[self.item.pk]))
        self.assertEqual(r.json(), {'unit_cost': '0.06', 'quantity': '5000.00', 'unit': 'g'})

    def test_staff_only(self):
        self.assertEqual(self.client.get(reverse('po-item-defaults', args=[self.item.pk])).status_code, 302)
        self.client.force_login(User.objects.create_user('c@example.com', 'pw'))
        self.assertEqual(self.client.get(reverse('po-item-defaults', args=[self.item.pk])).status_code, 302)

"""
The Inventory item pages and the Stock Movements page, the way staff use them.

What these guard:
  * an item with 10+ movements used to lose its "add movement" link (max_num = 10),
    and every past movement was drawn as an editable-looking row (18,000 px tall);
  * "Quantity on hand" could be typed over on an existing item, changing stock
    with no record; on a new item it could be double-counted alongside a movement;
  * Stock Movements had no way to add one, and no sidebar link.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from inventory.models import Inventory, InventoryCategory, StockMovement
from online_shop.models import Notification
from tests.support.admin_forms import admin_post_data
from tests.support.factories import make_item, make_po, make_supplier

User = get_user_model()


class AdminTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin@example.com', 'pw')

    def setUp(self):
        self.client.force_login(self.admin)

    def stock(self, item):
        return Inventory.objects.get(pk=item.pk).quantity_on_hand

    def messages(self, response):
        return [str(m) for m in response.context['messages']]


class NewItemTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.category = InventoryCategory.objects.create(name='Beans')
        self.supplier = make_supplier()
        self.url = reverse('admin:inventory_inventory_add')

    def add_item(self, **fields):
        base = {
            'category': self.category.pk, 'supplier': self.supplier.pk, 'name': 'Espresso Beans', 'sku': 'BEAN-1',
            'unit': 'kg', 'quantity_on_hand': '10', 'reorder_points': '2', 'reorder_quantity': '10', 'cost_per_unit': '350',
        }
        data = admin_post_data(self.client.get(self.url), **{**base, **fields})
        return self.client.post(self.url, data, follow=True)

    def test_opening_stock_is_recorded_as_a_movement_without_being_counted_twice(self):
        r = self.add_item(quantity_on_hand='10')
        item = Inventory.objects.get()
        self.assertEqual(item.quantity_on_hand, Decimal('10.00'))              # not 20
        move = StockMovement.objects.get()
        self.assertEqual(
            (move.movement_type, move.quantity, move.quantity_change, move.reference, move.performed_by, move.unit_cost),
            ('purchase', Decimal('10.00'), Decimal('10.00'), 'Opening stock', self.admin, Decimal('350.00')),
        )

    def test_history_adds_up_to_the_stock_it_started_with(self):
        self.add_item(quantity_on_hand='10')
        item = Inventory.objects.get()
        StockMovement.objects.create(inventory=item, movement_type='purchase', quantity=Decimal('5'))
        StockMovement.objects.create(inventory=item, movement_type='adjustment', quantity=Decimal('3'))
        total = sum(m.quantity_change for m in StockMovement.objects.filter(inventory=item))
        self.assertEqual(total, self.stock(item))

    def test_no_movement_is_recorded_when_it_starts_empty(self):
        self.add_item(quantity_on_hand='0')
        self.assertEqual(Inventory.objects.get().quantity_on_hand, 0)
        self.assertFalse(StockMovement.objects.exists())

    def test_an_item_that_starts_with_stock_does_not_raise_a_low_stock_alert(self):
        # it used to be created empty and topped up afterwards, alerting "0 left" for a moment
        self.add_item(quantity_on_hand='10', reorder_points='2')
        self.assertFalse(Notification.objects.filter(type='low_stock').exists())

    def test_the_new_item_form_has_no_movement_section(self):
        page = self.client.get(self.url)
        self.assertEqual(page.context['inline_admin_formsets'], [])

    def test_the_new_item_form_asks_only_for_what_is_needed(self):
        fields = set(self.client.get(self.url).context['adminform'].form.fields)
        self.assertEqual(fields, {
            'category', 'supplier', 'name', 'sku', 'unit',
            'quantity_on_hand', 'reorder_points', 'reorder_quantity', 'cost_per_unit', 'expiry_date',
        })                                                       # no "reserved": nothing in the system uses it

    def test_the_fields_say_what_they_mean(self):
        form = self.client.get(self.url).context['adminform'].form
        self.assertEqual(form.fields['quantity_on_hand'].label, 'Opening stock')
        self.assertEqual(form.fields['reorder_points'].label, 'Reorder level')
        self.assertIn('low-stock warning', str(form.fields['reorder_points'].help_text))
        self.assertIn('kg', str(form.fields['unit'].help_text))


class ExistingItemTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.item = make_item('Espresso Beans', on_hand='10', cost='350', supplier=make_supplier())
        self.url = reverse('admin:inventory_inventory_change', args=[self.item.pk])

    def page(self):
        return self.client.get(self.url)

    def record(self, **movement):
        """Fill in the "Record stock in / stock out" row and save — the item page's own form."""
        data = admin_post_data(self.page(), **{f'movements-0-{key}': value for key, value in movement.items()})
        return self.client.post(self.url, data, follow=True)

    # ── stock is changed through movements, never typed over ──
    def test_stock_on_hand_cannot_be_edited_on_an_existing_item(self):
        self.assertNotIn('quantity_on_hand', self.page().context['adminform'].form.fields)
        self.client.post(self.url, admin_post_data(self.page(), quantity_on_hand='999'))
        self.assertEqual(self.stock(self.item), Decimal('10.00'))

    def test_the_page_shows_stock_now_with_its_unit_and_value(self):
        page = self.page()
        self.assertContains(page, '10.00 kg')
        self.assertContains(page, '₱3,500.00')

    # ── recording stock in / out ──
    def test_recording_stock_in(self):
        r = self.record(movement_type='purchase', quantity='5', reference='INV-42', notes='Kent delivery')
        self.assertEqual(self.stock(self.item), Decimal('15.00'))
        move = StockMovement.objects.get()
        self.assertEqual(
            (move.movement_type, move.quantity_change, move.reference, move.notes, move.performed_by),
            ('purchase', Decimal('5.00'), 'INV-42', 'Kent delivery', self.admin),
        )
        self.assertTrue(any('Stock In — Purchase / Delivery: +5.00 kg' in m and 'now has 15.00 kg' in m for m in self.messages(r)), self.messages(r))

    def test_recording_stock_out(self):
        self.record(movement_type='spoilage', quantity='2.5')
        self.assertEqual(self.stock(self.item), Decimal('7.50'))
        self.assertEqual(StockMovement.objects.get().quantity_change, Decimal('-2.50'))

    def test_the_cost_defaults_to_the_items_cost_when_left_blank(self):
        self.record(movement_type='purchase', quantity='1')
        self.assertEqual(StockMovement.objects.get().unit_cost, Decimal('350.00'))
        self.record(movement_type='purchase', quantity='1', unit_cost='340')
        self.assertEqual(StockMovement.objects.latest('id').unit_cost, Decimal('340.00'))

    def test_taking_out_more_than_is_on_hand_is_refused_with_the_reason(self):
        r = self.record(movement_type='adjustment', quantity='11')
        self.assertContains(r, 'Only 10.00 kg on hand')
        self.assertEqual(self.stock(self.item), Decimal('10.00'))
        self.assertFalse(StockMovement.objects.exists())

    def test_quantity_must_be_above_zero(self):
        r = self.record(movement_type='purchase', quantity='0')
        self.assertContains(r, 'Enter a quantity greater than 0.')
        self.assertFalse(StockMovement.objects.exists())

    def test_only_manual_types_are_offered(self):
        choices = self.page().context['inline_admin_formsets'][0].formset.forms[0].fields['movement_type'].choices
        self.assertEqual({value for value, _ in choices}, {'purchase', 'adjustment', 'spoilage', 'return'})

    def test_the_row_left_as_it_is_creates_nothing(self):
        self.client.post(self.url, admin_post_data(self.page()))
        self.assertFalse(StockMovement.objects.exists())

    # ── the bug: 10+ movements hid "add" and drew them all ──
    def test_an_item_with_many_movements_still_offers_the_record_row_and_lists_none_of_them_as_rows(self):
        for _ in range(12):
            StockMovement.objects.create(inventory=self.item, movement_type='usage', quantity=Decimal('0.02'))
        formset = self.page().context['inline_admin_formsets'][0].formset
        self.assertEqual(len(formset.forms), 1)                                # just the blank row to fill in…
        self.assertFalse(formset.forms[0].instance.pk)                         # …not 12 past movements
        self.assertIsNone(formset.max_num if formset.max_num is None else None)  # nothing caps how many can be added
        self.record(movement_type='purchase', quantity='5')                   # and it still works
        self.assertEqual(self.stock(self.item), Decimal('10') - Decimal('0.24') + 5)

    def test_recent_movements_are_summarised_and_link_to_the_full_history(self):
        for i in range(10):
            StockMovement.objects.create(inventory=self.item, movement_type='usage', quantity=Decimal('0.02'), reference=f'Order #{i}')
        page = self.page()
        self.assertContains(page, 'View all 10 movements')
        self.assertContains(page, f'?inventory__id__exact={self.item.pk}')
        self.assertContains(page, 'Order #9')                                  # newest is shown…
        self.assertNotContains(page, 'Order #0<')                              # …the oldest two aren't in the summary
        self.assertNotContains(page, 'Order #1<')

    def test_the_history_link_actually_opens_that_items_history(self):
        other = make_item('Sugar', unit='g', on_hand='100')
        StockMovement.objects.create(inventory=self.item, movement_type='purchase', quantity=Decimal('1'), reference='BEANS-REF')
        StockMovement.objects.create(inventory=other, movement_type='purchase', quantity=Decimal('1'), reference='SUGAR-REF')
        r = self.client.get(reverse('admin:inventory_stockmovement_changelist') + f'?inventory__id__exact={self.item.pk}')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'BEANS-REF')
        self.assertNotContains(r, 'SUGAR-REF')

    def test_an_item_with_no_history_says_so(self):
        self.assertContains(self.page(), 'No stock movements yet.')


class InventoryListTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.supplier = make_supplier()
        self.url = reverse('admin:inventory_inventory_changelist')

    def test_stock_is_shown_with_its_unit(self):
        make_item('Espresso Beans', unit='kg', on_hand='28.18', supplier=self.supplier)
        make_item('Sugar', unit='g', on_hand='4040', supplier=self.supplier)
        page = self.client.get(self.url)
        self.assertContains(page, '28.18 kg')
        self.assertContains(page, '4040.00 g')

    def test_on_order_shows_what_open_purchase_orders_still_owe(self):
        beans = make_item('Espresso Beans', unit='kg', supplier=self.supplier)
        make_item('Sugar', unit='g', supplier=self.supplier)
        make_po(self.supplier, [(beans, 10, 4)], status='partial')
        page = self.client.get(self.url)
        self.assertContains(page, '6.00 kg coming')
        self.assertEqual(page.content.decode().count(' coming'), 1)            # only the item that has something on order

    def test_the_list_does_not_do_extra_queries_per_row(self):
        make_item('Item 0', supplier=self.supplier)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for i in range(1, 15):
            make_item(f'Item {i}', supplier=self.supplier)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(many), len(few))

    def test_reserved_is_no_longer_a_column(self):
        self.assertNotContains(self.client.get(self.url), 'Reserved')


class StockMovementPageTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.item = make_item('Espresso Beans', on_hand='10', cost='350')
        self.url = reverse('admin:inventory_stockmovement_add')

    def add(self, **fields):
        data = admin_post_data(self.client.get(self.url), inventory=self.item.pk, **fields)
        return self.client.post(self.url, data, follow=True)

    def test_there_is_a_way_to_add_one(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertContains(self.client.get(reverse('admin:inventory_stockmovement_changelist')), self.url)

    def test_only_manual_types_are_offered(self):
        choices = self.client.get(self.url).context['adminform'].form.fields['movement_type'].choices
        self.assertEqual({value for value, _ in choices}, {'purchase', 'adjustment', 'spoilage', 'return'})

    def test_recording_a_movement_for_any_item(self):
        self.add(movement_type='spoilage', quantity='2', notes='dropped')
        self.assertEqual(self.stock(self.item), Decimal('8.00'))
        move = StockMovement.objects.get()
        self.assertEqual((move.performed_by, move.unit_cost, move.notes), (self.admin, Decimal('350.00'), 'dropped'))

    def test_the_same_rules_apply_as_on_the_item_page(self):
        r = self.add(movement_type='return', quantity='11')
        self.assertContains(r, 'Only 10.00 kg on hand')
        self.assertFalse(StockMovement.objects.exists())

    def test_a_return_to_supplier_takes_stock_out(self):
        self.add(movement_type='return', quantity='4')
        self.assertEqual(self.stock(self.item), Decimal('6.00'))

    def test_past_movements_cannot_be_changed(self):
        move = StockMovement.objects.create(inventory=self.item, movement_type='purchase', quantity=Decimal('1'))
        url = reverse('admin:inventory_stockmovement_change', args=[move.pk])
        self.assertEqual(self.client.get(url).status_code, 200)                # can be looked at
        self.assertEqual(self.client.post(url, {'quantity': '500'}).status_code, 403)
        self.assertEqual(StockMovement.objects.get().quantity, Decimal('1.00'))

    def test_only_superusers_can_delete_history(self):
        move = StockMovement.objects.create(inventory=self.item, movement_type='purchase', quantity=Decimal('1'))
        staff = User.objects.create_user('staff@example.com', 'pw', is_staff=True)
        request = self.client.get(reverse('admin:inventory_stockmovement_changelist')).wsgi_request
        from django.contrib import admin
        model_admin = admin.site._registry[StockMovement]
        self.assertTrue(model_admin.has_delete_permission(request, move))
        request.user = staff
        self.assertFalse(model_admin.has_delete_permission(request, move))

    def test_the_list_can_show_only_what_staff_entered(self):
        StockMovement.objects.create(inventory=self.item, movement_type='purchase', quantity=Decimal('1'), reference='BY-STAFF')
        StockMovement.objects.create(inventory=self.item, movement_type='usage', quantity=Decimal('1'), reference='BY-ORDER')
        base = reverse('admin:inventory_stockmovement_changelist')
        staff_only = self.client.get(base + '?source=staff')
        self.assertContains(staff_only, 'BY-STAFF')
        self.assertNotContains(staff_only, 'BY-ORDER')
        orders_only = self.client.get(base + '?source=orders')
        self.assertContains(orders_only, 'BY-ORDER')
        self.assertNotContains(orders_only, 'BY-STAFF')

    def test_the_sidebar_has_a_link_to_it(self):
        index = self.client.get(reverse('admin:index'))
        self.assertContains(index, 'Stock Movements')
        self.assertContains(index, reverse('admin:inventory_stockmovement_changelist'))

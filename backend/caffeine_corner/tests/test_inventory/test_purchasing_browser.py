"""
Real-browser tests for the inventory screens staff actually click through:
the Purchase Order form (auto-fill, numbering, receiving) and the item page.

These need a browser because the behaviour is in the page: the Item picker on a
PO line is a select2 autocomplete that fills in cost and quantity by JavaScript
(static/js/po-item-defaults.js), the Receive button and read-only lock come from
the admin's own rendering, and the whole point of the item-page fix was how the
page *looks* with a lot of history on it.

Skipped automatically when Playwright/Chromium isn't available (see
tests/support/browser_testing.py). Run just this file with:

    python manage.py test tests.test_inventory.test_purchasing_browser
"""
import re
from decimal import Decimal

from inventory.models import Inventory, PurchaseOrder, StockMovement
from tests.support import browser_testing
from tests.support.factories import make_item, make_po, make_supplier


class PurchaseOrderBrowserTests(browser_testing.AdminBrowserTestCase):
    def setUp(self):
        super().setUp()
        self.supplier = make_supplier()
        self.beans = make_item('Espresso Beans', unit='kg', on_hand='10', reorder='2', reorder_qty='10', cost='350', supplier=self.supplier)
        self.log_in_without_a_page()

    def stock(self):
        return Inventory.objects.get(pk=self.beans.pk).quantity_on_hand

    def pick_item_on_first_line(self, text='Espresso'):
        row = self.page.locator('tr', has=self.page.locator('#id_items-0-inventory'))
        row.locator('.select2-selection').first.click()
        self.page.locator('.select2-search__field').fill(text)
        self.page.locator('.select2-results__option', has_text=text).first.click()
        return row

    def confirm(self, button, submit):
        """Press a button on the order's page, then the confirmation's own button (nothing happens until that one)."""
        self.page.get_by_role('link', name=button).click()
        self.page.get_by_role('button', name=submit).click()

    def new_order_with_beans(self, quantity=None):
        self.page.goto(self.url('/admin/inventory/purchaseorder/add/'))
        self.page.select_option('#id_supplier', label=self.supplier.name)
        self.pick_item_on_first_line()
        if quantity:
            self.page.fill('#id_items-0-quantity_ordered', quantity)
        self.page.click('[name=_save]')
        self.page.wait_for_url('**/purchaseorder/')
        return PurchaseOrder.objects.get()

    # ── the form fills in what staff would have to look up ──
    def test_picking_an_item_fills_in_its_cost_and_usual_quantity_and_the_line_total_follows(self):
        self.page.goto(self.url('/admin/inventory/purchaseorder/add/'))
        row = self.pick_item_on_first_line()
        self.page.wait_for_function("document.querySelector('#id_items-0-unit_cost').value !== ''")
        self.assertEqual(self.page.input_value('#id_items-0-unit_cost'), '350.00')          # the item's cost
        self.assertEqual(self.page.input_value('#id_items-0-quantity_ordered'), '10.00')     # its reorder quantity
        self.assertEqual(row.locator('.field-line_total').inner_text().strip(), '₱3,500.00')
        self.page.fill('#id_items-0-quantity_ordered', '4')                                  # the total follows as you type
        self.assertEqual(row.locator('.field-line_total').inner_text().strip(), '₱1,400.00')

    def test_a_quantity_typed_before_picking_the_item_is_not_overwritten(self):
        self.page.goto(self.url('/admin/inventory/purchaseorder/add/'))
        self.page.fill('#id_items-0-quantity_ordered', '3')
        self.pick_item_on_first_line()
        self.page.wait_for_function("document.querySelector('#id_items-0-unit_cost').value !== ''")
        self.assertEqual(self.page.input_value('#id_items-0-quantity_ordered'), '3')

    # ── numbering, receiving, locking ──
    def test_a_new_order_is_numbered_and_receiving_it_puts_stock_in_and_locks_it(self):
        po = self.new_order_with_beans(quantity='4')
        self.assertEqual(po.reference, f'PO-{po.pk:06d}')                                    # nobody typed a number
        self.assertEqual((po.status, self.stock()), ('draft', Decimal('10.00')))

        self.page.goto(self.url(f'/admin/inventory/purchaseorder/{po.pk}/change/'))
        self.page.fill('#id_items-0-quantity_received', '1')                                 # 1 of 4 arrives
        self.page.click('[name=_continue]')
        self.page.wait_for_selector('text=Added to stock: 1.00 kg Espresso Beans')
        self.assertEqual(self.stock(), Decimal('11.00'))
        self.assertEqual(self.page.locator('#id_status option:checked').inner_text(), 'Partially Received')

        self.confirm('Receive all remaining items', 'Add to stock')                          # the rest arrives
        self.page.wait_for_selector('text=added to stock —')
        self.assertEqual(self.stock(), Decimal('14.00'))                                     # 10 + 1 + 3, not 10 + 1 + 4
        po.refresh_from_db()
        self.assertEqual(po.status, 'received')
        self.assertEqual(self.page.locator('select#id_status').count(), 0)                   # now a read-only record
        self.assertFalse(self.page.get_by_text('Add another Item').is_visible())
        self.assertEqual(self.page.get_by_role('link', name='Receive all remaining items').count(), 0)
        self.assertEqual(StockMovement.objects.filter(reference=po.reference).count(), 2)    # both arrivals are on the item's record

    def test_the_list_actions_and_banner_use_the_same_orders(self):
        make_po(self.supplier, [(self.beans, 5)], status='sent')
        self.page.goto(self.url('/admin/inventory/purchaseorder/'))
        self.page.locator('input.action-select').first.check()
        self.page.locator('select[name=action]').first.select_option('receive_remaining_action')
        self.page.click('button[name=index]')
        self.page.wait_for_selector('text=added to stock')
        self.assertEqual(self.stock(), Decimal('15.00'))

    def test_an_order_marked_received_with_nothing_in_warns_and_can_be_fixed(self):
        legacy = make_po(self.supplier, [(self.beans, 5)], status='received')                # what PO-2026-0001 looked like
        self.page.goto(self.url(f'/admin/inventory/purchaseorder/{legacy.pk}/change/'))
        self.page.wait_for_selector('text=is marked “Fully Received”')
        self.confirm('Receive all remaining items', 'Add to stock')
        self.page.wait_for_selector('text=added to stock —')
        self.assertEqual(self.stock(), Decimal('15.00'))

    def test_auto_generate_makes_one_draft_and_says_what_it_skipped(self):
        Inventory.objects.filter(pk=self.beans.pk).update(quantity_on_hand=Decimal('1'))    # below its reorder level of 2
        make_item('Flour', unit='g', on_hand='0', reorder='500')                             # low, but no supplier
        self.page.goto(self.url('/admin/inventory/purchaseorder/'))
        self.assertIn('1 item needs reordering', self.page.inner_text('body'))
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.page.get_by_role('button', name='Auto-Generate Purchase Orders').click()
        self.page.wait_for_selector('text=Skipped — no supplier set')
        po = PurchaseOrder.objects.get()
        self.assertEqual((po.status, po.items.get().quantity_ordered), ('draft', Decimal('10.00')))
        self.assertIn('Nothing new to order right now.', self.page.inner_text('body'))       # the banner reflects it at once


class ItemPageBrowserTests(browser_testing.AdminBrowserTestCase):
    def setUp(self):
        super().setUp()
        self.beans = make_item('Espresso Beans', unit='kg', on_hand='30', reorder='2', cost='350', supplier=make_supplier())
        for i in range(40):
            StockMovement.objects.create(inventory=self.beans, movement_type='usage', quantity=Decimal('0.02'), reference=f'Order #{i}')
        self.log_in_without_a_page()
        self.page.goto(self.url(f'/admin/inventory/inventory/{self.beans.pk}/change/'))

    def stock(self):
        return Inventory.objects.get(pk=self.beans.pk).quantity_on_hand

    def test_a_busy_item_page_stays_short_and_keeps_its_record_form(self):
        # with 40 movements it used to be ~10,000 px of editable-looking rows, with "add" hidden
        self.assertLess(self.page.evaluate('document.documentElement.scrollHeight'), 3200)
        self.assertTrue(self.page.get_by_text('Record stock in / stock out').first.is_visible())
        self.assertTrue(self.page.locator('#id_movements-0-quantity').is_visible())
        self.assertIn('View all 40 movements', self.page.inner_text('body'))

    def test_recording_stock_out_updates_the_item_and_says_so(self):
        before = self.stock()
        self.page.select_option('#id_movements-0-movement_type', 'spoilage')
        self.page.fill('#id_movements-0-quantity', '2')
        self.page.fill('#id_movements-0-notes', 'dropped a bag')
        self.page.click('[name=_continue]')
        self.page.wait_for_selector('text=Stock Out — Spoilage / Waste: −2.00 kg')
        self.assertEqual(self.stock(), before - 2)
        self.assertEqual(StockMovement.objects.filter(movement_type='spoilage').get().notes, 'dropped a bag')

    def test_taking_out_more_than_is_there_is_explained_on_the_field(self):
        self.page.select_option('#id_movements-0-movement_type', 'adjustment')
        self.page.fill('#id_movements-0-quantity', '500')
        self.page.click('[name=_continue]')
        self.page.wait_for_selector('text=on hand — you can’t take out 500.00')
        self.assertEqual(self.stock(), Decimal('30.00') - Decimal('0.80'))                   # nothing was removed
        self.assertFalse(StockMovement.objects.filter(movement_type='adjustment').exists())

    def test_the_history_link_opens_only_this_items_movements(self):
        make_item('Sugar', unit='g', on_hand='100')
        self.page.get_by_role('link', name=re.compile('View all 40 movements')).click()
        self.page.wait_for_selector('text=40 Stock Movements')
        self.assertIn('Espresso Beans', self.page.inner_text('body'))
        self.assertNotIn('Sugar', self.page.inner_text('#result_list, table'))

    def test_a_new_item_starts_with_opening_stock_that_is_recorded_once(self):
        self.page.goto(self.url('/admin/inventory/inventory/add/'))
        self.assertEqual(self.page.locator('input[name="movements-TOTAL_FORMS"]').count(), 0)   # nothing to record a movement against yet
        for field, value in [('name', 'Sugar'), ('sku', 'SUGAR-1'), ('unit', 'g'), ('quantity_on_hand', '500'),
                             ('reorder_points', '100'), ('reorder_quantity', '1000'), ('cost_per_unit', '0.06')]:
            self.page.fill(f'#id_{field}', value)
        self.page.click('[name=_save]')
        self.page.wait_for_url('**/inventory/inventory/')
        sugar = Inventory.objects.get(sku='SUGAR-1')
        self.assertEqual(sugar.quantity_on_hand, Decimal('500.00'))                           # not 1,000
        opening = StockMovement.objects.get(inventory=sugar)
        self.assertEqual((opening.reference, opening.quantity_change), ('Opening stock', Decimal('500.00')))

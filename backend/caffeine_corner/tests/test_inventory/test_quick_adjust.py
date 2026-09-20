"""The "+" / "−" Quick Adjust widget on the Inventory list (htmx_adjust_stock)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import Inventory, InventoryCategory, StockMovement

User = get_user_model()


class QuickAdjustTests(TestCase):
    """The "+" / "−" widget on the Inventory list (htmx_adjust_stock)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('staff@example.com', 'pw', is_staff=True)
        cls.customer = User.objects.create_user('customer@example.com', 'pw')
        cls.item = Inventory.objects.create(
            category=InventoryCategory.objects.create(name='Beans'), name='Espresso Beans', sku='BEAN-1',
            unit='kg', quantity_on_hand=Decimal('10'), reorder_points=Decimal('2'), cost_per_unit=Decimal('350'),
        )

    def url(self, kind='purchase'):
        return reverse('htmx-adjust-stock', args=[self.item.pk]) + f'?type={kind}'

    def adjust(self, quantity, kind='purchase'):
        self.client.force_login(self.staff)
        return self.client.post(self.url(kind), {'quantity': quantity})

    def stock(self):
        return Inventory.objects.get(pk=self.item.pk).quantity_on_hand

    def test_plus_adds_stock_and_logs_a_purchase(self):
        r = self.adjust('5')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.stock(), Decimal('15.00'))
        m = StockMovement.objects.get()
        self.assertEqual((m.movement_type, m.quantity, m.quantity_change), ('purchase', Decimal('5.00'), Decimal('5.00')))
        self.assertEqual((m.performed_by, m.unit_cost, m.reference), (self.staff, Decimal('350.00'), 'Quick adjust (admin)'))
        # the widget plus the Stock Level / Status cells come back together, so all three stay in sync
        self.assertContains(r, f'id="qa-{self.item.pk}"')
        self.assertContains(r, f'id="stock-bar-{self.item.pk}"')
        self.assertContains(r, f'id="stock-status-{self.item.pk}"')

    def test_minus_removes_stock_and_logs_an_adjustment(self):
        self.assertEqual(self.adjust('3', 'adjustment').status_code, 200)
        self.assertEqual(self.stock(), Decimal('7.00'))
        m = StockMovement.objects.get()
        self.assertEqual((m.movement_type, m.quantity_change), ('adjustment', Decimal('-3.00')))

    def test_decimal_quantities_are_kept(self):
        self.adjust('2.5')
        self.assertEqual(self.stock(), Decimal('12.50'))

    def test_taking_out_more_than_is_on_hand_is_refused(self):
        # 10 kg on hand: removing 50 is a typo, not a write-off — say so instead of silently zeroing the stock
        r = self.adjust('50', 'adjustment')
        self.assertEqual((r.status_code, r.content.decode()), (400, 'Only 10.00 kg on hand — you can’t take out 50.00.'))
        self.assertEqual(self.stock(), Decimal('10.00'))
        self.assertFalse(StockMovement.objects.exists())

    def test_taking_out_exactly_what_is_on_hand_empties_the_item(self):
        self.assertEqual(self.adjust('10', 'adjustment').status_code, 200)
        self.assertEqual(self.stock(), Decimal('0.00'))

    def test_a_bad_quantity_is_refused_with_a_message_and_changes_nothing(self):
        # The blank case is what pressing "+" with an empty box sends; it used to
        # just 400 with nothing shown. Every one of these must be a readable 400,
        # never a 500 (NaN/Infinity/1e30 used to be able to crash the view).
        cases = [
            ('', 'Enter a quantity first.'),
            ('   ', 'Enter a quantity first.'),
            ('abc', 'Enter a valid number.'),
            ('1,5', 'Enter a valid number.'),
            ('NaN', 'Enter a valid number.'),
            ('Infinity', 'Enter a valid number.'),
            ('0', 'Quantity must be greater than 0.'),
            ('-5', 'Quantity must be greater than 0.'),
            ('0.004', 'Quantity must be greater than 0.'),      # would round to a 0.00 movement
            ('1e30', 'That quantity is too large.'),
            ('99999999.99', 'That quantity is too large.'),     # 10 on hand + this overflows the 10-digit stock field
        ]
        for value, message in cases:
            with self.subTest(quantity=value):
                r = self.adjust(value)
                self.assertEqual(r.status_code, 400)
                self.assertEqual(r.content.decode(), message)
        self.assertEqual(self.stock(), Decimal('10.00'))
        self.assertFalse(StockMovement.objects.exists())

    def test_a_missing_quantity_field_is_treated_like_a_blank_one(self):
        self.client.force_login(self.staff)
        r = self.client.post(self.url(), {})
        self.assertEqual((r.status_code, r.content.decode()), (400, 'Enter a quantity first.'))

    def test_unknown_adjustment_type_is_refused(self):
        r = self.adjust('5', 'usage')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(StockMovement.objects.exists())

    def test_get_is_not_allowed(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_only_staff_can_adjust_stock(self):
        for user in (None, self.customer):
            with self.subTest(user=user):
                self.client.logout()
                if user:
                    self.client.force_login(user)
                r = self.client.post(self.url(), {'quantity': '5'})
                self.assertEqual(r.status_code, 302)                # bounced to the admin login
        self.assertEqual(self.stock(), Decimal('10.00'))
        self.assertFalse(StockMovement.objects.exists())

    def test_unknown_item_is_a_404(self):
        self.client.force_login(self.staff)
        r = self.client.post(reverse('htmx-adjust-stock', args=[999999]) + '?type=purchase', {'quantity': '5'})
        self.assertEqual(r.status_code, 404)

    def test_widget_asks_for_a_quantity_and_refocuses_the_box_on_error(self):
        from inventory.admin import render_quick_adjust
        html = render_quick_adjust(self.item)
        self.assertIn('placeholder="Qty"', html)
        self.assertIn('title="Quantity in kg"', html)
        self.assertEqual(html.count('hx-on::response-error='), 2)     # one per button

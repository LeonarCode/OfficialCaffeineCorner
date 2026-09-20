"""
Real-browser tests for the Inventory list's Quick Adjust widget (the "+" / "−"
next to each item's stock).

The bug these guard against: pressing "+" with the quantity box empty was
rejected by the server (400) — and HTMX shows nothing for a 4xx, so on screen
it simply looked like the button didn't work. Now the reason appears as a
message (static/js/htmx-feedback.js) and the cursor goes back to the box.

Skipped automatically when Playwright/Chromium isn't available (see
tests/support/browser_testing.py). Run just this file with:

    python manage.py test tests.test_inventory.test_quick_adjust_browser
"""
from decimal import Decimal

from django.contrib.sessions.models import Session

from inventory.models import Inventory, InventoryCategory
from tests.support import browser_testing


class QuickAdjustBrowserTests(browser_testing.AdminBrowserTestCase):
    def setUp(self):
        super().setUp()
        self.item = Inventory.objects.create(
            category=InventoryCategory.objects.create(name='Beans'), name='Espresso Beans', sku='BEAN-1',
            unit='kg', quantity_on_hand=Decimal('10'), reorder_points=Decimal('2'), cost_per_unit=Decimal('350'),
        )
        self.log_in_without_a_page()
        self.open_inventory_list()

    # ── helpers ───────────────────────────────────────────────────────────

    def open_inventory_list(self):
        self.page.goto(self.url('/admin/inventory/inventory/'))
        self.box().wait_for()

    def box(self):
        return self.page.locator(f'#qa-{self.item.pk} input')

    def stock_in(self):
        return self.page.locator(f'#qa-{self.item.pk} button[aria-label="Stock in"]')

    def stock_out(self):
        return self.page.locator(f'#qa-{self.item.pk} button[aria-label="Stock out"]')

    def press(self, button, quantity=None):
        """Type a quantity (unless None) and press a button; returns the server's response."""
        if quantity is not None:
            self.box().fill(quantity)
        with self.page.expect_response(lambda r: '/adjust/' in r.url) as response:
            button.click()
        return response.value

    def stock(self):
        self.item.refresh_from_db()
        return self.item.quantity_on_hand

    def toast(self):
        """The failure message shown on screen right now, or None."""
        toast = self.page.locator('#htmx-feedback-toast')
        return toast.inner_text() if toast.count() and toast.is_visible() else None

    def stock_cell(self):
        return self.page.locator(f'#stock-bar-{self.item.pk}')

    # ── it works, in place ────────────────────────────────────────────────

    def test_plus_adds_stock_and_updates_the_row_in_place(self):
        response = self.press(self.stock_in(), '5')
        self.assertEqual(response.status, 200)
        self.page.wait_for_selector(f'#stock-bar-{self.item.pk}:has-text("15.00")')      # the Stock Level cell, no reload
        self.assertEqual(self.stock(), Decimal('15.00'))
        self.assertEqual(self.box().input_value(), '')                                   # widget was reset
        self.assertIsNone(self.toast())

    def test_minus_removes_stock_and_updates_the_row_in_place(self):
        response = self.press(self.stock_out(), '3')
        self.assertEqual(response.status, 200)
        self.page.wait_for_selector(f'#stock-bar-{self.item.pk}:has-text("7.00")')
        self.assertEqual(self.stock(), Decimal('7.00'))

    # ── it fails out loud ─────────────────────────────────────────────────

    def test_pressing_plus_with_an_empty_box_explains_itself(self):
        # This is the exact request from the bug report: POST ...?type=purchase, quantity=""
        response = self.press(self.stock_in())
        self.assertEqual(response.status, 400)
        self.page.wait_for_selector('#htmx-feedback-toast')
        self.assertEqual(self.toast(), 'Enter a quantity first.')
        self.assertTrue(self.box().evaluate('el => el === document.activeElement'), 'the cursor should be back in the quantity box')
        self.assertEqual(self.stock(), Decimal('10.00'))

    def test_a_number_the_server_refuses_shows_the_servers_reason(self):
        self.assertEqual(self.press(self.stock_in(), '0').status, 400)
        self.page.wait_for_selector('#htmx-feedback-toast')
        self.assertEqual(self.toast(), 'Quantity must be greater than 0.')
        self.assertEqual(self.stock(), Decimal('10.00'))

    def test_a_good_press_after_a_bad_one_still_works(self):
        self.press(self.stock_in())                                     # bad: empty
        self.page.wait_for_selector('#htmx-feedback-toast')
        response = self.press(self.stock_in(), '5')                     # then fixed
        self.assertEqual(response.status, 200)
        self.assertEqual(self.stock(), Decimal('15.00'))

    # ── the other ways a press can go wrong ───────────────────────────────

    def test_works_on_a_page_left_open_across_a_login(self):
        self.make_open_pages_stale()
        self.assertEqual(self.press(self.stock_in(), '5').status, 200)
        self.assertEqual(self.stock(), Decimal('15.00'))

    def test_an_expired_session_sends_you_to_the_login_page_instead_of_breaking_the_row(self):
        Session.objects.all().delete()          # the server forgets the login; the browser still holds its cookies
        self.press(self.stock_in(), '5')
        self.page.wait_for_url('**/admin/login/**')
        self.assertIn('next=%2Fadmin%2Finventory%2Finventory%2F', self.page.url)     # ...and comes back to this list afterwards
        self.assertEqual(self.stock(), Decimal('10.00'))

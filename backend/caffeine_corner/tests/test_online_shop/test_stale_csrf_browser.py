"""
Real-browser regression tests for the admin's
"403 Forbidden — CSRF token from POST incorrect" bug.

Django rotates the CSRF cookie on every login, so an admin page that was
already open (another tab, or Back after a login) still holds the old token in
its hidden form field. Saving it used to fail even though the browser was
logged in with a perfectly good new cookie. static/js/htmx-csrf.js fixes that
by reading the cookie at submit time — and only a browser can prove it, since
it's JavaScript. Each test below opens a page, logs in again from a second tab
(that's what makes the first one stale), then submits the stale page the way a
person would, or the way a script might.

Skipped automatically when Playwright/Chromium isn't available (see
tests/support/browser_testing.py). Run just this file with:

    python manage.py test tests.test_online_shop.test_stale_csrf_browser
"""
from decimal import Decimal

from online_shop.models import Category, Order, OrderItem, Product
from tests.support import browser_testing


class StaleCsrfTokenBrowserTests(browser_testing.AdminBrowserTestCase):
    def setUp(self):
        super().setUp()
        category = Category.objects.create(name='Coffee')
        self.product = Product.objects.create(
            name='Latte', description='Latte', category=category, price=Decimal('100.00'),
            cost_price=Decimal('40.00'), sku='LAT-1', barcode='LAT-1',
        )
        for i in range(3):
            order = Order.objects.create(
                email=f'c{i}@example.com', phone='09171234567', order_type='dine_in',
                table_number='1', payment_method='counter',
            )
            OrderItem.objects.create(order=order, product=self.product, quantity=1, price=Decimal('100.00'))

    def assert_not_forbidden(self, navigation):
        self.assertNotEqual(
            navigation.value.status, 403,
            'the stale page was rejected with 403 — the CSRF token was not refreshed at submit time',
        )

    # ── the stale page is submitted in every way the admin can submit ─────

    def test_stale_change_form_still_saves(self):
        self.log_in_without_a_page()
        self.page.goto(self.url(f'/admin/online_shop/product/{self.product.pk}/change/'))
        self.make_open_pages_stale()

        self.page.fill('#id_price', '170.00')
        with self.page.expect_navigation() as nav:
            self.page.click('input[name="_save"], button[name="_save"]')
        self.assert_not_forbidden(nav)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal('170.00'))

    def test_stale_htmx_status_toggle_still_saves(self):
        self.log_in_without_a_page()
        self.page.goto(self.url('/admin/online_shop/order/'))
        self.make_open_pages_stale()

        with self.page.expect_response(lambda r: '/set-status/' in r.url) as response:
            self.page.locator('select[hx-post*="set-status"]').first.select_option('delivered')
        self.assertEqual(response.value.status, 200, 'the toggle POST was rejected (it used to fail silently)')
        self.assertEqual(Order.objects.filter(status='delivered').count(), 1)

    def test_stale_bulk_action_still_runs(self):
        self.log_in_without_a_page()
        self.page.goto(self.url('/admin/online_shop/order/'))
        self.make_open_pages_stale()

        self.page.locator('input.action-select').first.check()
        self.page.locator('select[name=action]').first.select_option('mark_confirmed')
        with self.page.expect_navigation() as nav:
            self.page.click('button[name=index]')
        self.assert_not_forbidden(nav)
        self.assertEqual(Order.objects.filter(status='confirmed').count(), 1)

    def test_stale_form_submitted_from_a_script_still_works(self):
        # form.submit() fires no `submit` event, so it needs its own hook
        self.log_in_without_a_page()
        self.page.goto(self.url('/admin/'))
        self.make_open_pages_stale()

        with self.page.expect_navigation() as nav:
            self.page.locator('form[action*="logout"]').first.evaluate('form => form.submit()')
        self.assert_not_forbidden(nav)

    def test_stale_login_page_still_logs_in(self):
        self.page.goto(self.url('/admin/login/?next=/admin/'))       # left open, not logged in yet
        self.make_open_pages_stale()                                 # someone logs in first

        self.page.fill('input[name=username]', 'admin@example.com')
        self.page.fill('input[name=password]', 'pw')
        with self.page.expect_navigation() as nav:
            self.page.click('button[type=submit]')
        self.assert_not_forbidden(nav)
        self.assertTrue(self.page.url.rstrip('/').endswith('/admin'), self.page.url)

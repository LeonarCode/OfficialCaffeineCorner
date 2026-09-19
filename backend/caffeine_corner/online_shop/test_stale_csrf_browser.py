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

Playwright is an optional dev dependency: without it (or without its Chromium
build: `playwright install chromium`) this whole module is skipped, and the
rest of the suite is unaffected. Run just this file with:

    python manage.py test online_shop.test_stale_csrf_browser
"""
import os
import unittest
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from online_shop.models import Category, Order, OrderItem, Product

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

User = get_user_model()


# PBKDF2 (Django's default) costs ~1.6 s per password check, and every test logs in
# a few times — a fast hasher keeps this file quick and changes nothing under test.
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
@unittest.skipIf(sync_playwright is None, 'playwright is not installed')
class StaleCsrfTokenBrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        # Playwright's sync API keeps an event loop running in this thread,
        # which trips Django's async-safety guard on the ORM calls the tests
        # make between browser steps.
        cls._env = mock.patch.dict(os.environ, {'DJANGO_ALLOW_ASYNC_UNSAFE': 'true'})
        cls._env.start()
        cls._pw = cls._browser = None
        try:
            cls._pw = sync_playwright().start()
            cls._browser = cls._pw.chromium.launch()
            super().setUpClass()
        except unittest.SkipTest:
            raise
        except Exception as exc:
            cls._release()
            if cls._browser is None:      # never got a browser: not this project's fault
                raise unittest.SkipTest(f'Playwright could not start Chromium ({exc}) — run: playwright install chromium')
            raise

    @classmethod
    def _release(cls):
        if cls._browser:
            cls._browser.close()
        if cls._pw:
            cls._pw.stop()
        cls._env.stop()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._release()

    def setUp(self):
        User.objects.create_superuser('admin@example.com', 'pw')
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

        self.context = self._browser.new_context(viewport={'width': 1500, 'height': 1000})
        # The admin pulls web fonts and the like from the internet; nothing
        # here needs them, and blocking them keeps the test fast and offline-safe.
        self.context.route('**/*', self._local_only)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()

    def _local_only(self, route):
        if route.request.url.startswith((self.live_server_url, 'data:')):
            route.continue_()
        else:
            route.abort()

    # ── helpers ───────────────────────────────────────────────────────────

    def url(self, path):
        return self.live_server_url + path

    def csrf_cookie(self):
        return next((c['value'] for c in self.context.cookies() if c['name'] == 'csrftoken'), None)

    def log_in_without_a_page(self):
        """
        Log in over plain HTTP, sharing the browser's cookies — no page loads,
        so it's quick. Like logging in from a second tab, it starts a new
        session and rotates the CSRF cookie, which is exactly what leaves every
        admin page opened before it stale.
        """
        http, login_url = self.context.request, self.url('/admin/login/')
        http.get(login_url)                              # makes sure there is a csrftoken cookie to send back
        token = self.csrf_cookie()
        self.assertIsNotNone(token, 'setup problem: the login page did not set a CSRF cookie')
        response = http.post(login_url, form={
            'username': 'admin@example.com', 'password': 'pw', 'csrfmiddlewaretoken': token,
        })
        self.assertTrue(response.ok, f'setup problem: logging in failed ({response.status})')

    def make_open_pages_stale(self):
        before = self.csrf_cookie()
        self.log_in_without_a_page()
        self.assertNotEqual(
            self.csrf_cookie(), before,
            'setup problem: logging in again should have rotated the CSRF cookie, so nothing is stale',
        )

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

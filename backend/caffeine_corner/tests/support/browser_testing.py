"""
Shared plumbing for the real-browser (Playwright) tests of the admin — the ones
that have to run the admin's JavaScript to mean anything:

    tests/test_online_shop/test_stale_csrf_browser.py   stale CSRF tokens after a re-login
    tests/test_inventory/test_quick_adjust_browser.py   the Quick Adjust +/- widget
    tests/test_inventory/test_purchasing_browser.py     Purchase Orders and the item page

Playwright is an optional dev dependency: without it (or without its Chromium
build: `playwright install chromium`) every test built on this base is skipped
and the rest of the suite is unaffected.

Import the module, not the class, from a test module
(`from tests.support import browser_testing`): the test loader collects every
TestCase class in a module's namespace, and this base has no tests of its own.
"""
import os
import unittest
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

User = get_user_model()


# PBKDF2 (Django's default) costs ~1.6 s per password check, and every test logs in
# a few times — a fast hasher keeps these quick and changes nothing under test.
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
@unittest.skipIf(sync_playwright is None, 'playwright is not installed')
class AdminBrowserTestCase(StaticLiveServerTestCase):
    """A live server, a Chromium, and a superuser (admin@example.com / pw)."""

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
        self.context = self._browser.new_context(viewport={'width': 1500, 'height': 1000})
        # The admin pulls web fonts and the like from the internet; nothing
        # here needs them, and blocking them keeps the tests fast and offline-safe.
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

"""The admin's JavaScript helpers (CSRF refresh, failure messages), login redirect, and their guards."""
import os
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string

from online_shop.models import Category, Order, Product

User = get_user_model()


class AdminLoginAndCsrfTests(TestCase):
    """
    Django rotates the CSRF cookie on every login, so an admin page that was
    already open (another tab, or Back after a login) holds a stale token.
    static/js/htmx-csrf.js re-reads the cookie at submit time to cope with
    that (checked in a real browser); what's pinned down here is the server
    side it relies on — and that CSRF is still enforced.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin@example.com', 'pw')
        cls.order = Order.objects.create(
            email='c@example.com', phone='09171234567', order_type='dine_in',
            table_number='1', payment_method='counter',
        )

    def toggle_url(self):
        return reverse('htmx-order-status', args=[self.order.pk])

    def test_direct_login_lands_on_the_admin_not_a_404(self):
        # Unfold's login form has no hidden "next", so this used to go to /accounts/profile/
        r = self.client.post(reverse('admin:login'), {'username': 'admin@example.com', 'password': 'pw'})
        self.assertRedirects(r, reverse('admin:index'), fetch_redirect_response=False)

    def test_login_still_honours_an_explicit_next(self):
        r = self.client.post(
            reverse('admin:login') + '?next=/admin/online_shop/order/',
            {'username': 'admin@example.com', 'password': 'pw'},
        )
        self.assertRedirects(r, '/admin/online_shop/order/', fetch_redirect_response=False)

    def test_csrf_is_still_enforced_on_admin_posts(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.toggle_url(), {'status': 'confirmed'}).status_code, 403)   # no token
        client.cookies['csrftoken'] = get_random_string(32)
        r = client.post(self.toggle_url(), {'status': 'confirmed', 'csrfmiddlewaretoken': get_random_string(32)})
        self.assertEqual(r.status_code, 403)                                                          # wrong token
        self.assertEqual(Order.objects.get(pk=self.order.pk).status, 'pending')

    def test_the_cookie_value_is_accepted_as_form_field_or_header(self):
        # exactly what htmx-csrf.js sends: the csrftoken cookie's own value
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        secret = get_random_string(32)
        client.cookies['csrftoken'] = secret
        self.assertEqual(client.post(self.toggle_url(), {'status': 'confirmed', 'csrfmiddlewaretoken': secret}).status_code, 200)
        self.assertEqual(client.post(self.toggle_url(), {'status': 'delivered'}, HTTP_X_CSRFTOKEN=secret).status_code, 200)
        self.assertEqual(Order.objects.get(pk=self.order.pk).status, 'delivered')


class CsrfScriptGuardTests(TestCase):
    """
    The stale-token fix lives in static/js/htmx-csrf.js. If that script stops
    being loaded, or loses one of its hooks, the "403 CSRF token from POST
    incorrect" comes straight back — so these trip on exactly that. What the
    script actually *does* is checked in a real browser
    (tests/test_online_shop/test_stale_csrf_browser.py); these are the fast, always-on
    part that needs no browser.
    """

    SCRIPT = 'js/htmx-csrf.js?v='        # loaded through _versioned_static() in settings

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin@example.com', 'pw')
        cls.product = Product.objects.create(
            name='Latte', description='Latte', category=Category.objects.create(name='Coffee'),
            price=Decimal('100.00'), cost_price=Decimal('40.00'), sku='LAT-1', barcode='LAT-1',
        )

    def test_script_is_loaded_on_the_login_page(self):
        self.assertContains(self.client.get(reverse('admin:login')), self.SCRIPT)

    def test_script_is_loaded_on_every_admin_page_that_posts(self):
        self.client.force_login(self.admin)
        pages = [
            reverse('admin:index'),
            reverse('admin:online_shop_order_changelist'),        # HTMX toggles + bulk-action form
            reverse('admin:online_shop_order_add'),
            reverse('admin:online_shop_product_changelist'),
            reverse('admin:online_shop_product_change', args=[self.product.pk]),
            reverse('sales-report'),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), self.SCRIPT)

    def test_script_keeps_the_hooks_that_fix_the_403(self):
        source = open(finders.find('js/htmx-csrf.js'), encoding='utf-8').read()
        for needle in (
            'htmx:configRequest',                # HTMX requests (status/payment toggles, bell)
            "'submit'",                          # normal forms: button click / Enter
            'HTMLFormElement.prototype.submit',  # form.submit() called from a script
            'csrfmiddlewaretoken',               # the hidden field that goes stale
            'csrftoken',                         # the cookie the fresh value is read from
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, source)

    def test_script_url_changes_when_the_file_changes(self):
        # otherwise a browser can keep running a cached, pre-fix copy
        from caffeine_corner.settings import _versioned_static
        url = _versioned_static('js/htmx-csrf.js')
        with mock.patch.object(os.path, 'getmtime', return_value=111):
            first = url(None)
        with mock.patch.object(os.path, 'getmtime', return_value=222):
            second = url(None)
        self.assertTrue(first.endswith('js/htmx-csrf.js?v=111'), first)
        self.assertTrue(second.endswith('js/htmx-csrf.js?v=222'), second)


class FeedbackScriptGuardTests(TestCase):
    """
    static/js/htmx-feedback.js is what turns a rejected admin action (bad
    input on an htmx POST) into a visible message, and what stops an expired
    session from pasting the login page into a table cell. If it stops
    loading, both go back to failing silently. What follows is the fast,
    always-on guard that it keeps working; there is no dedicated browser
    test of the toast itself right now.
    """

    SCRIPT = 'js/htmx-feedback.js?v='

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin@example.com', 'pw')

    def test_script_is_loaded_on_the_admin_pages_that_use_htmx(self):
        self.client.force_login(self.admin)
        pages = [
            reverse('admin:index'),
            reverse('admin:inventory_inventory_changelist'),
            reverse('admin:online_shop_order_changelist'),       # status / payment toggles
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), self.SCRIPT)

    def test_script_keeps_its_hooks(self):
        source = open(finders.find('js/htmx-feedback.js'), encoding='utf-8').read()
        for needle in ('htmx:responseError', 'htmx:sendError', 'htmx:beforeSwap'):
            with self.subTest(needle=needle):
                self.assertIn(needle, source)

    def test_script_never_writes_server_text_as_html(self):
        # the toast shows text that came from a server response — textContent only
        source = open(finders.find('js/htmx-feedback.js'), encoding='utf-8').read()
        self.assertIn('textContent', source)
        self.assertNotIn('innerHTML', source)


class AdminThemeCssGuardTests(TestCase):
    """
    static/css/admin-theme.css is what keeps the header/sidebar on-brand and
    its buttons readable (see the long comments in that file for exactly
    which bugs those rules fix). It used to be loaded plainly — an edit to it
    changed nothing for anyone still running a cached copy, which is exactly
    how a fixed bug (unreadable header buttons) kept being reported as still
    broken. It must go through _versioned_static() like every other admin
    asset, so a fix actually reaches people the moment it's deployed.
    """

    STYLE = 'css/admin-theme.css?v='

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin@example.com', 'pw')

    def test_stylesheet_is_loaded_with_a_cache_busting_version(self):
        self.assertContains(self.client.get(reverse('admin:login')), self.STYLE)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('admin:index')), self.STYLE)

    def test_stylesheet_url_changes_when_the_file_changes(self):
        # otherwise a browser can keep running a cached, pre-fix copy — see class docstring
        from caffeine_corner.settings import _versioned_static
        url = _versioned_static('css/admin-theme.css')
        with mock.patch.object(os.path, 'getmtime', return_value=111):
            first = url(None)
        with mock.patch.object(os.path, 'getmtime', return_value=222):
            second = url(None)
        self.assertTrue(first.endswith('css/admin-theme.css?v=111'), first)
        self.assertTrue(second.endswith('css/admin-theme.css?v=222'), second)

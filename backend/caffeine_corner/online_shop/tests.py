from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string

from online_shop.admin import PRICE_CHANGE_NOTE
from online_shop.models import Category, Order, OrderItem, Product, Variant

User = get_user_model()


def admin_post_data(response, **overrides):
    """
    The POST a browser would send back for the admin change form in `response`
    (main form + inline formsets, as currently displayed), with `overrides`
    applied on top — so a test edits one field the way staff would, not by
    hand-building every management-form key.
    """
    data = {}

    def take(form):
        prefix = f'{form.prefix}-' if form.prefix else ''
        for name in form.fields:
            value = form[name].value()
            if value is None or value is False or value == '':
                continue
            data[f'{prefix}{name}'] = 'on' if value is True else value

    ctx = response.context
    take(ctx['adminform'].form)
    for inline in ctx['inline_admin_formsets']:
        formset = inline.formset
        for key, value in formset.management_form.initial.items():
            data[f'{formset.prefix}-{key}'] = value
        for form in formset.forms:
            take(form)
    data.update(overrides)
    return data


class PriceChangeDoesNotTouchPlacedOrdersTests(TestCase):
    """
    Order lines carry their own copy of the price (OrderItem.price), taken when
    the order is placed. Changing a Product/Variant price afterwards — the way
    staff really do it, through the admin form — must only affect new orders.

    Before: Latte 100 + Large +20 = 120 each.   After: Latte 150 + Large +35 = 185.
    """

    OLD_LINE, NEW_LINE = Decimal('120.00'), Decimal('185.00')

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin@example.com', 'pw')
        category = Category.objects.create(name='Coffee')
        cls.latte = Product.objects.create(
            name='Latte', description='Latte', category=category, price=Decimal('100.00'),
            cost_price=Decimal('40.00'), sku='LAT-1', barcode='LAT-1',
        )
        cls.large = Variant.objects.create(product=cls.latte, size='large', additional_price=Decimal('20.00'))

    def setUp(self):
        self.order = self.place_order(quantity=2)

    def place_order(self, quantity):
        r = self.client.post(reverse('order-create'), {
            'email': 'buyer@example.com', 'phone': '09171234567',
            'payment_method': 'counter', 'order_type': 'pickup',
            'items': [{'product': self.latte.pk, 'variant': self.large.pk, 'quantity': quantity}],
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        return Order.objects.get(pk=r.json()['id'])

    def reprice_in_admin(self):
        """Edit the Product page like staff would: new base price and new Large add-on."""
        self.client.force_login(self.admin)
        url = reverse('admin:online_shop_product_change', args=[self.latte.pk])
        data = admin_post_data(
            self.client.get(url),
            price='150.00',
            **{'variants-0-additional_price': '35.00'},
        )
        r = self.client.post(url, data)
        self.assertEqual(r.status_code, 302, 'the product form should save cleanly')
        self.client.logout()
        self.latte.refresh_from_db()
        self.large.refresh_from_db()
        self.assertEqual(self.latte.price, Decimal('150.00'))              # the edit really happened
        self.assertEqual(self.large.additional_price, Decimal('35.00'))

    def test_placed_order_kept_the_price_it_was_ordered_at(self):
        self.assertEqual(self.order.items.get().price, self.OLD_LINE)      # snapshot taken at order time

    def test_price_change_leaves_a_placed_order_unchanged_everywhere(self):
        self.reprice_in_admin()

        item = OrderItem.objects.get(order=self.order)
        self.assertEqual(item.price, self.OLD_LINE)
        order = Order.objects.get(pk=self.order.pk)
        self.assertEqual(order.subtotal, Decimal('240.00'))
        self.assertEqual(order.total_price, Decimal('240.00'))

        # customer-facing API
        data = self.client.get(reverse('order-detail', args=[order.pk])).json()
        self.assertEqual(data['items'][0]['price'], '120.00')
        self.assertEqual(data['items'][0]['subtotal'], '240.00')
        self.assertEqual((data['subtotal'], data['total_price']), ('240.00', '240.00'))

        # staff-facing pages
        self.client.force_login(self.admin)
        receipt = self.client.get(reverse('print-receipt', args=[order.pk]))
        self.assertContains(receipt, '2 x ₱120.00')
        self.assertNotContains(receipt, '185.00')
        change_page = self.client.get(reverse('admin:online_shop_order_change', args=[order.pk]))
        self.assertContains(change_page, '120.00')
        self.assertNotContains(change_page, '185.00')

    def test_new_orders_use_the_new_price(self):
        self.reprice_in_admin()
        newer = self.place_order(quantity=1)
        self.assertEqual(newer.items.get().price, self.NEW_LINE)
        self.assertEqual(OrderItem.objects.get(order=self.order).price, self.OLD_LINE)

        # and the admin's Add Order price auto-fill offers the current price, too
        self.client.force_login(self.admin)
        r = self.client.get(reverse('order-item-price', args=[self.latte.pk]), {'variant': self.large.pk})
        self.assertEqual(r.json(), {'price': '185.00'})

    def test_working_on_a_placed_order_later_does_not_reprice_it(self):
        self.reprice_in_admin()
        rider = User.objects.create_user('rider@example.com', 'pw', is_rider=True)
        self.client.force_login(self.admin)
        url = reverse('admin:online_shop_order_change', args=[self.order.pk])
        response = self.client.get(url)

        # the line items' price isn't an editable field on an existing order at all…
        line_form = response.context['inline_admin_formsets'][0].formset.forms[0]
        self.assertNotIn('price', line_form.fields)

        # …saving the order form (assigning a rider is its one editable field)…
        r = self.client.post(url, admin_post_data(response, assigned_rider=rider.pk))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Order.objects.get(pk=self.order.pk).assigned_rider, rider)   # the save really went through

        # …and moving it along from the Orders list (the HTMX status control)
        r = self.client.post(reverse('htmx-order-status', args=[self.order.pk]), {'status': 'confirmed'})
        self.assertEqual(r.status_code, 200)

        order = Order.objects.get(pk=self.order.pk)
        self.assertEqual(order.status, 'confirmed')
        self.assertEqual(order.items.get().price, self.OLD_LINE)
        self.assertEqual(order.total_price, Decimal('240.00'))

    def test_product_page_tells_staff_price_changes_only_affect_new_orders(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse('admin:online_shop_product_change', args=[self.latte.pk]))
        self.assertContains(page, PRICE_CHANGE_NOTE, count=2)              # base price + the variant add-on row


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

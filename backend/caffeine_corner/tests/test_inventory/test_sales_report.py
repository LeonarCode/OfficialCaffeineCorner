"""The Sales Report: the numbers, the performance record, the parameters, the pages and the PDF."""
import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from inventory.sales_report import MAX_SPAN_DAYS, MIN_DATE, build_sales_report, parse_report_params
from online_shop.models import Category, Order, OrderItem, Product, Rating, TownZone

User = get_user_model()
UTC = datetime.timezone.utc


def at(y, m, d, hour=12):
    return datetime.datetime(y, m, d, hour, 0, tzinfo=UTC)


class SalesReportFixture(TestCase):
    """
    Range under test: Sep 1 – Sep 10, 2026 (Sep 1 is a Tuesday).
    Previous period of the same length: Aug 22 – Aug 31.

    In range (E is cancelled, so it must not count anywhere):
      A  Sep 2  dine-in   Latte x2                       -> 200
      B  Sep 2  dine-in   Cake x1                        ->  50
      C  Sep 3  pickup    Latte x1 + Cake x2, discount 10-> 200
      D  Sep 5  delivery  Latte x3 + Cake x1, fee 40     -> 350  (two items: a
                                                            naive join would double the fee)
      E  Sep 5  delivery  Latte x10  CANCELLED           -> (1000 if wrongly counted)
      F  Sep 9  dine-in   Cake x4                        -> 200
    Previous period:
      G  Aug 25 dine-in   Latte x1 -> 100
      H  Aug 28 delivery  Latte x1 -> 100, fee 30
    """

    D_FROM = datetime.date(2026, 9, 1)
    D_TO = datetime.date(2026, 9, 10)

    @classmethod
    def setUpTestData(cls):
        cat_coffee = Category.objects.create(name='Coffee')
        cat_pastry = Category.objects.create(name='Pastry')

        def product(name, category, price, sku):
            return Product.objects.create(
                name=name, description=name, category=category, price=Decimal(price),
                cost_price=Decimal('10'), sku=sku, barcode=sku,
            )

        cls.latte = product('Latte', cat_coffee, '100', 'LAT-1')
        cls.cake = product('Cake', cat_pastry, '50', 'CAK-1')

        def order(when, order_type, lines, status='delivered', fee='0', discount='0', payment='cod'):
            o = Order.objects.create(
                email='c@example.com', phone='09171234567', order_type=order_type,
                status=status, payment_method=payment, delivery_fee=Decimal(fee),
                discount=Decimal(discount),
            )
            for prod, qty in lines:
                OrderItem.objects.create(order=o, product=prod, quantity=qty, price=prod.price)
            # created_at is auto_now_add; a queryset update bypasses it
            Order.objects.filter(pk=o.pk).update(created_at=when)
            return o

        cls.a = order(at(2026, 9, 2), 'dine_in', [(cls.latte, 2)])
        cls.b = order(at(2026, 9, 2), 'dine_in', [(cls.cake, 1)], status='pending', payment='counter')
        cls.c = order(at(2026, 9, 3), 'pickup', [(cls.latte, 1), (cls.cake, 2)], status='confirmed', discount='10')
        cls.d = order(at(2026, 9, 5), 'regular', [(cls.latte, 3), (cls.cake, 1)], fee='40', payment='gcash')
        cls.e = order(at(2026, 9, 5), 'regular', [(cls.latte, 10)], status='cancelled')
        cls.f = order(at(2026, 9, 9), 'dine_in', [(cls.cake, 4)], payment='counter')
        cls.g = order(at(2026, 8, 25), 'dine_in', [(cls.latte, 1)])
        cls.h = order(at(2026, 8, 28), 'regular', [(cls.latte, 1)], fee='30')

    def report(self, granularity='daily', order_type='', d_from=None, d_to=None):
        return build_sales_report(d_from or self.D_FROM, d_to or self.D_TO, granularity, order_type)


class SalesReportNumbersTests(SalesReportFixture):
    def test_headline_excludes_cancelled_orders(self):
        s = self.report()['summary']
        self.assertEqual(s['orders'], 5)          # not 6
        self.assertEqual(s['sales'], 1000.0)      # not 2000
        self.assertEqual(s['items'], 14)
        self.assertEqual(s['avg_order'], 200.0)
        self.assertEqual(s['cancelled_orders'], 1)

    def test_delivery_fee_is_not_multiplied_by_item_rows(self):
        s = self.report()['summary']
        self.assertEqual(s['delivery_fees'], 40.0)   # order D has two items
        self.assertEqual(s['discounts'], 10.0)
        self.assertEqual(s['collected'], 1030.0)     # sales - discounts + fees

    def test_grouped_by_order_type(self):
        by_type = {t['key']: t for t in self.report()['by_type']}
        self.assertEqual(list(by_type), ['dine_in', 'pickup', 'regular'])
        self.assertEqual((by_type['dine_in']['orders'], by_type['dine_in']['sales'], by_type['dine_in']['items']), (3, 450.0, 7))
        self.assertEqual((by_type['pickup']['orders'], by_type['pickup']['sales'], by_type['pickup']['items']), (1, 200.0, 3))
        self.assertEqual((by_type['regular']['orders'], by_type['regular']['sales'], by_type['regular']['items']), (1, 350.0, 4))
        self.assertEqual(by_type['regular']['label'], 'Delivery')
        self.assertEqual(by_type['regular']['delivery_fees'], 40.0)
        self.assertEqual([by_type[k]['share_pct'] for k in ('dine_in', 'pickup', 'regular')], [45.0, 20.0, 35.0])

    def test_types_add_up_to_the_headline(self):
        r = self.report()
        self.assertEqual(sum(t['sales'] for t in r['by_type']), r['summary']['sales'])
        self.assertEqual(sum(t['orders'] for t in r['by_type']), r['summary']['orders'])
        self.assertEqual(sum(row['sales'] for row in r['series']), r['summary']['sales'])
        self.assertEqual(sum(p['total_revenue'] for p in r['product_performance']), r['summary']['sales'])
        self.assertEqual(sum(c['sales'] for c in r['categories']), r['summary']['sales'])
        self.assertEqual(sum(p['sales'] for p in r['payment_methods']), r['summary']['sales'])

    def test_top_products_per_type(self):
        by_type = {t['key']: t for t in self.report()['by_type']}
        # Pickup: Latte x1 and Cake x2 are both ₱100 — a tie, broken by units sold (2 beats 1)
        self.assertEqual([(p['name'], p['sales'], p['qty']) for p in by_type['pickup']['top_products']],
                         [('Cake', 100.0, 2), ('Latte', 100.0, 1)])
        self.assertEqual(by_type['dine_in']['top_products'][0], {'name': 'Cake', 'category': 'Pastry', 'qty': 5, 'sales': 250.0})
        self.assertEqual(by_type['regular']['top_products'][0]['name'], 'Latte')

    def test_ratings_do_not_inflate_sales_or_quantities(self):
        for i in range(3):
            Rating.objects.create(product=self.latte, user=User.objects.create_user(f'r{i}@example.com', 'pw'), rating=[5, 4, 4][i])
        perf = {p['name']: p for p in self.report()['product_performance']}
        self.assertEqual(perf['Latte']['total_sold'], 6)         # 2 + 1 + 3, not multiplied by 3 ratings
        self.assertEqual(perf['Latte']['total_revenue'], 600.0)
        self.assertEqual(perf['Latte']['avg_rating'], 4.3)
        self.assertIsNone(perf['Cake']['avg_rating'])
        self.assertEqual(perf['Cake']['total_revenue'], 400.0)
        self.assertEqual(self.report()['summary']['sales'], 1000.0)

    def test_comparison_with_previous_period(self):
        r = self.report()
        self.assertEqual((r['meta']['previous_from'], r['meta']['previous_to']), ('2026-08-22', '2026-08-31'))
        self.assertEqual(r['previous']['sales'], 200.0)
        self.assertEqual(r['previous']['orders'], 2)
        self.assertEqual(r['comparison']['sales'], 400.0)       # 200 -> 1000
        self.assertEqual(r['comparison']['orders'], 150.0)      # 2 -> 5
        by_type = {t['key']: t for t in r['by_type']}
        self.assertEqual(by_type['dine_in']['change_pct'], 350.0)   # 100 -> 450
        self.assertIsNone(by_type['pickup']['change_pct'])          # nothing last period to compare to

    def test_order_type_filter(self):
        r = self.report(order_type='dine_in')
        self.assertEqual((r['summary']['orders'], r['summary']['sales']), (3, 450.0))
        self.assertEqual([t['key'] for t in r['by_type']], ['dine_in'])
        self.assertEqual(r['previous']['sales'], 100.0)         # the filter applies to the comparison too
        self.assertEqual(r['meta']['order_type_label'], 'Dine-in')
        self.assertEqual(sum(row['sales'] for row in r['series']), 450.0)

    def test_status_breakdown_still_shows_cancelled(self):
        counts = {s['status']: s['count'] for s in self.report()['status']}
        self.assertEqual(counts, {'pending': 1, 'confirmed': 1, 'delivered': 3, 'cancelled': 1})

    def test_payment_method_split(self):
        pay = {p['method']: p for p in self.report()['payment_methods']}
        self.assertEqual((pay['cod']['orders'], pay['cod']['sales']), (2, 400.0))
        self.assertEqual((pay['gcash']['orders'], pay['gcash']['sales']), (1, 350.0))
        self.assertEqual((pay['counter']['orders'], pay['counter']['sales']), (2, 250.0))

    def test_empty_range_is_all_zeros_not_an_error(self):
        r = self.report(d_from=datetime.date(2026, 1, 1), d_to=datetime.date(2026, 1, 5))
        self.assertEqual((r['summary']['orders'], r['summary']['sales'], r['summary']['avg_order']), (0, 0.0, 0.0))
        self.assertEqual(len(r['series']), 5)
        self.assertTrue(all(row['sales'] == 0 for row in r['series']))
        self.assertFalse(any(row['is_best'] for row in r['series']))
        self.assertEqual([t['share_pct'] for t in r['by_type']], [0.0, 0.0, 0.0])
        self.assertIsNone(r['comparison']['sales'])


class PerformanceRecordTests(SalesReportFixture):
    def test_daily_record_includes_quiet_days(self):
        series = self.report('daily')['series']
        self.assertEqual(len(series), 10)
        self.assertEqual([row['key'] for row in series][:3], ['2026-09-01', '2026-09-02', '2026-09-03'])
        self.assertEqual([row['sales'] for row in series], [0, 250, 200, 0, 350, 0, 0, 0, 200, 0])
        self.assertEqual([row['orders'] for row in series], [0, 2, 1, 0, 1, 0, 0, 0, 1, 0])
        self.assertEqual(series[1]['weekday'], 'Wed')

    def test_change_vs_previous_row_and_best_period(self):
        series = self.report('daily')['series']
        self.assertIsNone(series[0]['change_pct'])
        self.assertIsNone(series[1]['change_pct'])          # previous day had 0 sales: nothing to compare
        self.assertEqual(series[2]['change_pct'], -20.0)    # 250 -> 200
        self.assertEqual([row['key'] for row in series if row['is_best']], ['2026-09-05'])

    def test_per_type_sales_in_each_row(self):
        row = self.report('daily')['series'][4]     # Sep 5 — only the delivery order
        self.assertEqual(row['by_type'], {'dine_in': 0.0, 'pickup': 0.0, 'regular': 350.0})

    def test_weekly_buckets_start_on_monday_and_are_clipped_to_the_range(self):
        series = self.report('weekly')['series']
        self.assertEqual([row['key'] for row in series], ['2026-08-31', '2026-09-07'])
        self.assertEqual([row['sales'] for row in series], [800, 200])
        self.assertEqual([row['label'] for row in series], ['Sep 1 – Sep 6', 'Sep 7 – Sep 10'])

    def test_monthly_bucket(self):
        series = self.report('monthly')['series']
        self.assertEqual([(row['label'], row['sales'], row['orders']) for row in series], [('Sep 2026', 1000, 5)])

    def test_monthly_across_a_year_boundary_has_no_gaps(self):
        r = self.report('monthly', d_from=datetime.date(2025, 11, 20), d_to=datetime.date(2026, 2, 3))
        self.assertEqual([row['label'] for row in r['series']], ['Nov 2025', 'Dec 2025', 'Jan 2026', 'Feb 2026'])

    @override_settings(TIME_ZONE='Asia/Manila')
    def test_days_follow_the_projects_timezone(self):
        # 17:00 UTC on Sep 14 is already 01:00 on Sep 15 in Manila
        o = Order.objects.create(email='tz@example.com', phone='09171234567', order_type='dine_in',
                                 status='delivered', payment_method='counter')
        OrderItem.objects.create(order=o, product=self.cake, quantity=1, price=self.cake.price)
        Order.objects.filter(pk=o.pk).update(created_at=at(2026, 9, 14, 17))
        day = datetime.date(2026, 9, 15)
        r = build_sales_report(day, day, 'daily')
        self.assertEqual((r['summary']['orders'], r['summary']['sales']), (1, 50.0))
        self.assertEqual(r['series'][0]['sales'], 50.0)
        self.assertEqual(build_sales_report(datetime.date(2026, 9, 14), datetime.date(2026, 9, 14), 'daily')['summary']['orders'], 0)


class ParseParamsTests(TestCase):
    TODAY = datetime.date(2026, 9, 19)

    def parse(self, **params):
        return parse_report_params(params, today=self.TODAY)

    def test_defaults_to_the_last_30_days(self):
        p = self.parse()
        self.assertEqual((p.date_from, p.date_to), (datetime.date(2026, 8, 21), self.TODAY))
        self.assertEqual((p.granularity, p.granularity_choice, p.order_type), ('daily', 'auto', ''))

    def test_swapped_dates_are_put_in_order(self):
        p = self.parse(date_from='2026-09-10', date_to='2026-09-01')
        self.assertEqual((p.date_from, p.date_to), (datetime.date(2026, 9, 1), datetime.date(2026, 9, 10)))

    def test_garbage_falls_back_instead_of_raising(self):
        p = self.parse(date_from='not-a-date', date_to='2026-13-45', granularity='hourly', order_type='bulk')
        self.assertEqual((p.date_from, p.date_to), (datetime.date(2026, 8, 21), self.TODAY))
        self.assertEqual((p.granularity_choice, p.order_type), ('auto', ''))

    def test_future_end_date_is_clamped_to_today(self):
        p = self.parse(date_from='2026-09-15', date_to='2099-01-01')
        self.assertEqual((p.date_from, p.date_to), (datetime.date(2026, 9, 15), self.TODAY))

    def test_a_range_entirely_in_the_future_collapses_to_today(self):
        p = self.parse(date_from='2030-01-01', date_to='2030-02-01')
        self.assertEqual((p.date_from, p.date_to), (self.TODAY, self.TODAY))

    def test_absurd_ranges_are_bounded(self):
        p = self.parse(date_from='0001-01-01', date_to='9999-12-31')
        self.assertEqual(p.date_to, self.TODAY)
        self.assertEqual((p.date_to - p.date_from).days + 1, MAX_SPAN_DAYS)
        self.assertGreaterEqual(p.date_from, MIN_DATE)
        self.assertEqual(p.granularity, 'monthly')

    def test_granularity_auto_thresholds(self):
        def gran(days, **extra):
            return self.parse(date_from=(self.TODAY - datetime.timedelta(days=days - 1)).isoformat(), **extra).granularity
        self.assertEqual(gran(31), 'daily')
        self.assertEqual(gran(32), 'weekly')
        self.assertEqual(gran(180), 'weekly')
        self.assertEqual(gran(181), 'monthly')

    def test_explicit_granularity_is_honoured_but_daily_is_capped(self):
        start = (self.TODAY - datetime.timedelta(days=59)).isoformat()
        self.assertEqual(self.parse(date_from=start, granularity='daily').granularity, 'daily')
        self.assertEqual(self.parse(date_from=start, granularity='monthly').granularity, 'monthly')
        long_start = (self.TODAY - datetime.timedelta(days=499)).isoformat()
        p = self.parse(date_from=long_start, granularity='daily')
        self.assertEqual((p.granularity, p.granularity_choice), ('weekly', 'daily'))

    def test_valid_order_type_is_kept(self):
        self.assertEqual(self.parse(order_type='pickup').order_type, 'pickup')


class SalesReportViewTests(SalesReportFixture):
    DATA_URL = '/admin/sales-report/data/'
    QUERY = {'date_from': '2026-09-01', 'date_to': '2026-09-10', 'granularity': 'daily'}

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.staff = User.objects.create_user('staff@example.com', 'pw', is_staff=True)
        cls.customer = User.objects.create_user('customer@example.com', 'pw')

    def test_data_feed_requires_staff(self):
        r = self.client.get(self.DATA_URL, self.QUERY)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/admin/login/', r['Location'])

        self.client.force_login(self.customer)     # a logged-in customer is still not staff
        r = self.client.get(self.DATA_URL, self.QUERY)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/admin/login/', r['Location'])

    def test_old_customer_readable_api_is_gone(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get('/api/reports/sales/').status_code, 404)

    def test_data_feed_for_staff(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.DATA_URL, {**self.QUERY, 'order_type': 'pickup'})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual((data['summary']['orders'], data['summary']['sales']), (1, 200.0))
        self.assertEqual(data['meta']['order_type'], 'pickup')
        self.assertEqual(data['meta']['granularity'], 'daily')
        self.assertEqual(len(data['series']), 10)

    def test_data_feed_survives_hostile_params(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.DATA_URL, {'date_from': '0001-01-01', 'date_to': '9999-99-99', 'order_type': "x'; DROP TABLE--", 'granularity': '<b>'})
        self.assertEqual(r.status_code, 200)

    def test_report_page_renders(self):
        self.client.force_login(self.staff)
        r = self.client.get('/admin/sales-report/', self.QUERY)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Sales Report')

    def test_pdf_document_has_the_grouped_sections(self):
        self.client.force_login(self.staff)
        r = self.client.get('/admin/sales-report/document/', self.QUERY)
        self.assertEqual(r.status_code, 200)
        for text in ('Sales by Order Type', 'Performance Record', 'Dine-in', 'Pick-up', 'Delivery', '₱1,000.00', 'Delivery Fee Summary'):
            self.assertContains(r, text)
        # cancelled order E (Latte x10 = ₱1,000) must not leak into the log
        self.assertNotContains(r, '₱2,000.00')

    PDF_URL = '/admin/sales-report/document/'

    def test_pdf_item_log_is_on_by_default_for_a_short_range(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.PDF_URL, self.QUERY)          # 10 days
        self.assertContains(r, 'Detailed Transaction Log')
        self.assertContains(r, 'GRAND TOTAL')

    def test_pdf_item_log_is_off_by_default_for_a_long_range(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.PDF_URL, {'date_from': '2026-06-01', 'date_to': '2026-09-10'})   # 102 days
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'Detailed Transaction Log')
        self.assertContains(r, 'Sales by Order Type')          # the summary sections are still there
        self.assertContains(r, 'Performance Record')

    def test_pdf_item_log_can_be_toggled_either_way(self):
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get(self.PDF_URL, {**self.QUERY, 'log': '0'}), 'Detailed Transaction Log')
        long_range = {'date_from': '2026-06-01', 'date_to': '2026-09-10', 'log': '1'}
        self.assertContains(self.client.get(self.PDF_URL, long_range), 'Detailed Transaction Log')

    def test_pdf_toolbar_form_sends_zero_when_the_box_is_unticked(self):
        # the hidden log=0 comes first, the checkbox's log=1 after it — the last value wins
        self.client.force_login(self.staff)
        r = self.client.get(self.PDF_URL, {**self.QUERY, 'log': ['0', '1']})
        self.assertContains(r, 'Detailed Transaction Log')
        self.assertContains(r, 'checked')

    def test_pdf_delivery_fees_by_zone_with_the_order_listing_only_when_detailed(self):
        zone = TownZone.objects.create(name='Jagna', delivery_fee=Decimal('40'), estimated_time='30 min')
        Order.objects.filter(pk=self.d.pk).update(zone=zone)
        self.client.force_login(self.staff)

        r = self.client.get(self.PDF_URL, self.QUERY)              # detail on: totals + the order-by-order list
        self.assertContains(r, 'Jagna')
        self.assertContains(r, '₱40.00')
        self.assertContains(r, 'Delivery Orders')
        self.assertContains(r, f'#{self.d.pk:05d}')

        r = self.client.get(self.PDF_URL, {**self.QUERY, 'log': '0'})   # detail off: totals stay, the list goes
        self.assertContains(r, 'Jagna')
        self.assertContains(r, '₱40.00')
        self.assertNotContains(r, 'Delivery Orders')
        self.assertContains(r, 'not included in this report')

    @patch('inventory.views.MAX_LOG_ITEMS', 3)
    def test_pdf_item_log_is_capped_with_an_explanation(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.PDF_URL, self.QUERY)           # the fixture has 14 item lines in range
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'too many for a single document')
        self.assertNotContains(r, 'GRAND TOTAL')
        self.assertContains(r, '₱1,000.00')                     # the report itself is unaffected

    def test_pdf_respects_the_order_type_filter(self):
        self.client.force_login(self.staff)
        r = self.client.get('/admin/sales-report/document/', {**self.QUERY, 'order_type': 'dine_in'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '₱450.00')
        self.assertNotContains(r, 'Delivery Fee Summary')


class PriceChangeHistoryTests(SalesReportFixture):
    """Repricing a product later must not rewrite what a past period sold for."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.staff = User.objects.create_user('staff@example.com', 'pw', is_staff=True)

    def reprice(self):
        Product.objects.filter(pk=self.latte.pk).update(price=Decimal('999'))
        Product.objects.filter(pk=self.cake.pk).update(price=Decimal('1'))

    def test_repricing_leaves_every_past_figure_alone(self):
        before = self.report()
        self.reprice()
        self.assertEqual(self.report(), before)

    def test_product_row_shows_the_price_it_actually_sold_for(self):
        self.reprice()
        rows = {p['name']: p for p in self.report()['product_performance']}
        self.assertEqual(rows['Latte']['avg_price'], 100.0)      # not the new 999
        self.assertEqual(rows['Cake']['avg_price'], 50.0)        # not the new 1
        self.assertNotIn('base_price', rows['Latte'])            # the live catalogue price isn't in the report

    def test_avg_price_blends_a_price_change_inside_the_range(self):
        # Range already has 6 Lattes at 100 (A 2 + C 1 + D 3); add 2 more sold after a raise to 120.
        o = Order.objects.create(
            email='c@example.com', phone='09171234567', order_type='dine_in',
            status='delivered', payment_method='counter',
        )
        OrderItem.objects.create(order=o, product=self.latte, quantity=2, price=Decimal('120'))
        Order.objects.filter(pk=o.pk).update(created_at=at(2026, 9, 8))
        latte = {p['name']: p for p in self.report()['product_performance']}['Latte']
        self.assertEqual(latte['total_sold'], 8)
        self.assertEqual(latte['total_revenue'], 840.0)          # 6 x 100 + 2 x 120
        self.assertEqual(latte['avg_price'], 105.0)

    def test_report_page_labels_the_column_avg_price(self):
        self.client.force_login(self.staff)
        r = self.client.get('/admin/sales-report/')
        self.assertContains(r, 'Avg. Price')
        self.assertContains(r, 'p.avg_price')
        self.assertNotContains(r, 'base_price')

    def test_pdf_transaction_log_keeps_the_price_at_order_time(self):
        self.reprice()
        self.client.force_login(self.staff)
        r = self.client.get('/admin/sales-report/document/', {
            'date_from': '2026-09-01', 'date_to': '2026-09-10', 'log': '1',
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '₱100.00')
        self.assertNotContains(r, '₱999.00')

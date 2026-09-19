"""
Sales report numbers — the one place that decides what "sales" means, so the
interactive page (through its JSON feed) and the printable PDF can never
disagree with each other.

Definitions
-----------
* Cancelled orders are left out of every figure except the status breakdown —
  a cancelled order was never a sale.
* "Sales" is product sales only: the sum of item price x quantity. Delivery
  fees and loyalty discounts are order-level amounts, reported alongside
  instead of folded in, so every table (per period, per order type, per
  product) adds up to the same headline number.
* Order type ``regular`` is what customers know as Delivery.
* Dates are read in the project's current timezone (settings.TIME_ZONE), the
  same way the admin's date filters do.
"""
import datetime
from collections import defaultdict
from decimal import Decimal
from typing import NamedTuple

from django.db.models import Avg, Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from online_shop.models import Order, OrderItem, Rating

ORDER_TYPES = (
    ('dine_in', 'Dine-in'),
    ('pickup',  'Pick-up'),
    ('regular', 'Delivery'),
)
TYPE_LABELS = dict(ORDER_TYPES)
STATUS_LABELS = dict(Order.STATUS_CHOICES)
PAYMENT_LABELS = dict(Order.PAYMENT_METHOD_CHOICES)

GRANULARITIES = ('auto', 'daily', 'weekly', 'monthly')

MIN_DATE = datetime.date(2000, 1, 1)
MAX_SPAN_DAYS = 1826      # ~5 years — bounds how many rows a report can produce
MAX_DAILY_SPAN = 366      # a daily table past this stops being readable

ZERO = Decimal('0')
SALES = Sum(F('price') * F('quantity'))


class ReportParams(NamedTuple):
    date_from: datetime.date
    date_to: datetime.date
    granularity: str          # resolved: daily / weekly / monthly
    order_type: str           # '' = all types
    granularity_choice: str   # what the user picked (may be 'auto'), for the form


# ─── Input handling ───────────────────────────────────────────────────────────

def _resolve_granularity(choice, span_days):
    if choice not in GRANULARITIES:
        choice = 'auto'
    if choice == 'auto':
        if span_days <= 31:
            return 'daily'
        return 'weekly' if span_days <= 180 else 'monthly'
    if choice == 'daily' and span_days > MAX_DAILY_SPAN:
        return 'weekly'
    return choice


def parse_report_params(params, today=None):
    """Turn request.GET into clean, safe report parameters.

    Never raises: bad or missing values fall back to defaults (last 30 days),
    swapped dates are put in order, and the range is clamped so a hand-edited
    URL can't ask for a table of millions of rows.
    """
    today = today or timezone.localdate()

    def parse_date(raw, fallback):
        try:
            value = datetime.date.fromisoformat(raw) if raw else fallback
        except ValueError:
            return fallback
        return max(value, MIN_DATE)

    date_to = parse_date(params.get('date_to', ''), today)
    date_from = parse_date(params.get('date_from', ''), date_to - datetime.timedelta(days=29))
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    date_to = min(date_to, today)          # nothing has been sold in the future
    date_from = min(date_from, date_to)
    if (date_to - date_from).days + 1 > MAX_SPAN_DAYS:
        date_from = date_to - datetime.timedelta(days=MAX_SPAN_DAYS - 1)

    choice = params.get('granularity', 'auto')
    if choice not in GRANULARITIES:
        choice = 'auto'
    span = (date_to - date_from).days + 1
    order_type = params.get('order_type', '')
    if order_type not in TYPE_LABELS:
        order_type = ''

    return ReportParams(date_from, date_to, _resolve_granularity(choice, span), order_type, choice)


# ─── Scoping ──────────────────────────────────────────────────────────────────

def sales_scope(date_from, date_to, order_type=''):
    """(orders, items) querysets covering the sales in a range.

    Both come from the same definition, so anything built on them (the PDF's
    transaction log, its delivery list) agrees with the aggregates below.
    """
    orders = (
        Order.objects
        .filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
        .exclude(status='cancelled')
    )
    if order_type:
        orders = orders.filter(order_type=order_type)
    return orders, OrderItem.objects.filter(order__in=orders)


# ─── Aggregation helpers ──────────────────────────────────────────────────────

def _blank():
    return {'orders': 0, 'sales': ZERO, 'items': 0, 'discounts': ZERO, 'delivery_fees': ZERO}


def _type_totals(orders, items):
    """{order_type: totals} for a scope. Every known type is present (zeros
    filled in); an unexpected type found in old data is kept rather than
    silently dropped, so the parts always add up to the whole."""
    out = {key: _blank() for key, _ in ORDER_TYPES}
    for r in orders.order_by().values('order_type').annotate(
        n=Count('id'), disc=Sum('discount'), fee=Sum('delivery_fee'),
    ):
        t = out.setdefault(r['order_type'], _blank())
        t['orders'] += r['n']
        t['discounts'] += r['disc'] or ZERO
        t['delivery_fees'] += r['fee'] or ZERO
    for r in items.order_by().values('order__order_type').annotate(sales=SALES, qty=Sum('quantity')):
        t = out.setdefault(r['order__order_type'], _blank())
        t['sales'] += r['sales'] or ZERO
        t['items'] += r['qty'] or 0
    return out


def _sum_totals(totals):
    out = _blank()
    for t in totals.values():
        for key in out:
            out[key] += t[key]
    return out


def _derive(t):
    """Add the figures that are computed from the raw sums."""
    d = dict(t)
    d['avg_order'] = (t['sales'] / t['orders']) if t['orders'] else ZERO
    d['collected'] = t['sales'] - t['discounts'] + t['delivery_fees']
    return d


def _money(value):
    return float(Decimal(value or 0).quantize(Decimal('0.01')))


def _pct_change(current, previous):
    """% change, or None when there's nothing to compare against."""
    previous = Decimal(previous or 0)
    if not previous:
        return None
    return round(float((Decimal(current or 0) - previous) / previous * 100), 1)


def _public(t):
    """A totals dict as plain numbers for JSON / templates."""
    return {
        'orders': t['orders'],
        'items': t['items'],
        'sales': _money(t['sales']),
        'avg_order': _money(t['avg_order']),
        'discounts': _money(t['discounts']),
        'delivery_fees': _money(t['delivery_fees']),
        'collected': _money(t['collected']),
    }


def _type_label(key):
    return TYPE_LABELS.get(key) or key.replace('_', ' ').title()


# ─── Time buckets ─────────────────────────────────────────────────────────────

def _bucket_start(day, granularity):
    if granularity == 'weekly':
        return day - datetime.timedelta(days=day.weekday())   # weeks start Monday
    if granularity == 'monthly':
        return day.replace(day=1)
    return day


def _next_bucket(start, granularity):
    if granularity == 'weekly':
        return start + datetime.timedelta(days=7)
    if granularity == 'monthly':
        return (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return start + datetime.timedelta(days=1)


def _bucket_label(start, date_from, date_to, granularity):
    if granularity == 'monthly':
        return start.strftime('%b %Y')
    if granularity == 'weekly':
        first = max(start, date_from)
        last = min(start + datetime.timedelta(days=6), date_to)
        if first == last:
            return f'{first:%b} {first.day}'
        return f'{first:%b} {first.day} – {last:%b} {last.day}'
    return f'{start:%b} {start.day}'


def _series(orders, items, date_from, date_to, granularity, type_keys):
    """One row per day/week/month in the range — including the empty ones, so
    a quiet day shows up as a zero instead of vanishing from the record."""
    cells = defaultdict(lambda: defaultdict(_blank))

    for r in (
        orders.order_by()
        .annotate(day=TruncDate('created_at'))
        .values('day', 'order_type')
        .annotate(n=Count('id'), disc=Sum('discount'), fee=Sum('delivery_fee'))
    ):
        cell = cells[_bucket_start(r['day'], granularity)][r['order_type']]
        cell['orders'] += r['n']
        cell['discounts'] += r['disc'] or ZERO
        cell['delivery_fees'] += r['fee'] or ZERO

    for r in (
        items.order_by()
        .annotate(day=TruncDate('order__created_at'))
        .values('day', 'order__order_type')
        .annotate(sales=SALES, qty=Sum('quantity'))
    ):
        cell = cells[_bucket_start(r['day'], granularity)][r['order__order_type']]
        cell['sales'] += r['sales'] or ZERO
        cell['items'] += r['qty'] or 0

    rows = []
    previous_sales = None
    start = _bucket_start(date_from, granularity)
    while start <= date_to:
        by_type = cells.get(start, {})
        total = _sum_totals(by_type) if by_type else _blank()
        sales = total['sales']
        rows.append({
            'key': start.isoformat(),
            'label': _bucket_label(start, date_from, date_to, granularity),
            'weekday': f'{start:%a}' if granularity == 'daily' else '',
            'orders': total['orders'],
            'items': total['items'],
            'sales': _money(sales),
            'avg_order': _money(sales / total['orders']) if total['orders'] else 0.0,
            'by_type': {k: _money(by_type[k]['sales']) if k in by_type else 0.0 for k in type_keys},
            'change_pct': _pct_change(sales, previous_sales) if previous_sales is not None else None,
            'is_best': False,
        })
        previous_sales = sales
        start = _next_bucket(start, granularity)

    best = max(rows, key=lambda r: r['sales'], default=None)
    if best and best['sales'] > 0:
        best['is_best'] = True
    return rows


# ─── Products ─────────────────────────────────────────────────────────────────

def _product_rows(items, limit=None):
    # Nothing here reads Product.price: every figure comes from the price
    # snapshotted on each OrderItem, so repricing a product later can't rewrite
    # what a past period actually sold for.
    qs = (
        items.order_by()
        .values('product_id', 'product__name', 'product__category__name')
        .annotate(sales=SALES, qty=Sum('quantity'), orders=Count('order', distinct=True))
        .order_by('-sales', '-qty', 'product__name')
    )
    return list(qs[:limit] if limit else qs)


# ─── The report ───────────────────────────────────────────────────────────────

def build_sales_report(date_from, date_to, granularity='auto', order_type=''):
    span = (date_to - date_from).days + 1
    granularity = _resolve_granularity(granularity, span)
    if order_type not in TYPE_LABELS:
        order_type = ''

    orders, items = sales_scope(date_from, date_to, order_type)
    totals = _type_totals(orders, items)

    # The period just before this one, same length — what "performance"
    # (up or down?) is measured against.
    previous_to = date_from - datetime.timedelta(days=1)
    previous_from = previous_to - datetime.timedelta(days=span - 1)
    prev_orders, prev_items = sales_scope(previous_from, previous_to, order_type)
    prev_totals = _type_totals(prev_orders, prev_items)

    summary = _derive(_sum_totals(totals))
    previous = _derive(_sum_totals(prev_totals))

    # Statuses are counted over *all* orders in range (cancelled included);
    # this is the one place a cancelled order still shows up.
    status_qs = Order.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
    if order_type:
        status_qs = status_qs.filter(order_type=order_type)
    status_counts = {r['status']: r['n'] for r in status_qs.order_by().values('status').annotate(n=Count('id'))}
    status = [{'status': k, 'label': v, 'count': status_counts.get(k, 0)} for k, v in Order.STATUS_CHOICES]

    # Which order types to lay out: just the filtered one, or every type
    # (known ones always, plus any odd legacy type that actually has sales).
    if order_type:
        type_keys = [order_type]
    else:
        type_keys = [k for k, _ in ORDER_TYPES] + sorted(k for k in totals if k not in TYPE_LABELS)

    by_type = []
    for key in type_keys:
        t = _derive(totals[key])
        prev_sales = prev_totals.get(key, _blank())['sales']   # a legacy type may have had none last period
        share = float(t['sales'] / summary['sales'] * 100) if summary['sales'] else 0.0
        by_type.append({
            'key': key,
            'label': _type_label(key),
            **_public(t),
            'share_pct': round(share, 1),
            'previous_sales': _money(prev_sales),
            'change_pct': _pct_change(t['sales'], prev_sales),
            'top_products': [
                {
                    'name': p['product__name'],
                    'category': p['product__category__name'] or 'Uncategorized',
                    'qty': p['qty'] or 0,
                    'sales': _money(p['sales']),
                }
                for p in (_product_rows(items.filter(order__order_type=key), 5) if t['orders'] else [])
            ],
        })

    ratings = dict(Rating.objects.order_by().values_list('product_id').annotate(avg=Avg('rating')))
    product_rows = _product_rows(items)
    product_performance = [
        {
            'id': p['product_id'],
            'name': p['product__name'],
            'category': p['product__category__name'] or 'Uncategorized',
            # What it really sold for in this period (weighted, so a mid-range
            # price change shows up as a blend instead of the latest price).
            'avg_price': _money(p['sales'] / p['qty']) if p['qty'] else 0.0,
            'total_sold': p['qty'] or 0,
            'total_revenue': _money(p['sales']),
            'order_count': p['orders'],
            'avg_rating': round(float(ratings[p['product_id']]), 1) if p['product_id'] in ratings else None,
        }
        for p in product_rows
    ]

    categories = [
        {'name': r['product__category__name'] or 'Uncategorized', 'sales': _money(r['sales']), 'qty': r['qty'] or 0}
        for r in (
            items.order_by().values('product__category__name')
            .annotate(sales=SALES, qty=Sum('quantity'))
            .order_by('-sales')
        )
    ]

    payment = {k: {'method': k, 'label': v, 'orders': 0, 'sales': ZERO} for k, v in Order.PAYMENT_METHOD_CHOICES}

    def pay_row(code):
        return payment.setdefault(code, {'method': code, 'label': PAYMENT_LABELS.get(code, code), 'orders': 0, 'sales': ZERO})

    for r in orders.order_by().values('payment_method').annotate(n=Count('id')):
        pay_row(r['payment_method'])['orders'] = r['n']
    for r in items.order_by().values('order__payment_method').annotate(sales=SALES):
        pay_row(r['order__payment_method'])['sales'] = r['sales'] or ZERO

    return {
        'meta': {
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'days': span,
            'granularity': granularity,
            'order_type': order_type,
            'order_type_label': TYPE_LABELS.get(order_type, 'All order types'),
            'previous_from': previous_from.isoformat(),
            'previous_to': previous_to.isoformat(),
            'timezone': str(timezone.get_current_timezone()),
        },
        'summary': {
            **_public(summary),
            'cancelled_orders': status_counts.get('cancelled', 0),
            'delivered_orders': next((s['count'] for s in status if s['status'] == 'delivered'), 0),
        },
        'previous': _public(previous),
        'comparison': {
            'sales': _pct_change(summary['sales'], previous['sales']),
            'orders': _pct_change(summary['orders'], previous['orders']),
            'items': _pct_change(summary['items'], previous['items']),
            'avg_order': _pct_change(summary['avg_order'], previous['avg_order']),
        },
        'by_type': by_type,
        'series': _series(orders, items, date_from, date_to, granularity, type_keys),
        'top_products': [
            {'name': p['name'], 'category': p['category'], 'qty': p['total_sold'], 'sales': p['total_revenue']}
            for p in product_performance[:10]
        ],
        'categories': categories,
        'product_performance': product_performance,
        'status': status,
        'payment_methods': [
            {'method': p['method'], 'label': p['label'], 'orders': p['orders'], 'sales': _money(p['sales'])}
            for p in payment.values()
        ],
    }

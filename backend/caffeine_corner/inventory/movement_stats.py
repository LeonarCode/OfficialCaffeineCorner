"""
The numbers behind the Stock Movements overview (the cards, the chart and the
"most used / biggest waste" lists above the list).

Everything is measured in pesos — quantity x cost per unit at the time of the
movement — because that is the one measure that adds up across items: 2 kg of
beans, 500 g of sugar and 30 cups can't be summed as quantities, but they can as
money. Quantities still show up where they make sense (per item, with its unit).

What counts as what:

    received   stock coming in from outside          purchase, transfer
    used       consumed by orders                    usage, less the stock put
                                                     back by cancelled orders (reversal)
    lost       waste and write-offs entered by hand  spoilage, adjustment, return
    net        received + put back - used - lost     the change in stock value

The overview describes the queryset the list is showing, so it moves with the
period chips, the filters and the search. Change-vs-previous-period is only shown
when nothing but the period is filtering (a comparison against a differently
filtered slice would compare unlike things).
"""
import datetime
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Min, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import StockMovement
from .sales_report import _bucket_label, _bucket_start, _next_bucket
from .stock import show

ZERO = Decimal('0')

PERIODS = (
    ('today', 'Today'),
    ('7d', 'Last 7 days'),
    ('30d', 'Last 30 days'),
    ('month', 'This month'),
    ('lastmonth', 'Last month'),
    ('all', 'All time'),
)
PERIOD_KEYS = tuple(key for key, _label in PERIODS)
DEFAULT_PERIOD = '30d'

# quantity x cost per unit, per movement
VALUE = ExpressionWrapper(F('quantity') * F('unit_cost'), output_field=DecimalField(max_digits=20, decimal_places=2))

RECEIVED = ('purchase', 'transfer')
USED = ('usage',)
RESTORED = ('reversal',)
LOST = ('spoilage', 'adjustment', 'return')
LOST_REASON = {'spoilage': 'spoilage', 'adjustment': 'adjustments', 'return': 'returned to supplier'}

# A chart with a bar per day is readable for about six weeks; past that, weeks, then months.
MAX_DAILY_BARS = 45
MAX_WEEKLY_BARS_DAYS = 210


def money(value):
    return f'₱{Decimal(value):,.2f}'


def normalize_period(value):
    return value if value in PERIOD_KEYS else DEFAULT_PERIOD


# ─── Periods ──────────────────────────────────────────────────────────────────

def _first_of_next_month(day):
    return (day.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)


def period_bounds(period, today):
    """(first day, day after the last day) — or (None, None) for all time."""
    one = datetime.timedelta(days=1)
    if period == 'today':
        return today, today + one
    if period == '7d':
        return today - datetime.timedelta(days=6), today + one
    if period == '30d':
        return today - datetime.timedelta(days=29), today + one
    if period == 'month':
        first = today.replace(day=1)
        return first, _first_of_next_month(first)
    if period == 'lastmonth':
        this_month = today.replace(day=1)
        return (this_month - one).replace(day=1), this_month
    return None, None


def previous_bounds(start, end):
    """The window of the same length that ends where this one starts."""
    return start - (end - start), start


def _range_label(period, start, end):
    if period == 'all' and start is None:
        return 'All time'
    last = end - datetime.timedelta(days=1)
    if start == last:
        return f'{start:%b} {start.day}, {start.year}'
    if start.year == last.year:
        return f'{start:%b} {start.day} – {last:%b} {last.day}, {last.year}'
    return f'{start:%b} {start.day}, {start.year} – {last:%b} {last.day}, {last.year}'


# ─── Totals ───────────────────────────────────────────────────────────────────

def _tally(queryset):
    rows = queryset.order_by().values('movement_type').annotate(value=Sum(VALUE), n=Count('id'))
    by_type = {row['movement_type']: (row['value'] or ZERO, row['n']) for row in rows}

    def value(*types):
        return sum((by_type[t][0] for t in types if t in by_type), ZERO)

    def count(*types):
        return sum(by_type[t][1] for t in types if t in by_type)

    received, used, restored, lost = value(*RECEIVED), value(*USED), value(*RESTORED), value(*LOST)
    return {
        'count': sum(n for _v, n in by_type.values()),
        'received': received, 'received_n': count(*RECEIVED),
        'used_gross': used, 'restored': restored, 'used': used - restored, 'used_n': count(*USED),
        'lost': lost, 'lost_n': count(*LOST),
        'lost_parts': [(LOST_REASON[t], by_type[t][1]) for t in LOST if t in by_type],
        'net': received + restored - used - lost,
    }


def _delta(current, previous, worse=None):
    """
    The change vs the previous period as a small pill: {'text', 'tone'}, or None
    when there's nothing to compare. `worse` is the direction that is bad news
    ('up' for waste); with None a change is just shown, not judged.
    """
    if previous is None:
        return None
    if previous == 0:
        return {'text': 'new', 'tone': 'new'} if current != 0 else None
    pct = float((current - previous) / abs(previous) * 100)
    if abs(pct) < 0.5:
        return {'text': '0%', 'tone': 'flat'}
    tone = 'flat'
    if worse:
        tone = 'bad' if (pct > 0) == (worse == 'up') else 'good'
    size = '999%+' if abs(pct) >= 1000 else f'{abs(pct):.0f}%'         # "30668%" says less than "a lot more"
    return {'text': f'{"▲" if pct > 0 else "▼"} {size}', 'tone': tone}


def _plural(n, one, many):
    return f'{n:,} {one if n == 1 else many}'


def _cards(now, before):
    def prev(key):
        return before[key] if before is not None else None

    used_foot = _plural(now['used_n'], 'deduction from orders', 'deductions from orders')
    if now['restored'] > 0:
        used_foot += f' · {money(now["restored"])} put back'

    if now['lost_n']:
        parts = [f'{n} {reason}' for reason, n in now['lost_parts']]
        lost_foot = ' · '.join(parts)
    else:
        lost_foot = 'Nothing wasted or written off'

    net = now['net']
    return [
        {'key': 'received', 'label': 'Stock received', 'icon': 'move_to_inbox', 'accent': 'green',
         'value': money(now['received']), 'foot': _plural(now['received_n'], 'stock-in entry', 'stock-in entries'),
         'delta': _delta(now['received'], prev('received'))},
        {'key': 'used', 'label': 'Used in orders', 'icon': 'local_cafe', 'accent': 'brown',
         'value': money(now['used']), 'foot': used_foot,
         'delta': _delta(now['used'], prev('used'))},
        {'key': 'lost', 'label': 'Waste & adjustments', 'icon': 'delete_sweep',
         'accent': 'orange' if now['lost'] > 0 else 'green',
         'value': money(now['lost']), 'foot': lost_foot,
         'delta': _delta(now['lost'], prev('lost'), worse='up')},
        {'key': 'net', 'label': 'Net change in stock value',
         'icon': 'trending_up' if net >= 0 else 'trending_down', 'accent': 'blue',
         'value': ('+' if net >= 0 else '−') + money(abs(net)), 'foot': 'Received − used − waste',
         'delta': _delta(net, prev('net'))},
    ]


# ─── Chart ────────────────────────────────────────────────────────────────────

def _local_date(moment):
    return timezone.localtime(moment).date()


def _chart(queryset, start, end):
    """Received / used / lost per day, week or month — gaps filled so a quiet day is a zero, not a missing bar."""
    span = (end - start).days
    granularity = 'daily' if span <= MAX_DAILY_BARS else 'weekly' if span <= MAX_WEEKLY_BARS_DAYS else 'monthly'

    rows = (
        queryset.order_by().annotate(day=TruncDate('created_at')).values('day')
        .annotate(
            received=Sum(VALUE, filter=Q(movement_type__in=RECEIVED)),
            used=Sum(VALUE, filter=Q(movement_type__in=USED)),
            restored=Sum(VALUE, filter=Q(movement_type__in=RESTORED)),
            lost=Sum(VALUE, filter=Q(movement_type__in=LOST)),
        )
    )
    cells = defaultdict(lambda: [ZERO, ZERO, ZERO])
    for row in rows:
        cell = cells[_bucket_start(row['day'], granularity)]
        cell[0] += row['received'] or ZERO
        cell[1] += (row['used'] or ZERO) - (row['restored'] or ZERO)      # cancelled orders give stock back
        cell[2] += row['lost'] or ZERO

    last = end - datetime.timedelta(days=1)
    chart = {'granularity': granularity, 'labels': [], 'received': [], 'used': [], 'lost': []}
    bucket = _bucket_start(start, granularity)
    while bucket <= last:
        received, used, lost = cells.get(bucket, (ZERO, ZERO, ZERO))
        chart['labels'].append(_bucket_label(bucket, start, last, granularity))
        chart['received'].append(float(received))
        chart['used'].append(float(used))
        chart['lost'].append(float(lost))
        bucket = _next_bucket(bucket, granularity)
    return chart


# ─── Ranked lists ─────────────────────────────────────────────────────────────

def _ranked(items, limit):
    top = items[:limit]
    peak = top[0]['value'] if top else ZERO
    for item in top:
        item['value_text'] = money(item['value'])
        item['qty_text'] = f'{show(item["qty"])} {item["unit"]}'
        item['pct'] = max(round(item['value'] / peak * 100), 3) if peak else 0
    return top


def _top_used(queryset, limit=5):
    rows = (
        queryset.order_by().filter(movement_type__in=USED + RESTORED)
        .values('inventory_id', 'inventory__name', 'inventory__unit')
        .annotate(
            used=Sum(VALUE, filter=Q(movement_type__in=USED)),
            restored=Sum(VALUE, filter=Q(movement_type__in=RESTORED)),
            used_qty=Sum('quantity', filter=Q(movement_type__in=USED)),
            restored_qty=Sum('quantity', filter=Q(movement_type__in=RESTORED)),
        )
    )
    items = []
    for row in rows:
        value = (row['used'] or ZERO) - (row['restored'] or ZERO)
        if value > 0:
            items.append({
                'id': row['inventory_id'], 'name': row['inventory__name'], 'unit': row['inventory__unit'],
                'value': value, 'qty': (row['used_qty'] or ZERO) - (row['restored_qty'] or ZERO),
            })
    items.sort(key=lambda item: (-item['value'], item['name']))
    return _ranked(items, limit)


def _top_lost(queryset, limit=5):
    rows = (
        queryset.order_by().filter(movement_type__in=LOST)
        .values('inventory_id', 'inventory__name', 'inventory__unit', 'movement_type')
        .annotate(value=Sum(VALUE), qty=Sum('quantity'))
    )
    per_item = {}
    for row in rows:
        item = per_item.setdefault(row['inventory_id'], {
            'id': row['inventory_id'], 'name': row['inventory__name'], 'unit': row['inventory__unit'],
            'value': ZERO, 'qty': ZERO, 'reasons': defaultdict(lambda: ZERO),
        })
        item['value'] += row['value'] or ZERO
        item['qty'] += row['qty'] or ZERO
        item['reasons'][row['movement_type']] += row['value'] or ZERO
    items = sorted(per_item.values(), key=lambda item: (-item['value'], item['name']))
    for item in items:
        main = max(item['reasons'], key=lambda kind: item['reasons'][kind])
        item['reason'] = LOST_REASON[main]
    return _ranked(items, limit)


# ─── The whole overview ───────────────────────────────────────────────────────

def build_overview(queryset, period, comparable, today=None):
    """
    Everything the overview panel shows, for the movements in `queryset`.

    `period` only decides the label and the previous-period comparison — the
    queryset itself has already been narrowed to the period (and any filters) by
    the changelist. `comparable` says whether nothing but the period is
    filtering, so a comparison with the previous period is meaningful.
    """
    today = today or timezone.localdate()
    period = normalize_period(period)
    start, end = period_bounds(period, today)
    now = _tally(queryset)

    before, compare_label = None, ''
    if comparable and start is not None:
        prev_start, prev_end = previous_bounds(start, end)
        before = _tally(StockMovement.objects.filter(created_at__date__gte=prev_start, created_at__date__lt=prev_end))
        days = (end - start).days
        compare_label = 'yesterday' if period == 'today' else f'the previous {days} days'

    label = _range_label(period, start, end)
    chart = None
    if now['count']:
        if start is None:                                   # all time: from the first movement to the last
            span = queryset.order_by().aggregate(first=Min('created_at'), last=Max('created_at'))
            chart_start, chart_end = _local_date(span['first']), _local_date(span['last']) + datetime.timedelta(days=1)
            label = _range_label('range', chart_start, chart_end) + ' (all time)'
        else:
            chart_start, chart_end = start, end
        chart = _chart(queryset, chart_start, chart_end)

    return {
        'period': period,
        'label': label,
        'count': now['count'],
        'has_data': bool(now['count']),
        'cards': _cards(now, before),
        'compare_label': compare_label if before is not None else '',
        'chart': chart,
        'top_used': _top_used(queryset) if now['count'] else [],
        'top_lost': _top_lost(queryset) if now['count'] else [],
    }

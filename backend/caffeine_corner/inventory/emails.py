"""
The email that carries a purchase order to the supplier (templates/emails/purchase_order.*).

Staff press "Email to supplier" on a Purchase Order; this builds the message —
what is being ordered, the quantities and costs, when it should arrive and where
to — and hands it to caffeine_corner.mailer. The rules about *whether* it may be
sent (a supplier email on file, an order that isn't cancelled or finished) live in
purchasing.email_to_supplier(); this file only says what the email contains.
"""
from decimal import Decimal

from django.conf import settings

from caffeine_corner import mailer
from caffeine_corner.mailer import peso, shop_time

from .models import PurchaseOrderItem

ZERO = Decimal('0')


def _qty(value):
    """5 -> "5", 2.5 -> "2.50", 1250 -> "1,250" (whole numbers without a pointless .00)."""
    value = Decimal(value)
    return f'{value:,.0f}' if value == value.to_integral() else f'{value:,.2f}'


def _date(value):
    return f'{value:%A}, {value:%B} {value.day}, {value.year}'


def _moment(value):
    moment = shop_time(value)
    return f'{moment:%B} {moment.day}, {moment.year}'


def build_context(po, sent_by=None):
    """Everything the template shows, worded and formatted here."""
    lines = list(PurchaseOrderItem.objects.filter(purchase_order=po).select_related('inventory').order_by('inventory__name'))
    supplier = po.supplier
    any_received = any(line.quantity_received > 0 for line in lines)

    rows = [
        {
            'name': line.inventory.name,
            'sku': line.inventory.sku,
            'unit': line.inventory.unit,
            'ordered': _qty(line.quantity_ordered),
            'received': _qty(line.quantity_received),
            'remaining': _qty(max(line.quantity_ordered - line.quantity_received, ZERO)),
            'unit_cost': peso(line.unit_cost),
            'total': peso(line.total_cost),
        }
        for line in lines
    ]

    details = [('Order date', _moment(po.ordered_at))]
    if po.expected_at:
        details.append(('Expected delivery', _date(po.expected_at)))
    details.append(('Deliver to', f'{settings.SHOP_NAME}, {settings.SHOP_ADDRESS}'))
    if sent_by is not None:
        details.append(('Prepared by', sent_by.get_full_name() or sent_by.email))

    if po.emailed_at:
        intro = (f'This is an updated copy of the purchase order we emailed you on {_moment(po.emailed_at)}. '
                 'Please use this version.')
    else:
        intro = 'Please find our purchase order below. We would like to order the following items.'
    if any_received:
        intro += ' Items already delivered are shown, along with what is still to come.'

    return {
        'subject': f'{settings.SHOP_NAME}: Purchase Order {po.reference}',
        'preheader': f'Purchase Order {po.reference} — {len(rows)} item{"s" if len(rows) != 1 else ""}, {peso(po.total_cost)}',
        'reference': po.reference,
        'greeting': f'Hello {supplier.contact_name or supplier.name},',
        'intro': intro,
        'details': details,
        'rows': rows,
        'any_received': any_received,
        'total': peso(sum((line.total_cost for line in lines), ZERO)),
        'notes': po.notes,
    }


def send_purchase_order(po, sent_by, to):
    """Sends the purchase order email now. Raises if the mail server refuses or times out."""
    context = build_context(po, sent_by)
    mailer.send_html_email(subject=context['subject'], to=to, template='purchase_order', context=context)

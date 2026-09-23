"""
The emails a customer gets about an online order (templates/emails/order_confirmation.*):

    "placed"   right after they order — what they ordered, what it comes to, how
               and when to pay, and where it is going (or which table).
    "paid"     for a GCash order, once the payment goes through.

Only orders placed through the site/app get these (OrderCreateView and the GCash
payment confirmation). An order a staff member types into the admin doesn't: the
customer is standing right there, and the admin form isn't "ordering online".

All the wording is decided here, not in the template, so it can be tested as text.
"""
from decimal import Decimal

from django.conf import settings

from caffeine_corner import mailer
from caffeine_corner.mailer import peso, shop_time

from .models import Order

ZERO = Decimal('0')


def order_reference(order):
    return f'#CC-{order.pk:05d}'


def _placed_at(order):
    moment = shop_time(order.created_at)
    return f'{moment:%B} {moment.day}, {moment.year} at {moment.strftime("%I:%M %p").lstrip("0")}'


def _amount_due(order):
    """What the customer pays for the whole order: items + delivery, less loyalty points used."""
    return max(order.subtotal + order.delivery_fee - order.discount, ZERO)


def _cash_label(order):
    return 'Cash on delivery' if order.order_type == 'regular' else 'Cash on pick-up'


def payment_method_label(order):
    if order.payment_method == 'cod':
        return _cash_label(order)
    return order.get_payment_method_display()


def _payment_block(order, event, total):
    """(title, note, tone): how it is paid and what the customer should do about it."""
    has_downpayment = order.downpayment_amount > 0
    if event == 'paid':
        if order.payment_status == 'downpayment' or has_downpayment:
            return ('Downpayment received',
                    f'We received your GCash downpayment of {peso(order.downpayment_amount)}. '
                    f'Please have the remaining {peso(order.remaining_balance)} ready when your order arrives.', 'ok')
        return ('Payment received', 'We received your GCash payment. Thank you!', 'ok')

    if order.payment_method == 'gcash':
        if has_downpayment:
            return ('Waiting for your GCash downpayment',
                    f'Please complete your GCash downpayment of {peso(order.downpayment_amount)} (30%) to confirm this order. '
                    f'The remaining {peso(order.remaining_balance)} is paid on delivery.', 'wait')
        return ('Waiting for your GCash payment',
                f'Please complete your GCash payment of {peso(total)} to confirm this order. '
                'If the GCash page closed before you paid, tell us and we will help.', 'wait')
    if order.payment_method == 'cod':
        if order.order_type == 'regular':
            return ('Cash on delivery', f'Please have {peso(total)} in cash ready for the rider when your order arrives.', 'info')
        return ('Cash on pick-up', f'Please pay {peso(total)} in cash when you pick up your order.', 'info')
    return ('Pay at the counter', f'Please pay {peso(total)} at the counter.', 'info')


def _intro(order, event):
    if event == 'paid':
        return "Your order is confirmed and we're getting it ready."
    if order.order_type == 'dine_in':
        return f"We received your order for Table {order.table_number} and we're preparing it now."
    if order.order_type == 'pickup':
        return 'We received your order and will have it ready for you at the counter.'
    return "We received your order and will start preparing it. We'll bring it to your address."


def _details(order):
    """The where/who lines that make sense for this kind of order."""
    rows = []
    if order.order_type == 'regular':                # (a dine-in order's table is already part of its "Order type" line)
        if order.address:
            rows.append(('Deliver to', order.address))
        if order.zone_id:
            zone = order.zone.name + (f' · usually {order.zone.estimated_time}' if order.zone.estimated_time else '')
            rows.append(('Delivery zone', zone))
    if order.phone and order.order_type != 'dine_in':
        rows.append(('Contact number', order.phone))
    return rows


def build_context(order, event='placed'):
    """Everything the template shows, as plain strings — see the module docstring."""
    items = [
        {
            'name': item.product.name,
            'variant': item.variant.get_size_display() if item.variant_id else '',
            'qty': item.quantity,
            'price': peso(item.price),
            'subtotal': peso(item.subtotal),
        }
        for item in order.items.all()
    ]
    total = _amount_due(order)

    totals = [('Subtotal', peso(order.subtotal))]
    if order.delivery_fee > 0:
        totals.append(('Delivery fee', peso(order.delivery_fee)))
    if order.discount > 0:
        totals.append(('Loyalty points discount', f'-{peso(order.discount)}'))

    payment_lines = []
    if order.downpayment_amount > 0:
        payment_lines = [('Downpayment (30%)', peso(order.downpayment_amount)), ('Balance on delivery', peso(order.remaining_balance))]

    title, note, tone = _payment_block(order, event, total)
    reference = order_reference(order)
    type_label = order.get_order_type_display() + (f' · Table {order.table_number}' if order.order_type == 'dine_in' and order.table_number else '')
    if event == 'paid':
        headline, subject = 'Payment received — thank you!', f'Payment received for your order {reference}'
    else:
        headline, subject = 'Thanks for your order!', f'We received your order {reference}'

    return {
        'subject': f'{settings.SHOP_NAME}: {subject}',
        'preheader': f'Order {reference} · {peso(total)} · {order.get_order_type_display()}',
        'headline': headline,
        'intro': _intro(order, event),
        'order_ref': reference,
        'placed_at': _placed_at(order),
        'type_label': type_label,
        'payment_method': payment_method_label(order),
        'details': _details(order),
        'items': items,
        'totals': totals,
        'total': peso(total),
        'payment_lines': payment_lines,
        'payment_title': title,
        'payment_note': note,
        'payment_tone': tone,
        'notes': order.notes,
        # A guest has no orders page to go to; only a signed-in customer gets the button.
        'orders_url': f'{settings.FRONTEND_URL}/orders' if order.user_id else '',
    }


def send_order_email(order_id, event='placed'):
    """
    Sends the email now (from whichever thread this runs in). Returns True if it
    went out, False if there was nothing to send to. Failures raise — callers that
    must not be disturbed go through queue_order_email().
    """
    order = (
        Order.objects.select_related('zone', 'user')
        .prefetch_related('items__product', 'items__variant')
        .filter(pk=order_id).first()
    )
    if order is None or not order.email:
        return False
    context = build_context(order, event)
    mailer.send_html_email(subject=context['subject'], to=order.email, template='order_confirmation', context=context)
    return True


def queue_order_email(order, event='placed'):
    """
    Emails the customer about `order` without holding the request up, and without
    ever letting a mail problem touch the order (it is already saved). Failures
    are logged under "caffeine_corner.mail".
    """
    return mailer.run_in_background(send_order_email, order.pk, event)

"""
Cash a rider is holding, and turning it in.

A rider collects cash on every Cash-on-Delivery order they deliver — that
cash is "outstanding" until they hand it over to the shop and a Remittance
is recorded for it. There is no running balance stored anywhere: what a
rider is holding right now is always worked out fresh, from which of their
delivered, paid COD orders haven't been folded into a Remittance yet (see
Order.remittance). Recording one is the only thing that ever changes that —
nothing here is a number someone can quietly edit.
"""
from decimal import Decimal

from django.db import transaction

from .models import Order, Remittance

ZERO = Decimal('0')


class RemittanceError(Exception):
    """A rule was broken (message is written for staff and shown as-is)."""


def outstanding_orders(rider):
    """
    This rider's delivered, paid Cash-on-Delivery orders that haven't been
    turned in yet — oldest first, the order they'd naturally be listed in.
    """
    return Order.objects.filter(
        assigned_rider=rider, order_type='regular', payment_method='cod',
        status='delivered', payment_status='paid', remittance__isnull=True,
    ).order_by('delivered_at').prefetch_related('items')


def outstanding_total(rider):
    """What outstanding_orders(rider) adds up to — the amount a "Record remittance" right now would be for."""
    return sum((order.total_price for order in outstanding_orders(rider)), ZERO)


def riders_with_outstanding_cash():
    """
    Every rider currently holding Cash-on-Delivery cash, most first — "Record
    remittance" only lives on a rider's own page (Users & Access → Users), so
    the Remittance list — otherwise just a history of what's already been
    turned in — shows this too, or there would be no way to tell *which*
    rider's page to go to without checking each one by hand.
    """
    from django.contrib.auth import get_user_model
    rider_ids = (
        Order.objects.filter(
            order_type='regular', payment_method='cod', status='delivered',
            payment_status='paid', remittance__isnull=True, assigned_rider__isnull=False,
        )
        .order_by().values_list('assigned_rider_id', flat=True).distinct()
    )
    riders = get_user_model().objects.filter(pk__in=rider_ids)
    rows = [(rider, outstanding_total(rider), outstanding_orders(rider).count()) for rider in riders]
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows


@transaction.atomic
def record_remittance(rider, received_by, notes=''):
    """
    Turns every order this rider is currently holding cash for into one
    Remittance, at whatever that adds up to right now. Raises RemittanceError
    — with a message written for staff — if there's nothing outstanding.
    """
    orders = list(outstanding_orders(rider).select_for_update())
    if not orders:
        name = rider.get_full_name() or rider.email
        raise RemittanceError(f'{name} has nothing outstanding to remit right now.')
    total = sum((order.total_price for order in orders), ZERO)
    remittance = Remittance.objects.create(rider=rider, amount=total, received_by=received_by, notes=notes)
    Order.objects.filter(pk__in=[order.pk for order in orders]).update(remittance=remittance)
    return remittance

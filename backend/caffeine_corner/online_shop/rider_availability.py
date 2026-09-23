"""
Which riders can take a new delivery right now — the batching rule.

A rider can be given up to BATCH_CAP deliveries in the same town zone while
still tied up on an earlier one: a realistic run of nearby drops they can
reasonably chain together. The moment a *different* zone comes up, or the
cap for the current one is reached, they're not offered again until every
one of those recent same-zone orders has had time to actually be made —
production_minutes_for() below, not a flat window: a rider who just took a
pastry order that takes 45 minutes to bake is tied up longer than one who
took a coffee-only order, because the earlier delivery is assumed to still
be in the kitchen (or just leaving) for as long as its slowest item takes.

Assignment time (Order.assigned_rider_at), not order status, is what "how
long ago" is measured from — see Order.save().
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Order

BATCH_CAP = 3

# Even an order with no per-item prep time set (Product.time_production still
# at its default of 0) realistically ties a rider up for a little while —
# fetching, packing, handing off. Without this floor, an unset product would
# make the rider look instantly free the moment they're assigned.
MIN_BUSY_MINUTES = 15

# A hard outer bound regardless of any single order's own prep time — a
# mistyped production time (or just a rider with a long history) should
# never turn this into an unbounded scan of a rider's past orders, or lock
# them out of new assignments indefinitely.
MAX_LOOKBACK = timedelta(hours=6)


def production_minutes_for(order):
    """
    How long `order` realistically takes to have ready — the slowest item in
    it, not the sum of all of them (a barista and the oven work on different
    items at the same time, they don't queue behind each other), floored at
    MIN_BUSY_MINUTES.
    """
    times = [item.product.time_production for item in order.items.all()]
    return max([MIN_BUSY_MINUTES, *times])


def _still_busy(order, now):
    return order.assigned_rider_at + timedelta(minutes=production_minutes_for(order)) > now


def recent_assignments(rider, exclude_order_id=None):
    """
    This rider's delivery assignments that are still tying them up right
    now, most recent first — a cancelled order was never really "taken", so
    it doesn't count, and `exclude_order_id` leaves the order being edited
    out of its own check (otherwise saving an order would find its own
    rider "busy" on it).
    """
    queryset = Order.objects.filter(
        assigned_rider=rider, order_type='regular', assigned_rider_at__gte=timezone.now() - MAX_LOOKBACK,
    ).exclude(status='cancelled').prefetch_related('items__product')
    if exclude_order_id:
        queryset = queryset.exclude(pk=exclude_order_id)
    now = timezone.now()
    recent = [order for order in queryset if _still_busy(order, now)]
    recent.sort(key=lambda order: order.assigned_rider_at, reverse=True)
    return recent


def is_available_for(rider, zone, exclude_order_id=None):
    """
    Whether `rider` can be handed a new delivery in `zone` right now. A zone
    of None (an order with no zone set at all) never batches with anything,
    including itself — there's nothing to confirm it's really the same run.
    """
    recent = recent_assignments(rider, exclude_order_id)
    if not recent:
        return True
    if zone is None:
        return False
    zones = {order.zone_id for order in recent}
    return zones == {zone.pk} and len(recent) < BATCH_CAP


def zone_has_available_rider(zone):
    """
    Whether at least one rider could be handed a new delivery to `zone`
    right now — the same rule the assigned-rider dropdown offers riders
    under (formfield_for_foreignkey in admin.py), checked ahead of time
    for a zone that has no order yet, while the customer is still at
    checkout.
    """
    riders = get_user_model().objects.filter(is_rider=True)
    return any(is_available_for(rider, zone) for rider in riders)

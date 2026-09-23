"""
Purchase-order rules, in one place: numbering, what is already on order, what
needs reordering, and — the part that was missing entirely — receiving stock.

Before this module, a Purchase Order could be marked "Fully Received" and
nothing happened: `quantity_received`, `received_at` and the received/partial
statuses were never read by any code, so stock only went up if someone also
typed a separate Stock Movement by hand. Receiving now *is* the stock movement:
every quantity that arrives is recorded as a "Stock In — Purchase" against the
PO's reference, so the PO, the item's history and the stock level always agree.

Used by the admin (inventory/admin.py) and the Auto-Generate button
(inventory/views.py).
"""
import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from . import emails
from .models import Inventory, PurchaseOrder, PurchaseOrderItem, StockMovement

logger = logging.getLogger('caffeine_corner.mail')

ZERO = Decimal('0')

# A PO in one of these states is still expected to bring stock in.
OPEN_STATUSES = ('draft', 'sent', 'partial')


class PurchaseOrderError(Exception):
    """A rule was broken (message is written for staff and shown as-is)."""


# ─── Numbering ────────────────────────────────────────────────────────────────
# The number is the order's own database id, so it can only ever be assigned
# once — no scanning for the highest taken number, no gaps to "continue from",
# no chance of two staff members racing for the same number (each row gets its
# own id from the database itself, atomically, the moment it is inserted).
# PurchaseOrder.save() is what actually assigns it (a blank reference, on any
# save); this is just the format, kept here so it's only written once.

def reference_for(po):
    """The number a saved PO's own id turns into — purchase order #42 is "PO-000042"."""
    return f'PO-{po.pk:06d}'


# ─── State ────────────────────────────────────────────────────────────────────

def _lines(po):
    """
    The order's lines, read from the database every time — not through the
    order's `items` relation: the admin prefetches those for the list, and that
    cached copy is stale the moment a line is saved. Status was then worked out
    from quantities that had already changed (an order stayed "sent" after
    stock had come in).
    """
    return list(PurchaseOrderItem.objects.filter(purchase_order_id=po.pk))


def is_settled(po):
    """
    Finished: cancelled, or received with every line actually in. Settled POs
    are read-only. A PO merely *marked* received while lines are still short
    (how old data looks) is not settled — it can still be fixed.
    """
    if po.status == 'cancelled':
        return True
    lines = _lines(po)
    return po.status == 'received' and bool(lines) and all(line.is_fully_received for line in lines)


def outstanding_by_item():
    """{inventory_id: quantity still expected} across every open PO."""
    rows = (
        PurchaseOrderItem.objects
        .filter(purchase_order__status__in=OPEN_STATUSES)
        .values('inventory_id')
        .annotate(left=Sum(F('quantity_ordered') - F('quantity_received')))
    )
    return {row['inventory_id']: max(row['left'] or ZERO, ZERO) for row in rows}


def sync_status(po):
    """
    Work out received / partial from the lines. Cancelled POs are left alone,
    and one that was marked received/partial while nothing has actually come
    in goes back to "sent" (that is what old data looks like).
    """
    if po.status == 'cancelled':
        return
    lines = _lines(po)
    all_in = bool(lines) and all(line.is_fully_received for line in lines)
    got_some = any(line.quantity_received > 0 for line in lines)
    if all_in:
        status = 'received'
    elif got_some:
        status = 'partial'
    elif po.status in ('partial', 'received'):
        status = 'sent'
    else:
        status = po.status

    changed = []
    if status != po.status:
        po.status = status
        changed.append('status')
    received_at = (po.received_at or timezone.localdate()) if status == 'received' else None
    if received_at != po.received_at:
        po.received_at = received_at
        changed.append('received_at')
    if changed:
        po.save(update_fields=changed)


# ─── Receiving ────────────────────────────────────────────────────────────────

def record_receipt(line, quantity, user):
    """The stock movement for `quantity` of a PO line arriving."""
    reference = line.purchase_order.reference
    return StockMovement.objects.create(
        inventory=line.inventory,
        movement_type='purchase',
        quantity=quantity,
        unit_cost=line.unit_cost,
        reference=reference,
        notes=f'Received against {reference}',
        performed_by=user,
    )


@transaction.atomic
def receive_remaining(po, user):
    """
    Everything still outstanding on the PO arrives: each line is topped up to
    the quantity ordered and the difference goes into stock. Returns
    [(line, quantity_added)].
    """
    if po.status == 'cancelled':
        raise PurchaseOrderError(f'{po.reference} is cancelled — nothing can be received on it.')
    received = []
    for line in po.items.select_related('inventory', 'purchase_order'):
        left = line.quantity_ordered - line.quantity_received
        if left > 0:
            line.quantity_received = line.quantity_ordered
            line.save(update_fields=['quantity_received'])
            record_receipt(line, left, user)
            received.append((line, left))
    sync_status(po)
    return received


@transaction.atomic
def close_partial(po):
    """
    Accepts a partially-received order as final, for when the supplier isn't
    sending the rest: every line still short is lowered to what actually
    arrived — so it reads as fully received, the way the order really turned
    out — and the order itself becomes Fully Received.

    What used to be a raw edit of "Order qty" on an already-saved line (typed
    straight into the field, with nothing to say *why* it changed) is now
    only ever done this way — a deliberate, named action, not a value that
    quietly wasn't what was actually ordered any more.
    """
    if po.status != 'partial':
        raise PurchaseOrderError(f'{po.reference} is not partially received (it is “{po.get_status_display()}”).')
    for line in _lines(po):
        if line.quantity_received < line.quantity_ordered:
            line.quantity_ordered = line.quantity_received
            line.save(update_fields=['quantity_ordered'])
    sync_status(po)


def mark_sent(po):
    if po.status != 'draft':
        raise PurchaseOrderError(f'{po.reference} is not a draft (it is “{po.get_status_display()}”).')
    po.status = 'sent'
    po.save(update_fields=['status'])


def cancel(po):
    if po.status == 'cancelled':
        raise PurchaseOrderError(f'{po.reference} is already cancelled.')
    if any(line.quantity_received > 0 for line in _lines(po)):
        raise PurchaseOrderError(
            f'{po.reference} has already received some stock, so it cannot be cancelled. '
            'Close it as partially received instead.'
        )
    po.status = 'cancelled'
    po.save(update_fields=['status'])


# ─── Emailing the supplier ────────────────────────────────────────────────────

def email_to_supplier(po, user):
    """
    Emails the purchase order to the supplier (see inventory/emails.py for what it
    says). Sending a draft is what "sending the order" means, so a draft becomes
    "sent"; an order that is already sent (or partly received) just goes out again,
    marked in the email as an updated copy.

    Returns the address it was sent to. Raises PurchaseOrderError — with a message
    written for staff — if it may not or could not be sent; nothing is changed then.
    """
    supplier = po.supplier
    if po.status == 'cancelled':
        raise PurchaseOrderError(f'{po.reference} is cancelled, so it can’t be emailed.')
    if is_settled(po):
        raise PurchaseOrderError(f'{po.reference} has been received in full — there is nothing left to order.')
    address = (supplier.email or '').strip()
    if not address:
        raise PurchaseOrderError(
            f'{supplier.name} has no email address on file. Add one on the supplier’s page, then try again.'
        )
    if not _lines(po):
        raise PurchaseOrderError(f'{po.reference} has no items yet — add what you are ordering first.')

    try:
        emails.send_purchase_order(po, user, address)
    except Exception as error:                                # noqa: BLE001 — SMTP, DNS, timeouts…: all mean "not sent"
        logger.exception('Purchase order %s could not be emailed to %s', po.reference, address)
        reason = f'{type(error).__name__}: {error}'[:160]
        raise PurchaseOrderError(
            f'The email to {supplier.name} ({address}) could not be sent — {reason}. '
            f'Nothing was changed; check the mail settings and try again.'
        ) from error

    po.emailed_at = timezone.now()
    changed = ['emailed_at']
    if po.status == 'draft':
        po.status = 'sent'
        changed.append('status')
    po.save(update_fields=changed)
    return address


# ─── What needs reordering ────────────────────────────────────────────────────

def suggested_quantity(item):
    """How much to order: the item's reorder quantity, or twice its reorder level."""
    return item.reorder_quantity or (item.reorder_points * 2)


@dataclass
class ReorderReport:
    """Low-stock items, sorted by what can be done about them."""
    to_order: list = field(default_factory=list)       # will go on a new PO
    on_order: list = field(default_factory=list)       # already on an open PO
    no_supplier: list = field(default_factory=list)    # nobody to order from yet
    no_quantity: list = field(default_factory=list)    # no reorder quantity set

    @property
    def low_total(self):
        return len(self.to_order) + len(self.on_order) + len(self.no_supplier) + len(self.no_quantity)


def reorder_report():
    """
    Every item at or under its reorder level, and whether a PO can/should be
    made for it. The Purchase Orders banner and the Auto-Generate button both
    read this, so the number shown is the number that gets acted on.
    """
    report = ReorderReport()
    on_order = outstanding_by_item()
    low = Inventory.objects.filter(quantity_on_hand__lte=F('reorder_points')).select_related('supplier')
    for item in low:
        if item.supplier_id is None:
            report.no_supplier.append(item)
        elif on_order.get(item.pk, ZERO) > 0:
            report.on_order.append(item)
        elif suggested_quantity(item) <= 0:
            report.no_quantity.append(item)
        else:
            report.to_order.append(item)
    return report

"""
Rules for stock movements that staff enter by hand — shared by the item page
and the Stock Movements form, so the two can never drift apart on what is
allowed.

(Movements written by the order system — usage / reversal — don't go through
here: an order can't be refused because the shelf count is off, so the model
just floors stock at 0 for those.)
"""
from decimal import Decimal

from .models import StockMovement

# Largest value Inventory.quantity_on_hand / StockMovement.quantity can hold
# (DecimalField max_digits=10, decimal_places=2); anything past it is a DB
# overflow — a 500 the moment it's saved.
MAX_STOCK = Decimal('99999999.99')


def show(quantity):
    """12.5 -> '12.50', 1000 -> '1,000.00' (how quantities read in messages)."""
    return f'{Decimal(quantity).quantize(Decimal("0.01")):,}'


def check_movement(inventory, movement_type, quantity):
    """
    Why staff can't record this movement (a message written for them), or None
    if it is fine. `quantity` is a positive Decimal already limited to 2 places.
    """
    if quantity <= 0:
        return 'Quantity must be greater than 0.'
    if quantity > MAX_STOCK:
        return 'That quantity is too large.'
    if movement_type in StockMovement.STOCK_IN:
        if inventory.quantity_on_hand + quantity > MAX_STOCK:
            return 'That quantity is too large.'
    elif quantity > inventory.quantity_on_hand:
        return f'Only {show(inventory.quantity_on_hand)} {inventory.unit} on hand — you can’t take out {show(quantity)}.'
    return None

"""Small builders for the inventory tests (not a test module: no tests here)."""
from decimal import Decimal

from inventory.models import Inventory, InventoryCategory, PurchaseOrder, PurchaseOrderItem, Supplier


def make_supplier(name='Kent Acabo'):
    return Supplier.objects.get_or_create(name=name)[0]


def make_item(name='Espresso Beans', sku=None, unit='kg', on_hand='10', reorder='2', reorder_qty='10',
              cost='350', supplier=None, category='Beans', **extra):
    return Inventory.objects.create(
        category=InventoryCategory.objects.get_or_create(name=category)[0],
        supplier=supplier, name=name, sku=sku or name.upper().replace(' ', '-')[:20], unit=unit,
        quantity_on_hand=Decimal(on_hand), reorder_points=Decimal(reorder),
        reorder_quantity=Decimal(reorder_qty), cost_per_unit=Decimal(cost), **extra,
    )


def make_po(supplier, lines, status='draft', reference=None, **extra):
    """lines: [(item, ordered, received=0, unit_cost=None)]"""
    po = PurchaseOrder.objects.create(
        supplier=supplier, status=status,
        reference=reference or f'PO-TEST-{PurchaseOrder.objects.count() + 1:04d}', **extra,
    )
    for item, ordered, *rest in lines:
        received = rest[0] if rest else 0
        cost = rest[1] if len(rest) > 1 else item.cost_per_unit
        PurchaseOrderItem.objects.create(
            purchase_order=po, inventory=item, quantity_ordered=Decimal(str(ordered)),
            quantity_received=Decimal(str(received)), unit_cost=Decimal(str(cost)),
        )
    return po

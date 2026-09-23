import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from online_shop.models import Product
from decimal import Decimal

from . import units



class Supplier(models.Model):
    # A supplier here is a company, not an individual — contact_name is just
    # who to reach there, and is optional since not every supplier gives one.
    name         = models.CharField(max_length=200, help_text="Company / business name.")
    contact_name = models.CharField(max_length=100, blank=True, help_text="Person to reach at this supplier, if any.")
    email        = models.EmailField(blank=True)
    phone        = models.CharField(max_length=30, blank=True)
    website      = models.URLField(blank=True, help_text="The supplier's official website, if they have one.")
    social       = models.URLField(blank=True, help_text="The supplier's social account (fb, ig, tiktok)")
    address      = models.TextField(blank=True)
    notes        = models.TextField(blank=True)
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"

    def __str__(self):
        return self.name


class Inventory(models.Model):
    supplier          = models.ForeignKey(
                            Supplier,
                            on_delete=models.SET_NULL,
                            null=True, blank=True,
                            related_name="items",
                        )
    name              = models.CharField(max_length=250)
    sku               = models.CharField(max_length=20, unique=True)
    unit              = models.CharField(max_length=20)
    quantity_on_hand  = models.DecimalField(
                            max_digits=10, decimal_places=2,
                            default=0.00,
                            validators=[MinValueValidator(0)],
                        )
    quantity_reserved = models.DecimalField(
                            max_digits=10, decimal_places=2,
                            default=0.00,
                            validators=[MinValueValidator(0)],
                        )
    reorder_points    = models.DecimalField(
                            max_digits=10, decimal_places=2,
                            default=0.00,
                            validators=[MinValueValidator(0)],
                        )
    reorder_quantity  = models.DecimalField(
                            max_digits=10, decimal_places=2,
                            default=0.00,
                            validators=[MinValueValidator(0)],
                        )
    cost_per_unit     = models.DecimalField(
                            max_digits=10, decimal_places=2,
                            default=0.00,
                            validators=[MinValueValidator(0)],
                        )
    expiry_date       = models.DateField(             # ← DAGDAG
                            null=True, blank=True,
                            help_text="Expiry date ng item (kung applicable)"
                        )
    last_updated      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Inventory Item"
        verbose_name_plural = "Inventory Items"
        indexes = [
            models.Index(fields=["sku"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def quantity_available(self):
        return self.quantity_on_hand - self.quantity_reserved

    @property
    def is_low_stock(self):
        return self.quantity_on_hand <= self.reorder_points

    @property
    def is_expired(self):                             # ← DAGDAG
        if self.expiry_date:
            from django.utils import timezone
            return self.expiry_date < timezone.now().date()
        return False

    @property
    def stock_value(self):
        return self.quantity_on_hand * self.cost_per_unit


class StockMovement(models.Model):
    # The direction is spelled out in each label ("Stock In — …" / "Stock Out — …")
    # so nobody has to remember which of the seven adds and which removes.
    MOVEMENT_TYPES = (
        ("purchase",   "Stock In — Purchase / Delivery"),
        ("usage",      "Stock Out — Used in Orders (automatic)"),
        ("adjustment", "Stock Out — Manual Adjustment"),
        ("spoilage",   "Stock Out — Spoilage / Waste"),
        ("return",     "Stock Out — Return to Supplier"),
        ("transfer",   "Stock In — Transfer"),
        ("reversal",   "Stock In — Order Cancelled (automatic)"),
    )
    # Which way each type moves stock. "return" is *to* the supplier, so it
    # takes stock out (it used to be counted as stock in).
    STOCK_IN  = frozenset({"purchase", "transfer", "reversal"})
    STOCK_OUT = frozenset({"usage", "spoilage", "adjustment", "return"})
    # What staff can record by hand. "usage" and "reversal" are written by the
    # order system, and "transfer" has no destination to make sense of.
    MANUAL_TYPES = ("purchase", "adjustment", "spoilage", "return")

    inventory       = models.ForeignKey(
                          Inventory,
                          on_delete=models.CASCADE,
                          related_name="movements",
                      )
    movement_type   = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity        = models.DecimalField(
                          max_digits=10, decimal_places=2,
                          validators=[MinValueValidator(0)],
                      )
    quantity_change = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_cost       = models.DecimalField(
                          max_digits=10, decimal_places=2,
                          default=0.00,
                          validators=[MinValueValidator(0)],
                      )
    reference       = models.CharField(max_length=100, blank=True,
                                       help_text="PO number, invoice number, etc.")
    notes           = models.TextField(blank=True)
    performed_by = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            on_delete=models.SET_NULL,
            null=True, blank=True,
            related_name="stock_movements",
            limit_choices_to={'is_staff': True},  # ← dagdag ito
        )
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Stock Movement"
        verbose_name_plural = "Stock Movements"
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["inventory", "movement_type"]),
        ]

    def save(self, *args, apply_to_stock=True, **kwargs):
        # This is the ONLY place that should ever touch quantity_on_hand for
        # a movement — callers must not also pre-adjust it themselves before
        # creating a StockMovement, or the change gets applied twice.
        #
        # It does so exactly once, when the movement is *created*. Movements are
        # a history: saving an existing one again (a note edited in a shell, a
        # re-save) used to re-apply quantity_change and push stock by that
        # amount a second time.
        creating = self._state.adding
        if creating:
            self.quantity_change = self.quantity if self.movement_type in self.STOCK_IN else -self.quantity
        super().save(*args, **kwargs)
        # apply_to_stock=False is for the one case where the stock is already
        # there and only the record is missing: an item added with an opening
        # quantity (the movement documents it; applying it again would double it).
        if not creating or not apply_to_stock:
            return
        # Floor at 0 at the DB level (F-expression, race-safe) — physical
        # stock can't go negative even if usage exceeds what's on hand.
        from django.db.models.functions import Greatest
        self.inventory.quantity_on_hand = Greatest(
            models.F("quantity_on_hand") + self.quantity_change,
            Decimal("0"),
        )
        self.inventory.save(update_fields=["quantity_on_hand", "last_updated"])

    def __str__(self):
        sign = "+" if self.quantity_change >= 0 else ""
        return (f"{self.inventory.name} | {self.get_movement_type_display()} | "
                f"{sign}{self.quantity_change} {self.inventory.unit}")


class PurchaseOrder(models.Model):
    STATUS_CHOICES = (
        ("draft",     "Draft"),
        ("sent",      "Sent to Supplier"),
        ("partial",   "Partially Received"),
        ("received",  "Fully Received"),
        ("cancelled", "Cancelled"),
    )

    supplier    = models.ForeignKey(
                      Supplier,
                      on_delete=models.PROTECT,
                      related_name="purchase_orders",
                  )
    status      = models.CharField(
                      max_length=20,
                      choices=STATUS_CHOICES,
                      default="draft",
                      db_index=True,
                  )
    # Never typed — numbered from this row's own id the moment it exists (see
    # save() below) and shown read-only after that (PurchaseOrderAdmin).
    reference   = models.CharField(max_length=100, unique=True, verbose_name="PO number",
                                   help_text="Numbered automatically from the order's own id, e.g. PO-000042.")
    ordered_at  = models.DateTimeField(auto_now_add=True)
    expected_at = models.DateField(null=True, blank=True)
    received_at = models.DateField(null=True, blank=True)
    # When staff last emailed this order to the supplier (set by purchasing.email_to_supplier;
    # never typed in, so it is not on any form).
    emailed_at  = models.DateTimeField(null=True, blank=True, editable=False)
    notes       = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="purchase_orders",
        limit_choices_to={'is_staff': True},  # ← dagdag ito
    )

    class Meta:
        ordering = ("-ordered_at",)
        verbose_name = "Purchase Order"
        verbose_name_plural = "Purchase Orders"

    # A short-lived placeholder a brand-new, still-blank order gets for the one save
    # this column can't do without a value (required + unique). Different every time
    # (so two staff members creating an order at the same moment can never collide on
    # it), and never seen past that one save — the real number replaces it immediately
    # after, in save() below.
    _PENDING_PREFIX = 'PO-PENDING-'

    def save(self, *args, **kwargs):
        # A blank reference is numbered from this row's own id (see
        # inventory.purchasing.reference_for — the one place that format lives). A
        # brand-new row's id doesn't exist until it has been saved once, so that
        # case takes two saves: the placeholder above holds the column the first
        # time, then the real number replaces it now that there is an id to build
        # it from. An existing row already has its id, so blanking one out (staff
        # clearing the field on an order that already exists) numbers it in the one
        # save. A reference that's already there — typed by staff, or already
        # numbered — is left exactly alone, and this is just an ordinary save().
        if self.reference:
            return super().save(*args, **kwargs)
        from . import purchasing                                  # local: purchasing.py imports this module
        if self._state.adding:
            self.reference = f'{self._PENDING_PREFIX}{uuid.uuid4().hex}'
            super().save(*args, **kwargs)
            self.reference = purchasing.reference_for(self)
            return super().save(update_fields=['reference'])
        self.reference = purchasing.reference_for(self)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} — {self.supplier.name} ({self.get_status_display()})"

    @property
    def total_cost(self):
        return sum(item.total_cost for item in self.items.all())


class PurchaseOrderItem(models.Model):
    purchase_order    = models.ForeignKey(
                            PurchaseOrder,
                            on_delete=models.CASCADE,
                            related_name="items",
                        )
    inventory         = models.ForeignKey(
                            Inventory,
                            on_delete=models.PROTECT,
                            related_name="po_items",
                        )
    quantity_ordered  = models.DecimalField(
                            max_digits=10, decimal_places=2,
                            validators=[MinValueValidator(0)],
                        )
    quantity_received = models.DecimalField(
                            max_digits=10, decimal_places=2,
                            default=0.00,
                            validators=[MinValueValidator(0)],
                        )
    unit_cost         = models.DecimalField(
                            max_digits=10, decimal_places=2,
                            validators=[MinValueValidator(0)],
                        )

    class Meta:
        ordering = ("inventory__name",)
        verbose_name = "Purchase Order Item"
        verbose_name_plural = "Purchase Order Items"
        unique_together = (("purchase_order", "inventory"),)

    def __str__(self):
        return (f"{self.purchase_order.reference} — "
                f"{self.inventory.name} x {self.quantity_ordered}")

    @property
    def total_cost(self):
        return self.quantity_ordered * self.unit_cost

    @property
    def is_fully_received(self):
        return self.quantity_received >= self.quantity_ordered


class Ingredient(models.Model):
    product   = models.ForeignKey(
                    Product,
                    on_delete=models.CASCADE,
                    related_name="ingredients",
                )
    inventory = models.ForeignKey(
                    Inventory,
                    on_delete=models.CASCADE,
                    related_name="used_in",
                )
    quantity  = models.DecimalField(
                    max_digits=10, decimal_places=2,
                    validators=[MinValueValidator(0)],
                )
    unit      = models.CharField(
                    max_length=20,
                    help_text="Can be written in a different metric unit than the inventory item "
                               "itself (e.g. ml for an item tracked in L) — it's converted automatically.",
                )
    notes     = models.TextField(blank=True)

    class Meta:
        ordering = ("product__name", "inventory__name")
        verbose_name = "Ingredient"
        verbose_name_plural = "Ingredients"
        unique_together = (("product", "inventory"),)

    def clean(self):
        # Only an error when both units are ones inventory.units actually
        # recognizes and they're not the same kind of measurement (weight vs
        # volume — there's no converting one into the other). A count-style
        # unit like "pcs" on either side is left alone, same as always.
        if self.unit and self.inventory_id and self.inventory.unit:
            from_family = units.family_of(self.unit)
            to_family = units.family_of(self.inventory.unit)
            if from_family and to_family and from_family != to_family:
                raise ValidationError({
                    'unit': f'"{self.unit}" ({from_family}) can’t be converted to '
                            f'"{self.inventory.unit}" ({to_family}), the inventory item’s unit.',
                })

    def __str__(self):
        return (f"{self.product.name} — "
                f"{self.inventory.name} ({self.quantity} {self.unit})")
    
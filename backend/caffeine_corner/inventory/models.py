from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from online_shop.models import Product
from decimal import Decimal


class InventoryCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Inventory Category"
        verbose_name_plural = "Inventory Categories"

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name         = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=100, blank=True)
    email        = models.EmailField(blank=True)
    phone        = models.CharField(max_length=30, blank=True)
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
    category          = models.ForeignKey(
                            InventoryCategory,
                            on_delete=models.PROTECT,
                            related_name="items",
                        )
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
        ordering = ("category", "name")
        verbose_name = "Inventory Item"
        verbose_name_plural = "Inventory Items"
        indexes = [
            models.Index(fields=["sku"]),
            models.Index(fields=["category", "name"]),
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
    MOVEMENT_TYPES = (
        ("purchase",   "Purchase (Stock In)"),
        ("usage",      "Usage (Stock Out)"),
        ("adjustment", "Manual Adjustment"),
        ("spoilage",   "Spoilage / Waste"),
        ("return",     "Return to Supplier"),
        ("transfer",   "Transfer"),
    )

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
    performed_by    = models.ForeignKey(           # ← FIXED
                          settings.AUTH_USER_MODEL,
                          on_delete=models.SET_NULL,
                          null=True, blank=True,
                          related_name="stock_movements",
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

    def save(self, *args, **kwargs):
        STOCK_IN  = {"purchase", "return", "transfer"}
        STOCK_OUT = {"usage", "spoilage", "adjustment"}
        if self.movement_type in STOCK_IN:
            self.quantity_change = self.quantity
        else:
            self.quantity_change = -self.quantity
        super().save(*args, **kwargs)
        self.inventory.quantity_on_hand = (
            models.F("quantity_on_hand") + self.quantity_change
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
    reference   = models.CharField(max_length=100, unique=True,
                                   help_text="PO number e.g. PO-2026-0001")
    ordered_at  = models.DateTimeField(auto_now_add=True)
    expected_at = models.DateField(null=True, blank=True)
    received_at = models.DateField(null=True, blank=True)
    notes       = models.TextField(blank=True)
    created_by  = models.ForeignKey(           # ← FIXED
                      settings.AUTH_USER_MODEL,
                      on_delete=models.SET_NULL,
                      null=True, blank=True,
                      related_name="purchase_orders",
                  )

    class Meta:
        ordering = ("-ordered_at",)
        verbose_name = "Purchase Order"
        verbose_name_plural = "Purchase Orders"

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
    unit      = models.CharField(max_length=20)
    notes     = models.TextField(blank=True)

    class Meta:
        ordering = ("product__name", "inventory__name")
        verbose_name = "Ingredient"
        verbose_name_plural = "Ingredients"
        unique_together = (("product", "inventory"),)

    def __str__(self):
        return (f"{self.product.name} — "
                f"{self.inventory.name} ({self.quantity} {self.unit})")
    
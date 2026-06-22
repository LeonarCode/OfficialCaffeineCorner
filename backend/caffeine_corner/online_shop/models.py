from decimal import Decimal

from django.db import models

# Create your models here.
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.forms import ValidationError

# Products
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    sort_order = models.IntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    sku = models.CharField(max_length=20, unique=True)
    barcode = models.CharField(max_length=150, db_index=True)
    image = models.ImageField(upload_to="product_images/", blank=True, max_length=255)
    sort_order = models.IntegerField(default=0, db_index=True)
    is_available = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_seasonal = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name", "-created_at")
        verbose_name = "Product"
        verbose_name_plural = "Products"
        indexes = [
            models.Index(fields=["sort_order", "name"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["is_available", "is_featured", "is_seasonal"]),
        ]

    @property
    def average_rating(self):
        ratings = self.ratings.all()
        if ratings.exists():
            return round(sum(r.rating for r in ratings) / ratings.count(), 1)
        return None

    @property
    def stock_available(self):
        if hasattr(self, 'stock_item') and self.stock_item:
            return self.stock_item.quantity_available
        return 0

    def __str__(self):
        return f"{self.name} ({self.sku})"


class Variant(models.Model):
    SIZE_CHOICES = (
        ("small", "Small"),
        ("medium", "Medium"),
        ("large", "Large"),
    )
    product          = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size             = models.CharField(max_length=20, choices=SIZE_CHOICES)
    additional_price = models.DecimalField(
                           max_digits=10, decimal_places=2,
                           default=Decimal("0.00"),
                           validators=[MinValueValidator(0)],
                       )
    sku              = models.CharField(max_length=20, blank=True, default='')   # ← blank=True
    barcode          = models.CharField(max_length=150, blank=True, default='')  # ← blank=True

    class Meta:
        ordering = ("product", "size")
        verbose_name = "Variant"
        verbose_name_plural = "Variants"

    @property
    def stock_available(self):
        if hasattr(self, 'variant_stock') and self.variant_stock:
            return self.variant_stock.quantity_available
        return 0

    def __str__(self):
        return f"{self.product.name} - {self.size}"


class Rating(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_user_product_rating"),
        ]
        ordering = ("-created_at",)
        verbose_name = "Rating"
        verbose_name_plural = "Ratings"

    def __str__(self):
        return f"{self.product.name} - {self.rating} stars by {self.user.username}"


class Order(models.Model):
    ORDER_TYPE_CHOICES = [
        ('regular', 'Regular'),
        ('bulk',    'Bulk / Catering'),
        ('dine_in', 'Dine-in'),
    ]
    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('confirmed',  'Confirmed'),
        ('processing', 'Processing'),
        ('delivered',  'Delivered'),
        ('cancelled',  'Cancelled'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('cod',   'Cash on Delivery'),
        ('gcash', 'GCash'),
        ('counter', 'Pay at Counter'), 
    ]
    PAYMENT_STATUS_CHOICES = [
        ('unpaid',   'Unpaid'),
        ('downpayment', 'Downpayment Paid'),
        ('paid',     'Paid'),
        ('failed',   'Failed'),
        ('refunded', 'Refunded'),
    ]

    # Who ordered
    user           = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    email          = models.EmailField()
    address        = models.TextField()
    notes          = models.TextField(blank=True, default='')
    order_type          = models.CharField(max_length=10, choices=ORDER_TYPE_CHOICES, default='regular')
    downpayment_amount  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remaining_balance   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    event_date          = models.DateField(null=True, blank=True, help_text="Para sa bulk/catering orders")
    pax                 = models.PositiveIntegerField(default=0, help_text="Number of persons")

    # Status
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Payment
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='cod')
    payment_status = models.CharField(max_length=15, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    gcash_ref      = models.CharField(max_length=100, blank=True, default='')
    paymongo_id    = models.CharField(max_length=100, blank=True, default='')

    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)
    points_earned = models.PositiveIntegerField(default=0)
    points_used   = models.PositiveIntegerField(default=0)
    discount      = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    table_number = models.CharField(max_length=10, blank=True, default='')

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'

    def __str__(self):
        name = self.user.username if self.user else self.email
        return f"Order #{self.id} — {name}"

    @property
    def total_price(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())


class OrderItem(models.Model):
    order    = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product  = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant  = models.ForeignKey(Variant, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    price    = models.DecimalField(max_digits=10, decimal_places=2)  # snapshot price at time of order

    class Meta:
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity

class CartItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(9999)])

    class Meta:
        unique_together = (("user", "product", "variant"),)
        ordering = ("user", "product", "variant")
        verbose_name = "Cart item"
        verbose_name_plural = "Cart items"
        indexes = [
            models.Index(fields=["user", "product"]),
        ]

    def __str__(self):
        if self.variant:
            return f"{self.user.username} - {self.product.name} ({self.variant.size}) x {self.quantity}"
        return f"{self.user.username} - {self.product.name} x {self.quantity}"

    def clean(self):
        # Optional: enforce app-level uniqueness for (user, product) when variant is NULL
        if self.variant is None and self.user_id and self.product_id:
            existing = CartItem.objects.filter(user_id=self.user_id, product_id=self.product_id, variant__isnull=True)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                from django.core.exceptions import ValidationError
                raise ValidationError("A cart item for this product without a variant already exists for this user.")

    @property
    def subtotal(self):
        return self.product.price * self.quantity


class LoyaltyPoint(models.Model):
    user         = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="loyalty")
    points       = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering     = ("-last_updated",)
        verbose_name = "Loyalty point"
        verbose_name_plural = "Loyalty points"

    def __str__(self):
        return f"{self.user.username} - {self.points} points"

    def earn(self, total_amount):
        """1 point per ₱10 spent."""
        earned      = int(total_amount // 10)
        self.points += earned
        self.save()
        return earned

    def redeem(self, points_to_use):
        """100 points = ₱10 discount."""
        if points_to_use > self.points:
            raise ValueError("Hindi sapat ang points!")
        if points_to_use % 100 != 0:
            raise ValueError("Multiples of 100 lang ang pwedeng i-redeem!")
        discount     = (points_to_use // 100) * 10
        self.points -= points_to_use
        self.save()
        return discount

    @property
    def discount_value(self):
        """Kung ire-redeem lahat ng points, magkano ang discount."""
        return (self.points // 100) * 10

    @property
    def redeemable_points(self):
        """Pinaka-maraming points na pwedeng i-redeem (multiple of 100)."""
        return (self.points // 100) * 100
    
class Notification(models.Model):
    TYPE_CHOICES = [
        ('new_order',    'New Order'),
        ('bulk_order',   'Bulk Order'),
        ('low_stock',    'Low Stock'),
        ('payment_paid', 'Payment Paid'),
    ]

    type       = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title      = models.CharField(max_length=200)
    message    = models.TextField()
    is_read    = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    order      = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f'{self.title} — {self.created_at.strftime("%b %d, %Y")}'
    
class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('order_created',   'Order Created'),
        ('order_updated',   'Order Updated'),
        ('order_cancelled', 'Order Cancelled'),
        ('payment_paid',    'Payment Paid'),
        ('product_created', 'Product Created'),
        ('product_updated', 'Product Updated'),
        ('user_login',      'User Login'),
        ('stock_movement',  'Stock Movement'),
    ]

    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action     = models.CharField(max_length=30, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=50, blank=True)
    object_id  = models.PositiveIntegerField(null=True, blank=True)
    details    = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'

    def __str__(self):
        user = self.user.email if self.user else 'System'
        return f'{user} — {self.get_action_display()} — {self.created_at.strftime("%b %d, %Y %H:%M")}'

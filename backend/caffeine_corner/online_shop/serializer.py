from datetime import timedelta

from rest_framework import serializers
from .models import Category, Product, Variant, Rating, Order, OrderItem, CartItem, LoyaltyPoint, TownZone, VALID_TABLE_NUMBERS
from . import rider_availability
import re


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'sort_order', 'is_active']


class VariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variant
        fields = ['id', 'size', 'additional_price', 'sku', 'stock_available']


class RatingSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_initial = serializers.SerializerMethodField()

    class Meta:
        model = Rating
        fields = ['id', 'user_email', 'user_initial', 'rating', 'review', 'created_at']
        read_only_fields = ['user_email', 'user_initial', 'created_at']

    def get_user_initial(self, obj):
        return obj.user.email[0].upper() if obj.user.email else '?'


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    variants = VariantSerializer(many=True, read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    stock_available = serializers.IntegerField(read_only=True)
    rating_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'category', 'category_name',
            'price', 'sku', 'image', 'sort_order',
            'is_available', 'is_featured', 'is_seasonal',
            'variants', 'average_rating', 'rating_count',
            'stock_available', 'created_at',
        ]

    def get_rating_count(self, obj):
        return obj.ratings.count()

class TownZoneSerializer(serializers.ModelSerializer):
    has_available_rider = serializers.SerializerMethodField()

    class Meta:
        model  = TownZone
        fields = ['id', 'name', 'delivery_fee', 'estimated_time', 'center_latitude', 'center_longitude',
                  'has_available_rider']

    def get_has_available_rider(self, obj):
        return rider_availability.zone_has_available_rider(obj)


class MarkDeliveredSerializer(serializers.Serializer):
    delivery_proof_photo = serializers.ImageField(required=True)
    payment_received      = serializers.BooleanField(default=False)
    rider_notes            = serializers.CharField(required=False, allow_blank=True, default='')

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_image = serializers.ImageField(source='product.image', read_only=True)
    variant_size = serializers.CharField(source='variant.size', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_image', 'variant', 'variant_size', 'quantity', 'price', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    items       = OrderItemSerializer(many=True, read_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    subtotal    = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    item_count  = serializers.IntegerField(read_only=True)
    zone_name   = serializers.CharField(source='zone.name', read_only=True, default=None)
    zone_estimated_time = serializers.CharField(source='zone.estimated_time', read_only=True, default=None)
    expected_ready_at = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'email', 'phone', 'address', 'notes',  # ← dagdag phone
            'status', 'payment_method', 'payment_status',
            'order_type', 'downpayment_amount', 'remaining_balance',
            'event_date', 'pax', 'table_number',
            'zone', 'zone_name', 'zone_estimated_time', 'delivery_fee',
            'gcash_ref', 'discount', 'points_earned', 'points_used',
            'items', 'subtotal', 'total_price', 'item_count',
            'created_at', 'updated_at', 'delivery_latitude', 'delivery_longitude',
            'expected_ready_at',
        ]
        read_only_fields = ['status', 'payment_status', 'points_earned', 'created_at', 'updated_at']

    def get_expected_ready_at(self, obj):
        # Only meaningful while the order is still on its way — once it's
        # delivered or cancelled there's nothing left to be "expected".
        if obj.status in ('delivered', 'cancelled'):
            return None
        return obj.created_at + timedelta(minutes=rider_availability.production_minutes_for(obj))


class CreateOrderSerializer(serializers.Serializer):
    email          = serializers.EmailField()
    # Required for regular (delivery) and pickup orders — enforced below in
    # validate(), since that's the only place order_type is known too.
    # Optional for dine_in: the customer is already physically at the
    # counter/table, so a phone number doesn't carry the same "how do we
    # reach them" weight it does for delivery/pickup. allow_blank so it can
    # be left out entirely; still runs through validate_phone's format
    # check if they do type one in, blank or not.
    phone          = serializers.CharField(max_length=15, required=False, allow_blank=True, default='')
    address        = serializers.CharField(required=False, allow_blank=True, default='')
    notes          = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(choices=['cod', 'gcash', 'counter'])
    points_to_use  = serializers.IntegerField(required=False, default=0)
    items          = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    order_type = serializers.ChoiceField(
        choices=['regular', 'dine_in', 'pickup'],  # ← dagdag pickup
        default='regular'
    )
    event_date     = serializers.DateField(required=False, allow_null=True)
    pax            = serializers.IntegerField(required=False, default=0)
    table_number   = serializers.CharField(required=False, allow_blank=True, default='')
    zone_id        = serializers.IntegerField(required=False, allow_null=True)
    delivery_latitude  = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    delivery_longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)

    def validate_phone(self, value):
        # Blank is allowed through here regardless of order_type — DRF calls
        # validate_phone() even for a blank value (allow_blank doesn't skip
        # it), and whether blank is actually OK depends on order_type, which
        # isn't available yet at this per-field stage. That decision is
        # validate()'s job below, once every field's cleaned value is in.
        if not value:
            return value

        # Alisin ang spaces, dashes
        cleaned = re.sub(r'[\s\-]', '', value)

        # Philippine mobile format: 09XXXXXXXXX (11 digits) or +639XXXXXXXXX
        pattern = r'^(09\d{9}|\+639\d{9})$'
        if not re.match(pattern, cleaned):
            raise serializers.ValidationError(
                'Please enter a valid Philippine mobile number (e.g. 09171234567).'
            )
        return cleaned

    def validate(self, attrs):
        order_type = attrs.get('order_type', 'regular')

        # Dine-in customers are already physically at the table/counter, so
        # phone isn't required there — but delivery (regular) and pickup
        # orders still strictly need it (it's the main way to reach that
        # customer if something's off with the order).
        if order_type != 'dine_in' and not attrs.get('phone'):
            raise serializers.ValidationError({'phone': 'Phone number is required for this order type.'})

        # The phone exception above only makes sense because a dine-in order
        # is tied to a real, physical table — DineInMenu always sends one
        # (read straight from the QR-scanned URL, see frontend DineInMenu.jsx).
        # Without this check, order_type is otherwise just a client-supplied
        # field: anyone calling the API directly could set order_type to
        # dine_in purely to skip the phone requirement above, landing a
        # completely anonymous order tied to no table and no contact info.
        if order_type == 'dine_in' and attrs.get('table_number') not in VALID_TABLE_NUMBERS:
            raise serializers.ValidationError({'table_number': 'A valid table number is required for dine-in orders.'})

        # A dine-in order is paid at the counter or with GCash. "Cash on delivery" has no
        # meaning at a table, and would only put a nonsense payment method on the record.
        if order_type == 'dine_in' and attrs.get('payment_method') not in ('counter', 'gcash'):
            raise serializers.ValidationError({'payment_method': 'Dine-in orders are paid at the counter or with GCash.'})

        return attrs


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_image = serializers.ImageField(source='product.image', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    variant_size = serializers.CharField(source='variant.size', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_name', 'product_image', 'product_price', 'variant', 'variant_size', 'quantity', 'subtotal']
        read_only_fields = ['subtotal']


class RiderOrderSerializer(serializers.ModelSerializer):
    items          = OrderItemSerializer(many=True, read_only=True)
    total_price    = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    zone_name      = serializers.CharField(source='zone.name', read_only=True, default=None)
    customer_name  = serializers.SerializerMethodField()  # ← dagdag

    class Meta:
        model  = Order
        fields = [
            'id', 'email', 'phone', 'address', 'notes', 'customer_name',  # ← dagdag customer_name
            'status', 'payment_method', 'payment_status',
            'order_type', 'zone_name', 'delivery_fee',
            'items', 'total_price',
            'delivery_proof_photo', 'delivered_at', 'rider_notes',
            'delivery_latitude', 'delivery_longitude',
            'created_at',
        ]

    def get_customer_name(self, obj):
        if obj.user and obj.user.username:
            return obj.user.username
        return obj.email.split('@')[0]  # fallback — gamitin ang email prefix kung walang username


class MarkDeliveredSerializer(serializers.Serializer):
    delivery_proof_photo = serializers.ImageField(required=True)
    payment_received      = serializers.BooleanField(default=False)
    rider_notes            = serializers.CharField(required=False, allow_blank=True, default='')

class LoyaltyPointSerializer(serializers.ModelSerializer):
    discount_value = serializers.IntegerField(read_only=True)
    redeemable_points = serializers.IntegerField(read_only=True)

    class Meta:
        model = LoyaltyPoint
        fields = ['points', 'discount_value', 'redeemable_points', 'last_updated']
from rest_framework import serializers
from .models import Category, Product, Variant, Rating, Order, OrderItem, CartItem, LoyaltyPoint, TownZone


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
    class Meta:
        model = TownZone
        fields = ['id', 'name', 'delivery_fee', 'min_order_amount', 'estimated_time']

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
    subtotal    = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)  # ← dagdag
    item_count  = serializers.IntegerField(read_only=True)
    zone_name   = serializers.CharField(source='zone.name', read_only=True, default=None)  # ← dagdag

    class Meta:
        model = Order
        fields = [
            'id', 'email', 'address', 'notes',
            'status', 'payment_method', 'payment_status',
            'order_type', 'downpayment_amount', 'remaining_balance',
            'event_date', 'pax', 'table_number',
            'zone', 'zone_name', 'delivery_fee',  # ← dagdag
            'gcash_ref', 'discount', 'points_earned', 'points_used',
            'items', 'subtotal', 'total_price', 'item_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['status', 'payment_status', 'points_earned', 'created_at', 'updated_at']


class CreateOrderSerializer(serializers.Serializer):
    email          = serializers.EmailField()
    address        = serializers.CharField(required=False, allow_blank=True, default='')
    notes          = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(choices=['cod', 'gcash', 'counter'])
    points_to_use  = serializers.IntegerField(required=False, default=0)
    items          = serializers.ListField(
                         child=serializers.DictField(),
                         required=False,
                         default=list
                     )
    order_type     = serializers.ChoiceField(choices=['regular', 'bulk', 'dine_in'], default='regular')
    event_date     = serializers.DateField(required=False, allow_null=True)
    pax            = serializers.IntegerField(required=False, default=0)
    table_number   = serializers.CharField(required=False, allow_blank=True, default='')
    zone_id        = serializers.IntegerField(required=False, allow_null=True)  # ← dagdag


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


class LoyaltyPointSerializer(serializers.ModelSerializer):
    discount_value = serializers.IntegerField(read_only=True)
    redeemable_points = serializers.IntegerField(read_only=True)

    class Meta:
        model = LoyaltyPoint
        fields = ['points', 'discount_value', 'redeemable_points', 'last_updated']
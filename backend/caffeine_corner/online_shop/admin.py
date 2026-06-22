from django.contrib import admin

# Register your models here.
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline, format_html, mark_safe
from .models import ActivityLog, Category, Product, Variant, Rating, Order, OrderItem, CartItem, LoyaltyPoint, Notification
from unfold.decorators import action


@admin.action(description='✅ Mark as Confirmed')
def mark_confirmed(modeladmin, request, queryset):
    updated = queryset.exclude(status='cancelled').update(status='confirmed')
    modeladmin.message_user(request, f'{updated} order(s) marked as Confirmed.')

@admin.action(description='☕ Mark as Processing')
def mark_processing(modeladmin, request, queryset):
    updated = queryset.exclude(status='cancelled').update(status='processing')
    modeladmin.message_user(request, f'{updated} order(s) marked as Processing.')

@admin.action(description='🎉 Mark as Delivered')
def mark_delivered(modeladmin, request, queryset):
    updated = queryset.exclude(status='cancelled').update(status='delivered')
    modeladmin.message_user(request, f'{updated} order(s) marked as Delivered.')

@admin.action(description='❌ Mark as Cancelled')
def mark_cancelled(modeladmin, request, queryset):
    updated = queryset.update(status='cancelled')
    modeladmin.message_user(request, f'{updated} order(s) marked as Cancelled.')

@admin.action(description='💰 Mark Payment as Paid')
def mark_payment_paid(modeladmin, request, queryset):
    updated = queryset.update(payment_status='paid')
    modeladmin.message_user(request, f'{updated} order(s) marked as Paid.')

@admin.action(description='⏳ Mark Payment as Unpaid')
def mark_payment_unpaid(modeladmin, request, queryset):
    updated = queryset.update(payment_status='unpaid')
    modeladmin.message_user(request, f'{updated} order(s) marked as Unpaid.')


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display  = ['show_type', 'title', 'message', 'is_read', 'created_at', 'mark_read_link']
    list_filter   = ['type', 'is_read']
    search_fields = ['title', 'message']
    readonly_fields = ['type', 'title', 'message', 'order', 'created_at']
    ordering      = ['-created_at']

    TYPE_ICONS = {
        'new_order':    ('🛒', '#eaf5ed', '#2e7d4a'),
        'bulk_order':   ('🍽️', '#fff6e0', '#a06010'),
        'low_stock':    ('⚠️', '#fef0ee', '#c04a3a'),
        'payment_paid': ('✅', '#e6f0fa', '#1a5494'),
    }

    def show_type(self, obj):
        icon, bg, color = self.TYPE_ICONS.get(obj.type, ('📢', '#f1efe8', '#5f5e5a'))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;border-radius:5px;font-size:11px;font-weight:500;">{} {}</span>',
            bg, color, icon, obj.get_type_display()
        )
    show_type.short_description = 'Type'

    def mark_read_link(self, obj):
        if obj.is_read:
            return format_html('<span style="color:#9ca3af;font-size:11px;">✓ Read</span>')
        return format_html(
            '<a href="/admin/mark-notification-read/{}/" style="color:#6f4e37;font-size:11px;font-weight:600;">Mark as Read</a>',
            obj.id
        )
    mark_read_link.short_description = 'Action'

@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ['name', 'sort_order', 'is_active']
    list_editable = ['sort_order', 'is_active']
    search_fields = ['name']


class VariantInline(TabularInline):
    model = Variant
    extra = 0        # ← walang blank rows by default
    min_num = 0      # ← hindi required maglagay ng variant
    can_delete = True

@admin.register(Variant)
class VariantAdmin(ModelAdmin):
    list_display = ['product', 'size', 'additional_price', 'sku']
    list_filter = ['size']
    search_fields = ['product__name', 'sku']


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product', 'variant', 'quantity', 'price', 'get_subtotal']  # ← palitan subtotal ng get_subtotal

    def get_subtotal(self, obj):
        if obj.price and obj.quantity:
            return f'₱{obj.price * obj.quantity:.2f}'
        return '—'
    get_subtotal.short_description = 'Subtotal'


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_available', 'is_featured', 'is_seasonal', 'sort_order']
    list_editable = ['price', 'is_available', 'is_featured', 'is_seasonal', 'sort_order']
    list_filter = ['category', 'is_available', 'is_featured', 'is_seasonal']
    search_fields = ['name', 'sku']
    inlines = [VariantInline]


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display    = ['id', 'email', 'order_type', 'show_status', 'payment_method', 'show_payment_status', 'total_price', 'created_at', 'print_receipt_link']
    list_filter     = ['status', 'payment_method', 'payment_status', 'order_type']
    search_fields   = ['email', 'id']
    readonly_fields = ['total_price', 'item_count', 'points_earned', 'points_used', 'downpayment_amount', 'remaining_balance', 'created_at', 'updated_at']
    inlines         = [OrderItemInline]
    actions         = [
        mark_confirmed,
        mark_processing,
        mark_delivered,
        mark_cancelled,
        mark_payment_paid,
        mark_payment_unpaid,
    ]

    STATUS_COLORS = {
        'pending':    ('#fff6e0', '#a06010'),
        'confirmed':  ('#e6f0fa', '#1a5494'),
        'processing': ('#f3e8ff', '#7c3aed'),
        'delivered':  ('#eaf5ed', '#2e7d4a'),
        'cancelled':  ('#fef0ee', '#c04a3a'),
    }

    PAYMENT_COLORS = {
        'unpaid':      ('#fef0ee', '#c04a3a'),
        'downpayment': ('#fff6e0', '#a06010'),
        'paid':        ('#eaf5ed', '#2e7d4a'),
        'failed':      ('#fef0ee', '#c04a3a'),
        'refunded':    ('#f1efe8', '#5f5e5a'),
    }

    def show_status(self, obj):
        bg, fg = self.STATUS_COLORS.get(obj.status, ('#f1efe8', '#5f5e5a'))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;border-radius:5px;font-size:11px;font-weight:500;">{}</span>',
            bg, fg, obj.get_status_display()
        )
    show_status.short_description = 'Status'
    show_status.admin_order_field = 'status'

    def show_payment_status(self, obj):
        bg, fg = self.PAYMENT_COLORS.get(obj.payment_status, ('#f1efe8', '#5f5e5a'))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;border-radius:5px;font-size:11px;font-weight:500;">{}</span>',
            bg, fg, obj.get_payment_status_display()
        )
    
    def print_receipt_link(self, obj):
        return format_html(
            '<a href="/admin/orders/{}/receipt/" target="_blank" '
            'style="background:#2C1503; color:white; padding:4px 10px; '
            'border-radius:6px; font-size:11px; font-weight:600; text-decoration:none;">'
            '🖨️ Print</a>',
            obj.id
        )
    print_receipt_link.short_description = 'Receipt'
    show_payment_status.short_description = 'Payment Status'
    show_payment_status.admin_order_field = 'payment_status'



@admin.register(Rating)
class RatingAdmin(ModelAdmin):
    list_display = ['product', 'user', 'rating', 'created_at']
    list_filter = ['rating']
    search_fields = ['product__name', 'user__email']


@admin.register(CartItem)
class CartItemAdmin(ModelAdmin):
    list_display = ['user', 'product', 'variant', 'quantity']
    search_fields = ['user__email', 'product__name']


@admin.register(LoyaltyPoint)
class LoyaltyPointAdmin(ModelAdmin):
    list_display = ['user', 'points', 'discount_value', 'redeemable_points', 'last_updated']
    search_fields = ['user__email']
    readonly_fields = ['discount_value', 'redeemable_points', 'last_updated']

@admin.register(ActivityLog)
class ActivityLogAdmin(ModelAdmin):
    list_display  = ['created_at', 'show_action', 'show_user', 'model_name', 'object_id', 'details', 'ip_address']
    list_filter   = ['action', 'model_name', 'created_at']
    search_fields = ['details', 'user__email', 'ip_address']
    readonly_fields = ['user', 'action', 'model_name', 'object_id', 'details', 'ip_address', 'created_at']
    date_hierarchy = 'created_at'

    # No add/delete — logs only
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # only superuser can delete logs

    ACTION_COLORS = {
        'order_created':   ('#eaf5ed', '#2e7d4a'),
        'order_updated':   ('#e6f0fa', '#1a5494'),
        'order_cancelled': ('#fef0ee', '#c04a3a'),
        'payment_paid':    ('#eaf5ed', '#2e7d4a'),
        'product_created': ('#f3e8ff', '#7c3aed'),
        'product_updated': ('#e6f0fa', '#1a5494'),
        'user_login':      ('#fff6e0', '#a06010'),
        'stock_movement':  ('#f1efe8', '#5f5e5a'),
    }

    def show_action(self, obj):
        bg, fg = self.ACTION_COLORS.get(obj.action, ('#f1efe8', '#5f5e5a'))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;border-radius:5px;font-size:11px;font-weight:500;">{}</span>',
            bg, fg, obj.get_action_display()
        )
    show_action.short_description = 'Action'
    show_action.admin_order_field = 'action'

    def show_user(self, obj):
        if obj.user:
            return format_html('<span style="font-size:12px;">{}</span>', obj.user.email)
        return mark_safe('<span style="color:#9ca3af;font-size:12px;">System</span>')
    show_user.short_description = 'User'

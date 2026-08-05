from django.contrib import admin

# Register your models here.
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline, format_html, mark_safe
from .models import ActivityLog, Category, Product, Variant, Rating, Order, OrderItem, CartItem, LoyaltyPoint, Notification, TownZone
from unfold.decorators import action


# ─── Helpers ──────────────────────────────────────────────────────────────────
# Badge colors reuse Unfold's own label palette (bg-x-100/text-x-700 in light,
# dark:bg-x-500/20/dark:text-x-400 in dark) so they stay correct in both themes.
BADGE_VARIANTS = {
    'info':    'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',
    'danger':  'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400',
    'warning': 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400',
    'success': 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400',
    'primary': 'bg-primary-100 text-primary-700 dark:bg-primary-500/20 dark:text-primary-400',
    'base':    'bg-base-500/8 text-base-700 dark:bg-base-500/20 dark:text-base-200',
}


def _badge(label, variant='base'):
    return format_html(
        '<span class="inline-block font-semibold rounded-default text-[11px] px-2 py-1 whitespace-nowrap {}">{}</span>',
        BADGE_VARIANTS.get(variant, BADGE_VARIANTS['base']), label,
    )


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
        'new_order':    ('🛒', 'success'),
        'bulk_order':   ('🍽️', 'warning'),
        'low_stock':    ('⚠️', 'danger'),
        'payment_paid': ('✅', 'info'),
    }

    def show_type(self, obj):
        icon, variant = self.TYPE_ICONS.get(obj.type, ('📢', 'base'))
        return _badge(f'{icon} {obj.get_type_display()}', variant)
    show_type.short_description = 'Type'

    def mark_read_link(self, obj):
        if obj.is_read:
            return mark_safe('<span class="text-base-400 dark:text-base-500 text-xs">✓ Read</span>')
        return format_html(
            '<a href="/admin/mark-notification-read/{}/" class="text-primary-600 dark:text-primary-500 hover:text-primary-700 dark:hover:text-primary-400 text-xs font-semibold">Mark as Read</a>',
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
    list_filter = ['category', 'is_available', 'is_featured', 'is_seasonal']
    search_fields = ['name', 'sku']
    inlines = [VariantInline]


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_before_template = 'admin/order_change_list.html'
    list_display    = ['id', 'email', 'phone', 'order_type', 'show_status', 'payment_method', 'show_payment_status', 'total_price', 'created_at', 'print_receipt_link']
    list_filter     = ['status', 'payment_method', 'payment_status', 'order_type']
    search_fields   = ['email', 'phone', 'id']
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
        'pending':    'warning',
        'confirmed':  'info',
        'processing': 'primary',
        'delivered':  'success',
        'cancelled':  'danger',
    }

    PAYMENT_COLORS = {
        'unpaid':      'danger',
        'downpayment': 'warning',
        'paid':        'success',
        'failed':      'danger',
        'refunded':    'base',
    }

    def show_status(self, obj):
        return _badge(obj.get_status_display(), self.STATUS_COLORS.get(obj.status, 'base'))
    show_status.short_description = 'Status'
    show_status.admin_order_field = 'status'

    def show_payment_status(self, obj):
        return _badge(obj.get_payment_status_display(), self.PAYMENT_COLORS.get(obj.payment_status, 'base'))
    show_payment_status.short_description = 'Payment Status'
    show_payment_status.admin_order_field = 'payment_status'

    def print_receipt_link(self, obj):
        return format_html(
            '<a href="/admin/orders/{}/receipt/" target="_blank" '
            'class="font-medium inline-flex items-center gap-1 rounded-default whitespace-nowrap '
            'px-2.5 py-1 text-[11px] border border-base-200 bg-primary-600 border-transparent '
            'text-white hover:bg-primary-600/80">🖨️ Print</a>',
            obj.id
        )
    print_receipt_link.short_description = 'Receipt'



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
        'order_created':   'success',
        'order_updated':   'info',
        'order_cancelled': 'danger',
        'payment_paid':    'success',
        'product_created': 'primary',
        'product_updated': 'info',
        'user_login':      'warning',
        'stock_movement':  'base',
    }

    def show_action(self, obj):
        return _badge(obj.get_action_display(), self.ACTION_COLORS.get(obj.action, 'base'))
    show_action.short_description = 'Action'
    show_action.admin_order_field = 'action'

    def show_user(self, obj):
        if obj.user:
            return format_html('<span class="text-xs">{}</span>', obj.user.email)
        return mark_safe('<span class="text-base-400 dark:text-base-500 text-xs">System</span>')
    show_user.short_description = 'User'

@admin.register(TownZone)
class TownZoneAdmin(ModelAdmin):
    list_display = ['name', 'delivery_fee', 'min_order_amount', 'estimated_time', 'is_active']
    list_editable = ['delivery_fee', 'min_order_amount', 'estimated_time', 'is_active']
    search_fields = ['name']

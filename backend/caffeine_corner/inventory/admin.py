from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from .models import (
    InventoryCategory, Supplier, Inventory,
    StockMovement, PurchaseOrder, PurchaseOrderItem, Ingredient
)


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

BAR_VARIANTS = {
    'danger':  'bg-red-500',
    'warning': 'bg-orange-500',
    'success': 'bg-green-500',
}


def _badge(label, variant='base'):
    return format_html(
        '<span class="inline-block font-semibold rounded-default text-[11px] px-2 py-1 whitespace-nowrap {}">{}</span>',
        BADGE_VARIANTS.get(variant, BADGE_VARIANTS['base']), label,
    )


def _stock_bar(qty_on_hand, reorder_points):
    from decimal import Decimal
    if reorder_points == 0:
        pct = 100
    else:
        # I-convert sa float explicitly
        pct = min(int((float(qty_on_hand) / float(reorder_points)) * 50), 100)

    if qty_on_hand <= reorder_points:
        variant = 'danger'
    elif qty_on_hand <= reorder_points * Decimal('2'):
        variant = 'warning'
    else:
        variant = 'success'

    text_class = {'danger': 'text-red-700 dark:text-red-400',
                  'warning': 'text-orange-700 dark:text-orange-400',
                  'success': 'text-green-700 dark:text-green-400'}[variant]

    return format_html(
        '<div class="flex items-center gap-2">'
        '<div class="w-24 h-1.5 bg-base-100 dark:bg-base-800 rounded-full overflow-hidden">'
        '<div class="h-full rounded-full {}" style="width:{}%"></div>'
        '</div>'
        '<span class="text-xs font-medium {}">{}</span>'
        '</div>',
        BAR_VARIANTS[variant], pct, text_class, qty_on_hand,
    )


# ─── InventoryCategory ────────────────────────────────────────────────────────

@admin.register(InventoryCategory)
class InventoryCategoryAdmin(ModelAdmin):
    list_display  = ['name', 'description']
    search_fields = ['name']


# ─── Supplier ─────────────────────────────────────────────────────────────────

@admin.register(Supplier)
class SupplierAdmin(ModelAdmin):
    list_display  = ['name', 'contact_name', 'email', 'phone', 'is_active']
    list_editable = ['is_active']
    search_fields = ['name', 'email']
    list_filter   = ['is_active']


# ─── StockMovement Inline ─────────────────────────────────────────────────────

class StockMovementInline(TabularInline):
    model           = StockMovement
    extra           = 0
    fields          = ['movement_type', 'quantity', 'unit_cost', 'reference', 'notes', 'performed_by', 'created_at']
    readonly_fields = ['created_at', 'quantity_change']
    ordering        = ['-created_at']
    max_num         = 10


# ─── Inventory ────────────────────────────────────────────────────────────────

@admin.register(Inventory)
class InventoryAdmin(ModelAdmin):
    compressed_fields = True
    list_display = [
        'name', 'category', 'supplier',
        'show_stock_bar', 'show_reserved',
        'show_stock_status', 'show_expiry_status',
        'show_stock_value',
        'last_updated',
    ]
    list_filter     = ['category', 'supplier']
    search_fields   = ['name', 'sku']
    readonly_fields = ['quantity_available', 'stock_value', 'is_low_stock', 'is_expired', 'last_updated']
    inlines         = [StockMovementInline]

    def show_stock_bar(self, obj):
        return _stock_bar(obj.quantity_on_hand, obj.reorder_points)
    show_stock_bar.short_description = _('Stock Level')

    def show_reserved(self, obj):
        if obj.quantity_reserved == 0:
            return mark_safe('<span class="text-base-400 dark:text-base-500">—</span>')
        return format_html(
            '<span class="text-orange-700 dark:text-orange-400 font-medium">{} {}</span>',
            obj.quantity_reserved, obj.unit,
        )
    show_reserved.short_description = _('Reserved')

    def show_stock_status(self, obj):
        if obj.quantity_on_hand == 0:
            return _badge('Out of Stock', 'danger')
        if obj.is_low_stock:
            return _badge('Low Stock', 'warning')
        return _badge('OK', 'success')
    show_stock_status.short_description = _('Status')

    def show_stock_value(self, obj):
        value = float(obj.stock_value)  # ← i-convert sa float
        if value == 0:
            return mark_safe('<span class="text-base-400 dark:text-base-500">₱0.00</span>')
        return format_html(
            '<span class="font-semibold">₱{}</span>',
            f"{value:,.2f}",
        )
    show_stock_value.short_description = _('Stock Value')

    def show_expiry_status(self, obj):
        if not obj.expiry_date:
            return mark_safe('<span class="text-base-400 dark:text-base-500">—</span>')
        from django.utils import timezone
        days_left = (obj.expiry_date - timezone.now().date()).days
        if days_left < 0:
            return _badge('Expired', 'danger')
        elif days_left <= 7:
            return _badge(f'{days_left}d left', 'warning')
        elif days_left <= 30:
            return _badge(f'{days_left}d left', 'info')
        return _badge(f'{days_left}d', 'success')
    show_expiry_status.short_description = _('Expiry')


# ─── StockMovement ────────────────────────────────────────────────────────────

@admin.register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display    = ['inventory', 'movement_type', 'quantity', 'quantity_change', 'performed_by', 'created_at']
    list_filter     = ['movement_type']
    search_fields   = ['inventory__name', 'reference']
    readonly_fields = ['quantity_change', 'created_at']


# ─── PurchaseOrder ────────────────────────────────────────────────────────────

class PurchaseOrderItemInline(TabularInline):
    model = PurchaseOrderItem
    extra = 1


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ModelAdmin):
    list_display    = ['reference', 'supplier', 'show_status', 'ordered_at', 'expected_at', 'show_total_cost', 'show_item_count']
    list_editable   = ['status'] if False else []  # handled by show_status
    list_filter     = ['status', 'supplier', 'ordered_at']
    search_fields   = ['reference', 'supplier__name']
    inlines         = [PurchaseOrderItemInline]

    STATUS_COLORS = {
        'draft':     'base',
        'sent':      'info',
        'partial':   'warning',
        'received':  'success',
        'cancelled': 'danger',
    }

    def show_status(self, obj):
        return _badge(obj.get_status_display(), self.STATUS_COLORS.get(obj.status, 'base'))
    show_status.short_description = 'Status'

    def show_total_cost(self, obj):
        total = obj.total_cost
        if total == 0:
            return mark_safe('<span class="text-base-400 dark:text-base-500">₱0.00</span>')
        return format_html('<span class="font-semibold">₱{}</span>', f"{total:,.2f}")
    show_total_cost.short_description = 'Total Cost'

    def show_item_count(self, obj):
        count = obj.items.count()
        return format_html('<span class="font-medium">{} item{}</span>', count, 's' if count != 1 else '')
    show_item_count.short_description = 'Items'

    def changelist_view(self, request, extra_context=None):
        from inventory.models import Inventory
        from django.db.models import F

        low_stock_count = Inventory.objects.filter(
            quantity_on_hand__lte=F('reorder_points'),
            supplier__isnull=False,
        ).count()

        extra_context = extra_context or {}
        extra_context['low_stock_count'] = low_stock_count
        extra_context['auto_generate_url'] = '/admin/auto-generate-po/'
        return super().changelist_view(request, extra_context=extra_context)


# ─── Ingredient ───────────────────────────────────────────────────────────────

@admin.register(Ingredient)
class IngredientAdmin(ModelAdmin):
    list_display  = ['product', 'inventory', 'quantity', 'unit']
    search_fields = ['product__name', 'inventory__name']



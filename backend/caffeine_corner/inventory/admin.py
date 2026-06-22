from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from .models import (
    InventoryCategory, Supplier, Inventory,
    StockMovement, PurchaseOrder, PurchaseOrderItem, Ingredient
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _badge(label, bg, fg):
    return format_html(
        '<span style="background:{};color:{};padding:3px 10px;border-radius:5px;'
        'font-size:11px;font-weight:500;white-space:nowrap;">{}</span>',
        bg, fg, label,
    )


def _stock_bar(qty_on_hand, reorder_points):
    from decimal import Decimal
    if reorder_points == 0:
        pct = 100
    else:
        # I-convert sa float explicitly
        pct = min(int((float(qty_on_hand) / float(reorder_points)) * 50), 100)

    if qty_on_hand <= reorder_points:
        color = "#c04a3a"
    elif qty_on_hand <= reorder_points * Decimal('2'):
        color = "#a06010"
    else:
        color = "#2e7d4a"

    return format_html(
        '<div style="display:flex;align-items:center;gap:8px;min-width:120px;">'
        '  <div style="flex:1;height:6px;background:#e8ddd0;border-radius:3px;overflow:hidden;">'
        '    <div style="width:{}%;height:100%;background:{};border-radius:3px;"></div>'
        '  </div>'
        '  <span style="font-size:12px;font-weight:500;color:{};">{}</span>'
        '</div>',
        pct, color, color, qty_on_hand,
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
            return mark_safe('<span style="color:#b4b2a9;">—</span>')
        return format_html(
            '<span style="color:#a06010;font-weight:500;">{} {}</span>',
            obj.quantity_reserved, obj.unit,
        )
    show_reserved.short_description = _('Reserved')

    def show_stock_status(self, obj):
        if obj.quantity_on_hand == 0:
            return _badge('Out of Stock', '#fef0ee', '#c04a3a')
        if obj.is_low_stock:
            return _badge('Low Stock', '#fff6e0', '#a06010')
        return _badge('OK', '#eaf5ed', '#2e7d4a')
    show_stock_status.short_description = _('Status')

    def show_stock_value(self, obj):
        value = float(obj.stock_value)  # ← i-convert sa float
        if value == 0:
            return mark_safe('<span style="color:#b4b2a9;">₱0.00</span>')
        return format_html(
            '<span style="font-weight:600;">₱{}</span>',
            f"{value:,.2f}",
        )
    show_stock_value.short_description = _('Stock Value')

    def show_expiry_status(self, obj):
        if not obj.expiry_date:
            return mark_safe('<span style="color:#b4b2a9;">—</span>')
        from django.utils import timezone
        days_left = (obj.expiry_date - timezone.now().date()).days
        if days_left < 0:
            return _badge('Expired', '#fef0ee', '#c04a3a')
        elif days_left <= 7:
            return _badge(f'{days_left}d left', '#fff6e0', '#a06010')
        elif days_left <= 30:
            return _badge(f'{days_left}d left', '#e6f0fa', '#1a5494')
        return _badge(f'{days_left}d', '#eaf5ed', '#2e7d4a')
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
        'draft':     ('#f1efe8', '#5f5e5a'),
        'sent':      ('#e6f0fa', '#1a5494'),
        'partial':   ('#fff6e0', '#a06010'),
        'received':  ('#eaf5ed', '#2e7d4a'),
        'cancelled': ('#fef0ee', '#c04a3a'),
    }

    def show_status(self, obj):
        bg, fg = self.STATUS_COLORS.get(obj.status, ('#f1efe8', '#5f5e5a'))
        return _badge(obj.get_status_display(), bg, fg)
    show_status.short_description = 'Status'

    def show_total_cost(self, obj):
        total = obj.total_cost
        if total == 0:
            return mark_safe('<span style="color:#b4b2a9;">₱0.00</span>')
        return format_html('<span style="font-weight:600;">₱{}</span>', f"{total:,.2f}")
    show_total_cost.short_description = 'Total Cost'

    def show_item_count(self, obj):
        count = obj.items.count()
        return format_html('<span style="font-weight:500;">{} item{}</span>', count, 's' if count != 1 else '')
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



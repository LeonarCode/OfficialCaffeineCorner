from django.contrib import admin
from django import forms
from django.db.models import F
from django.urls import reverse
from django.utils.html import format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from .models import (
    InventoryCategory, Supplier, Inventory,
    StockMovement, PurchaseOrder, PurchaseOrderItem
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

class StockMovementInlineForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Past movements are an audit trail, not editable records — its
        # save() re-applies quantity_change to quantity_on_hand on *every*
        # save, not just creation, so editing an existing row's quantity
        # here would silently push stock by that new amount on top of
        # what's already there instead of correcting it. New (blank) rows
        # are unaffected — that's the only way movements should be entered.
        if self.instance.pk:
            for field in self.fields.values():
                field.disabled = True


class StockMovementInline(TabularInline):
    model           = StockMovement
    form            = StockMovementInlineForm
    extra           = 0
    fields          = ['movement_type', 'quantity', 'unit_cost', 'reference', 'notes', 'performed_by', 'created_at']
    readonly_fields = ['created_at', 'quantity_change']
    ordering        = ['-created_at']
    max_num         = 10

    # Same reasoning as the disabled fields above — deleting a past
    # movement here wouldn't undo its effect on quantity_on_hand, it would
    # just erase the record of why the stock is what it is. Superusers only,
    # same convention as ActivityLog (see online_shop/admin.py).
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ─── Inventory ────────────────────────────────────────────────────────────────

# Module-level (not InventoryAdmin methods) so htmx_adjust_stock (views.py)
# can re-render the exact same markup for its OOB swaps after a quick
# adjustment — see render_quick_adjust below for the other half.
def render_stock_bar(obj):
    return _stock_bar(obj.quantity_on_hand, obj.reorder_points)


def render_stock_status(obj):
    if obj.quantity_on_hand == 0:
        return _badge('Out of Stock', 'danger')
    if obj.is_low_stock:
        return _badge('Low Stock', 'warning')
    return _badge('OK', 'success')


# A tiny +/- form living right in the changelist row — no more opening the
# item just to log a delivery or a spoilage write-off. "+" logs a Purchase
# (stock in), "-" a manual Adjustment (stock out); anything needing a PO
# reference, a different movement type, or a look at past movements still
# goes through the full item page (see StockMovementInline below). Posts to
# htmx_adjust_stock (views.py), which re-renders this widget plus the Stock
# Level / Status cells (out-of-band, matched by the ids below) so all three
# stay in sync from one click, no page reload.
def render_quick_adjust(obj):
    # No `name` on the quantity input — deliberate, not an oversight. Every
    # row on this changelist has one, all sitting inside Django's one big
    # #changelist-form (it wraps the whole results table, for bulk
    # actions), and htmx always merges in every *named* field of a
    # triggering element's closest enclosing form for a POST — same as a
    # native form submit would. hx-include only adds more sources on top of
    # that, it can't turn it off, and hx-params can't selectively drop just
    # the duplicates either (it's a same-or-nothing filter over the
    # already-merged result, applied *after* hx-vals merges in too — tried
    # hx-params="none" first, thinking it'd suppress only the form; it
    # wiped the hx-vals value along with it). See the long comment on
    # _htmx_select in online_shop/admin.py for how this exact failure mode
    # actually corrupted a different order's status in testing — same bug,
    # confirmed here too before this fix (every row's quantity ended up in
    # one request). A field with no `name` isn't a "successful" form
    # control at all, so it's invisible to that automatic collection —
    # hx-vals below, reading this one input's value directly at request
    # time, is then the *only* source for it, no collision possible.
    dom_id = f'qa-{obj.pk}'
    base_url = reverse('htmx-adjust-stock', args=[obj.pk])
    # Double quotes inside, since the hx-vals HTML attribute itself is
    # wrapped in single quotes below — a single quote in here would close
    # that attribute early and truncate the rest of the expression (caught
    # this via an actual browser console: htmx choked on the cut-off JS
    # with "Unexpected end of input").
    qty_selector = f'document.getElementById("{dom_id}").querySelector("input").value'
    vals = mark_safe('js:{"quantity": ' + qty_selector + '}')
    return format_html(
        '<div id="{}" class="flex items-center gap-1">'
        '<input type="number" step="0.01" min="0.01" placeholder="{}" '
        'class="w-16 rounded-default border border-base-200 bg-white text-sm px-2 py-1 '
        'dark:bg-base-900 dark:border-base-700 dark:text-font-default-dark" />'
        '<button type="button" hx-post="{}" hx-vals=\'{}\' hx-target="closest td" hx-swap="innerHTML" '
        'class="w-6 h-6 flex items-center justify-center rounded-default font-bold leading-none '
        'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-500/20 dark:text-green-400 dark:hover:bg-green-500/30" '
        'title="Stock in (Purchase)">+</button>'
        '<button type="button" hx-post="{}" hx-vals=\'{}\' hx-target="closest td" hx-swap="innerHTML" '
        'class="w-6 h-6 flex items-center justify-center rounded-default font-bold leading-none '
        'bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-500/20 dark:text-red-400 dark:hover:bg-red-500/30" '
        'title="Stock out (Adjustment)">−</button>'
        '</div>',
        dom_id, obj.unit,
        base_url + '?type=purchase', vals,
        base_url + '?type=adjustment', vals,
    )


class StockStatusFilter(admin.SimpleListFilter):
    title = _('stock status')
    parameter_name = 'stock_status'

    def lookups(self, request, model_admin):
        return [
            ('out', _('Out of Stock')),
            ('low', _('Low Stock')),
            ('ok',  _('OK')),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'out':
            return queryset.filter(quantity_on_hand=0)
        if self.value() == 'low':
            return queryset.filter(quantity_on_hand__gt=0, quantity_on_hand__lte=F('reorder_points'))
        if self.value() == 'ok':
            return queryset.filter(quantity_on_hand__gt=F('reorder_points'))
        return queryset


@admin.register(Inventory)
class InventoryAdmin(ModelAdmin):
    compressed_fields = True
    list_display = [
        'name', 'category', 'supplier',
        'show_stock_bar', 'show_reserved',
        'show_stock_status', 'show_expiry_status',
        'show_stock_value', 'show_quick_adjust',
        'last_updated',
    ]
    list_filter     = [StockStatusFilter, 'category', 'supplier']
    search_fields   = ['name', 'sku']
    readonly_fields = ['quantity_available', 'stock_value', 'is_low_stock', 'is_expired', 'last_updated']
    inlines         = [StockMovementInline]

    def show_stock_bar(self, obj):
        return format_html('<span id="stock-bar-{}">{}</span>', obj.pk, render_stock_bar(obj))
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
        return format_html('<span id="stock-status-{}">{}</span>', obj.pk, render_stock_status(obj))
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

    def show_quick_adjust(self, obj):
        return render_quick_adjust(obj)
    show_quick_adjust.short_description = _('Quick Adjust')

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


# ─── StockMovement (standalone) ────────────────────────────────────────────────
# A browsable audit log across *all* items — the inline above only shows one
# item's history at a time. Read-only for the same reason as the inline: past
# movements shouldn't be editable or deletable after the fact (see
# StockMovementInlineForm / StockMovementInline.has_delete_permission).

@admin.register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display    = ['created_at', 'inventory', 'show_movement_type', 'show_quantity_change', 'reference', 'performed_by']
    list_filter     = ['movement_type', 'created_at']
    search_fields   = ['inventory__name', 'inventory__sku', 'reference', 'notes']
    date_hierarchy  = 'created_at'
    autocomplete_fields = ['inventory']

    MOVEMENT_COLORS = {
        'purchase':   'success',
        'usage':      'info',
        'adjustment': 'warning',
        'spoilage':   'danger',
        'return':     'warning',
        'transfer':   'base',
        'reversal':   'base',
    }

    def show_movement_type(self, obj):
        return _badge(obj.get_movement_type_display(), self.MOVEMENT_COLORS.get(obj.movement_type, 'base'))
    show_movement_type.short_description = _('Type')

    def show_quantity_change(self, obj):
        sign = '+' if obj.quantity_change >= 0 else ''
        color = 'text-green-700 dark:text-green-400' if obj.quantity_change >= 0 else 'text-red-700 dark:text-red-400'
        return format_html(
            '<span class="font-semibold {}">{}{} {}</span>',
            color, sign, obj.quantity_change, obj.inventory.unit,
        )
    show_quantity_change.short_description = _('Change')

    def has_add_permission(self, request):
        # Movements are created from the Inventory item page (either the
        # inline, or the Quick Adjust widget on the changelist) — both
        # already run through StockMovement.save()'s quantity_on_hand
        # logic. A bare add form here would too, but with none of the
        # context (which item, current cost) that makes that safe to do
        # quickly, so it's intentionally not exposed as a separate entry
        # point.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


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




from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.db.models import F, Q, Sum
from django.forms.models import BaseInlineFormSet
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action
from unfold.enums import ActionVariant
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget, UnfoldAdminTextInputWidget

from . import purchasing
from .models import (
    InventoryCategory, Supplier, Inventory,
    StockMovement, PurchaseOrder, PurchaseOrderItem
)
from .stock import check_movement, show as show_qty


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

MUTED = mark_safe('<span class="text-base-400 dark:text-base-500">—</span>')


def _badge(label, variant='base'):
    return format_html(
        '<span class="inline-block font-semibold rounded-default text-[11px] px-2 py-1 whitespace-nowrap {}">{}</span>',
        BADGE_VARIANTS.get(variant, BADGE_VARIANTS['base']), label,
    )


def _peso(value):
    return f"₱{float(value):,.2f}"


def _stock_bar(qty_on_hand, reorder_points, unit=''):
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

    # The unit sits right next to the number: "28.18" and "9400.00" side by
    # side meant nothing until you noticed one was kg and the other grams.
    return format_html(
        '<div class="flex items-center gap-2">'
        '<div class="w-20 h-1.5 bg-base-100 dark:bg-base-800 rounded-full overflow-hidden shrink-0">'
        '<div class="h-full rounded-full {}" style="width:{}%"></div>'
        '</div>'
        '<span class="text-xs font-medium whitespace-nowrap {}">{} {}</span>'
        '</div>',
        BAR_VARIANTS[variant], pct, text_class, qty_on_hand, unit,
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


# ─── Stock movements: how staff record stock in / out ─────────────────────────
# One form, used in two places — the item page ("Record stock in / stock out")
# and the Stock Movements page ("Add") — so the rules and wording match.

MANUAL_TYPE_CHOICES = [
    (value, label) for value, label in StockMovement.MOVEMENT_TYPES if value in StockMovement.MANUAL_TYPES
]

MOVEMENT_COLORS = {
    'purchase':   'success',
    'usage':      'info',
    'adjustment': 'warning',
    'spoilage':   'danger',
    'return':     'warning',
    'transfer':   'base',
    'reversal':   'base',
}


def render_movement_change(movement, unit):
    positive = movement.quantity_change >= 0
    return format_html(
        '<span class="font-semibold whitespace-nowrap {}">{}{} {}</span>',
        'text-green-700 dark:text-green-400' if positive else 'text-red-700 dark:text-red-400',
        '+' if positive else '', movement.quantity_change, unit,
    )


class StockMovementEntryForm(forms.ModelForm):
    """The fields staff fill in to record stock coming in or going out."""

    movement_type = forms.ChoiceField(
        label=_('Type'), choices=MANUAL_TYPE_CHOICES, initial='purchase', widget=UnfoldAdminSelectWidget,
        help_text=_('“Stock In” adds to what you have; “Stock Out” takes away.'),
    )

    class Meta:
        model = StockMovement
        fields = ['movement_type', 'quantity', 'unit_cost', 'reference', 'notes']
        labels = {
            'quantity': _('Quantity'),
            'unit_cost': _('Cost per unit (₱)'),
            'reference': _('Reference'),
            'notes': _('Note'),
        }
        help_texts = {
            'quantity': _('How much came in or went out, in the item’s unit.'),
            'unit_cost': _('Leave blank to use the item’s current cost.'),
            'reference': _('Optional — an invoice or receipt number, e.g. INV-1042.'),
            'notes': _('Optional — e.g. “dropped and spilled”.'),
        }
        widgets = {'notes': UnfoldAdminTextInputWidget()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit_cost'].required = False
        # The model's default is 0.00, which is what a new row would show — so
        # "leave blank to use the item's cost" could never be true, and a cost of
        # 0.0 was quietly saved. Start it blank; clean() fills in the item's cost.
        self.initial.pop('unit_cost', None)
        self.fields['unit_cost'].initial = None            # (the field carries the model's 0.00 default too)

    def clean_quantity(self):
        quantity = self.cleaned_data['quantity']
        if quantity <= 0:
            raise forms.ValidationError(_('Enter a quantity greater than 0.'))
        return quantity

    def _inventory(self):
        if self.cleaned_data.get('inventory'):                       # the Stock Movements page picks it
            return self.cleaned_data['inventory']
        if self.instance.inventory_id:                               # the item page already knows it
            return Inventory.objects.filter(pk=self.instance.inventory_id).first()
        return None

    def clean(self):
        cleaned = super().clean()
        inventory, kind, quantity = self._inventory(), cleaned.get('movement_type'), cleaned.get('quantity')
        if inventory and kind and quantity:
            problem = check_movement(inventory, kind, quantity)
            if problem:
                self.add_error('quantity', problem)
        # Decided here, not when saving: a blank number field is left at the
        # model's default (0.00) rather than None, so a "blank means the item's
        # cost" fallback at save time never saw it.
        if cleaned.get('unit_cost') is None and inventory:
            cleaned['unit_cost'] = inventory.cost_per_unit
        return cleaned


class StockMovementAddForm(StockMovementEntryForm):
    """Same, plus which item — for the Stock Movements page."""

    class Meta(StockMovementEntryForm.Meta):
        fields = ['inventory'] + StockMovementEntryForm.Meta.fields
        labels = {**StockMovementEntryForm.Meta.labels, 'inventory': _('Item')}
        help_texts = {**StockMovementEntryForm.Meta.help_texts, 'inventory': _('Start typing a name or code.')}


class StockMovementEntryInline(TabularInline):
    """
    The item page's way to record stock in / out. Add-only on purpose: it lists
    no past movements (an item can have hundreds, and showing them all as
    editable-looking rows made the page 18,000 px tall and — because of
    max_num — hid the "add another" link once an item reached 10). Recent
    movements are summarised above it, with a link to the full history.
    """
    model = StockMovement
    form = StockMovementEntryForm
    extra = 1
    can_delete = False
    verbose_name = _('stock movement')
    verbose_name_plural = _('Record stock in / stock out')

    def get_queryset(self, request):
        return super().get_queryset(request).none()


# ─── Inventory ────────────────────────────────────────────────────────────────

# Module-level (not InventoryAdmin methods) so htmx_adjust_stock (views.py)
# can re-render the exact same markup for its OOB swaps after a quick
# adjustment — see render_quick_adjust below for the other half.
def render_stock_bar(obj):
    return _stock_bar(obj.quantity_on_hand, obj.reorder_points, obj.unit)


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
    # A rejected request (say "+" pressed with the box empty) is explained by a
    # toast — see static/js/htmx-feedback.js — and hx-on below puts the cursor
    # back in the quantity box so the fix is one keystroke away. The two
    # buttons share hx-on, so it's spelled once and passed in.
    refocus = mark_safe('this.parentNode.querySelector(\'input\').focus()')
    return format_html(
        '<div id="{0}" class="flex items-center gap-1">'
        '<input type="number" step="0.01" min="0.01" placeholder="Qty" title="Quantity in {1}" '
        'class="w-16 rounded-default border border-base-200 bg-white text-sm px-2 py-1 '
        'dark:bg-base-900 dark:border-base-700 dark:text-font-default-dark" />'
        '<span class="text-xs text-font-subtle-light dark:text-font-subtle-dark">{1}</span>'
        '<button type="button" hx-post="{2}" hx-vals=\'{3}\' hx-target="closest td" hx-swap="innerHTML" '
        'hx-on::response-error="{6}" '
        'class="w-6 h-6 flex items-center justify-center rounded-default font-bold leading-none '
        'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-500/20 dark:text-green-400 dark:hover:bg-green-500/30" '
        'title="Stock in (Purchase)" aria-label="Stock in">+</button>'
        '<button type="button" hx-post="{4}" hx-vals=\'{5}\' hx-target="closest td" hx-swap="innerHTML" '
        'hx-on::response-error="{6}" '
        'class="w-6 h-6 flex items-center justify-center rounded-default font-bold leading-none '
        'bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-500/20 dark:text-red-400 dark:hover:bg-red-500/30" '
        'title="Stock out (Adjustment)" aria-label="Stock out">−</button>'
        '</div>',
        dom_id, obj.unit,
        base_url + '?type=purchase', vals,
        base_url + '?type=adjustment', vals,
        refocus,
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


class InventoryAdminForm(forms.ModelForm):
    class Meta:
        model = Inventory
        fields = '__all__'
        labels = {
            'sku': _('Item code (SKU)'),
            'quantity_on_hand': _('Opening stock'),
            'reorder_points': _('Reorder level'),
            'reorder_quantity': _('Reorder quantity'),
            'cost_per_unit': _('Cost per unit (₱)'),
        }
        help_texts = {
            'sku': _('Your own short code for this item, e.g. BEAN-ESP-001. Must be unique.'),
            'unit': _('What it is counted in — kg, g, ml, L, pcs…'),
            'quantity_on_hand': _(
                'How much you have right now. Once the item is saved, change stock with the + / − buttons '
                'or “Record stock in / stock out” so every change is on record.'
            ),
            'reorder_points': _('You get a low-stock warning — and it joins Auto-Generate Purchase Orders — when stock falls to this amount or below.'),
            'reorder_quantity': _('How much to order each time it runs low.'),
            'cost_per_unit': _('What one unit costs you. Used for stock value and as the default cost on purchase orders.'),
            'expiry_date': _('Leave blank if it does not expire.'),
        }


@admin.register(Inventory)
class InventoryAdmin(ModelAdmin):
    form = InventoryAdminForm
    compressed_fields = True
    list_display = [
        'name', 'category', 'supplier',
        'show_stock_bar', 'show_stock_status', 'show_on_order',
        'show_expiry_status', 'show_stock_value', 'show_quick_adjust',
    ]
    list_filter         = [StockStatusFilter, 'category', 'supplier']
    search_fields       = ['name', 'sku']
    list_select_related = ['category', 'supplier']
    inlines             = [StockMovementEntryInline]

    def get_queryset(self, request):
        # "On order" per item, in one query: what open purchase orders still owe.
        open_po = Q(po_items__purchase_order__status__in=purchasing.OPEN_STATUSES)
        return super().get_queryset(request).annotate(
            on_order=Sum(F('po_items__quantity_ordered') - F('po_items__quantity_received'), filter=open_po),
        )

    # ── the form ──
    # (Reserved isn't offered: nothing in the system ever sets or reads it, so
    # it was just a box that suggested a feature that doesn't exist.)
    def get_fieldsets(self, request, obj=None):
        item = (_('Item'), {'fields': ['category', 'supplier', 'name', 'sku', 'unit']})
        if obj is None:
            return [
                item,
                (_('Stock'), {'fields': ['quantity_on_hand', 'reorder_points', 'reorder_quantity', 'cost_per_unit', 'expiry_date']}),
            ]
        return [
            item,
            (_('Stock right now'), {'fields': ['current_stock', 'stock_state', 'stock_value_display']}),
            (_('Reordering & cost'), {'fields': ['reorder_points', 'reorder_quantity', 'cost_per_unit', 'expiry_date']}),
            (_('Recent movements'), {'fields': ['recent_movements']}),
        ]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        return ['current_stock', 'stock_state', 'stock_value_display', 'recent_movements']

    def get_inline_instances(self, request, obj=None):
        # A brand-new item has no movements to add to; its starting quantity is
        # the "Opening stock" field (recorded as a movement on save).
        return super().get_inline_instances(request, obj) if obj else []

    @admin.display(description=_('Stock now'))
    def current_stock(self, obj):
        return format_html('<span class="text-lg font-semibold">{} {}</span>', obj.quantity_on_hand, obj.unit)

    @admin.display(description=_('Status'))
    def stock_state(self, obj):
        return format_html('{} {}', render_stock_status(obj), self.show_expiry_status(obj))

    @admin.display(description=_('Stock value'))
    def stock_value_display(self, obj):
        return _peso(obj.stock_value)

    @admin.display(description=_('Recent movements'))
    def recent_movements(self, obj):
        if not obj or not obj.pk:
            return MUTED
        moves = list(obj.movements.select_related('performed_by')[:8])
        if not moves:
            return mark_safe('<span class="text-base-500">No stock movements yet.</span>')
        rows = format_html_join('', (
            '<tr class="border-b border-base-200 dark:border-base-800">'
            '<td class="py-1.5 pr-4 whitespace-nowrap">{}</td><td class="py-1.5 pr-4 whitespace-nowrap">{}</td>'
            '<td class="py-1.5 pr-4 whitespace-nowrap">{}</td><td class="py-1.5 pr-4 whitespace-nowrap">{}</td>'
            '<td class="py-1.5 text-base-500 whitespace-nowrap">{}</td></tr>'
        ), (
            (
                date_format(timezone.localtime(m.created_at), 'M j, g:i A'),
                _badge(m.get_movement_type_display(), MOVEMENT_COLORS.get(m.movement_type, 'base')),
                render_movement_change(m, obj.unit),
                m.reference or '—',
                m.performed_by or 'System',
            ) for m in moves
        ))
        history = reverse('admin:inventory_stockmovement_changelist') + f'?inventory__id__exact={obj.pk}'
        return format_html(
            '<div class="overflow-x-auto"><table class="w-full text-sm">{}</table></div>'
            '<p class="mt-3 text-sm"><a class="font-medium text-primary-600 dark:text-primary-500" href="{}">'
            'View all {} movements →</a></p>',
            rows, history, obj.movements.count(),
        )

    # ── saving ──
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            obj._opening_stock = obj.quantity_on_hand      # already on the item; documented in save_related

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        item, opening = form.instance, getattr(form.instance, '_opening_stock', 0)
        if not change and opening:
            # The item was created holding `opening`. Record where it came from,
            # without applying it a second time (that would double it).
            StockMovement(
                inventory=item, movement_type='purchase', quantity=opening, unit_cost=item.cost_per_unit,
                reference='Opening stock', notes='Stock on hand when the item was added.',
                performed_by=request.user,
            ).save(apply_to_stock=False)

    def save_formset(self, request, form, formset, change):
        if formset.model is not StockMovement:
            return super().save_formset(request, form, formset, change)
        item = form.instance
        for movement in formset.save(commit=False):
            movement.performed_by = request.user
            if movement.unit_cost is None:
                movement.unit_cost = item.cost_per_unit
            movement.save()
            item.refresh_from_db()
            self.message_user(
                request,
                f"{movement.get_movement_type_display()}: {'+' if movement.quantity_change >= 0 else '−'}"
                f'{show_qty(abs(movement.quantity_change))} {item.unit} '
                f'— {item.name} now has {show_qty(item.quantity_on_hand)} {item.unit}.',
                messages.SUCCESS,
            )
        formset.save_m2m()

    # ── list columns ──
    def show_stock_bar(self, obj):
        return format_html('<span id="stock-bar-{}">{}</span>', obj.pk, render_stock_bar(obj))
    show_stock_bar.short_description = _('Stock Level')

    def show_stock_status(self, obj):
        return format_html('<span id="stock-status-{}">{}</span>', obj.pk, render_stock_status(obj))
    show_stock_status.short_description = _('Status')

    def show_on_order(self, obj):
        on_order = getattr(obj, 'on_order', None)
        if not on_order or on_order <= 0:
            return MUTED
        return _badge(f'{show_qty(on_order)} {obj.unit} coming', 'info')
    show_on_order.short_description = _('On Order')

    def show_stock_value(self, obj):
        value = float(obj.stock_value)  # ← i-convert sa float
        if value == 0:
            return mark_safe('<span class="text-base-400 dark:text-base-500">₱0.00</span>')
        return format_html('<span class="font-semibold whitespace-nowrap">₱{}</span>', f"{value:,.2f}")
    show_stock_value.short_description = _('Stock Value')

    def show_quick_adjust(self, obj):
        return render_quick_adjust(obj)
    show_quick_adjust.short_description = _('Quick Adjust')

    def show_expiry_status(self, obj):
        if not obj.expiry_date:
            return MUTED
        days_left = (obj.expiry_date - timezone.localdate()).days
        if days_left < 0:
            return _badge('Expired', 'danger')
        elif days_left <= 7:
            return _badge(f'{days_left}d left', 'warning')
        elif days_left <= 30:
            return _badge(f'{days_left}d left', 'info')
        return _badge(f'{days_left}d', 'success')
    show_expiry_status.short_description = _('Expiry')


# ─── StockMovement (standalone) ────────────────────────────────────────────────
# The full history across *all* items, and the place to record a movement for
# any item. Past movements stay read-only and undeletable (except by a
# superuser): editing one after the fact would leave stock disagreeing with the
# history it is supposed to be the sum of.

class MovementSourceFilter(admin.SimpleListFilter):
    title = _('entered by')
    parameter_name = 'source'
    AUTOMATIC = ('usage', 'reversal')

    def lookups(self, request, model_admin):
        return [('staff', _('Staff (manual)')), ('orders', _('Orders (automatic)'))]

    def queryset(self, request, queryset):
        if self.value() == 'staff':
            return queryset.exclude(movement_type__in=self.AUTOMATIC)
        if self.value() == 'orders':
            return queryset.filter(movement_type__in=self.AUTOMATIC)
        return queryset


@admin.register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display        = ['created_at', 'inventory', 'show_movement_type', 'show_quantity_change', 'reference', 'notes', 'performed_by']
    list_filter         = [MovementSourceFilter, 'movement_type', 'inventory', 'created_at']
    list_select_related = ['inventory', 'performed_by']
    search_fields       = ['inventory__name', 'inventory__sku', 'reference', 'notes']
    date_hierarchy      = 'created_at'
    autocomplete_fields = ['inventory']

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs['form'] = StockMovementAddForm
        return super().get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.performed_by = request.user
            if obj.unit_cost is None:
                obj.unit_cost = obj.inventory.cost_per_unit
        super().save_model(request, obj, form, change)

    def show_movement_type(self, obj):
        return _badge(obj.get_movement_type_display(), MOVEMENT_COLORS.get(obj.movement_type, 'base'))
    show_movement_type.short_description = _('Type')

    def show_quantity_change(self, obj):
        return render_movement_change(obj, obj.inventory.unit)
    show_quantity_change.short_description = _('Change')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ─── PurchaseOrder ────────────────────────────────────────────────────────────
# The flow: create (Draft) → mark Sent when you've ordered → items arrive →
# Received. Arrival is what changes stock: whatever you enter under "Received
# so far" (or "Receive all remaining items") is recorded as Stock In against
# this PO, and Partially / Fully Received follow by themselves. See
# inventory/purchasing.py for the rules.

class PurchaseOrderForm(forms.ModelForm):
    # Received / Partially Received aren't offered: they follow from what has
    # actually been received, so picking them by hand could only ever be wrong
    # (that's how a PO ended up "Fully Received" with nothing in stock).
    EDITABLE_STATUSES = ('draft', 'sent', 'cancelled')

    class Meta:
        model = PurchaseOrder
        fields = ['supplier', 'status', 'reference', 'expected_at', 'notes']
        labels = {'reference': _('PO number'), 'expected_at': _('Expected delivery')}
        help_texts = {
            'reference': _('Leave blank and it is numbered for you (e.g. PO-202609-0001).'),
            'status': _(
                'Draft → Sent once you have ordered. Received is set automatically as items arrive — '
                'enter what came in under “Received so far”, or use “Receive all remaining items”.'
            ),
            'expected_at': _('When you expect the delivery.'),
        }
        widgets = {'notes': UnfoldAdminTextareaWidget(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # (A finished order is shown read-only, so these fields aren't on its form at all.)
        if 'reference' in self.fields:
            self.fields['reference'].required = False
        if 'status' in self.fields:
            statuses = list(self.EDITABLE_STATUSES) if self.instance.pk else ['draft', 'sent']
            if self.instance.pk and self.instance.status not in statuses:
                statuses.append(self.instance.status)                   # keep showing what it currently is
            labels = dict(PurchaseOrder.STATUS_CHOICES)
            self.fields['status'].choices = [(status, labels[status]) for status in statuses]

    def clean(self):
        cleaned = super().clean()
        cancelling = self.instance.pk and cleaned.get('status') == 'cancelled' and self.instance.status != 'cancelled'
        if cancelling and any(line.quantity_received > 0 for line in purchasing._lines(self.instance)):
            self.add_error('status', _(
                'Some of this order has already been received, so it cannot be cancelled. '
                'Lower the ordered quantities to what actually arrived instead.'
            ))
        return cleaned


class PurchaseOrderItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderItem
        fields = ['inventory', 'quantity_ordered', 'unit_cost', 'quantity_received']
        labels = {
            'inventory': _('Item'), 'quantity_ordered': _('Order qty'),
            'unit_cost': _('Cost per unit (₱)'), 'quantity_received': _('Received so far'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'unit_cost' in self.fields:                                  # (a finished order's lines are read-only: no fields)
            self.fields['unit_cost'].required = False                   # filled in from the item
        if self.instance.pk and 'inventory' in self.fields:
            self.fields['inventory'].disabled = True                    # what a line is for can't change after the fact

    def clean(self):
        cleaned = super().clean()
        item = cleaned.get('inventory')
        ordered, received = cleaned.get('quantity_ordered'), cleaned.get('quantity_received')
        if cleaned.get('unit_cost') is None and item is not None:
            cleaned['unit_cost'] = item.cost_per_unit
        if ordered is not None and ordered <= 0:
            self.add_error('quantity_ordered', _('Enter how many to order — it must be above 0.'))
        if received is not None:
            if ordered is not None and received > ordered:
                self.add_error('quantity_received', _(
                    'That is more than was ordered. If the supplier really delivered more, raise the ordered quantity first.'
                ))
            # self.instance still holds what is in the database here (it is only
            # overwritten once validation is done).
            already = self.instance.quantity_received if self.instance.pk else Decimal('0')
            if received < already:
                self.add_error('quantity_received', _(
                    'Stock that was already received can’t be taken back here. '
                    'Record a Stock Out (Manual Adjustment) on the item instead.'
                ))
        return cleaned


class PurchaseOrderItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.forms:
            data = getattr(form, 'cleaned_data', None)
            if data and data.get('DELETE') and Decimal(str(form.initial.get('quantity_received') or 0)) > 0:
                raise forms.ValidationError(_('An item that has already been received can’t be removed from the order.'))


class PurchaseOrderItemInline(TabularInline):
    model = PurchaseOrderItem
    form = PurchaseOrderItemForm
    formset = PurchaseOrderItemFormSet
    autocomplete_fields = ['inventory']
    verbose_name = _('item')
    verbose_name_plural = _('Items on this order')

    def _settled(self, obj):
        return obj is not None and purchasing.is_settled(obj)

    def get_fields(self, request, obj=None):
        fields = ['inventory', 'quantity_ordered', 'unit_cost']
        if obj is not None:
            fields.append('quantity_received')                          # nothing can have arrived on a PO that doesn't exist yet
        return fields + ['line_total']

    def get_readonly_fields(self, request, obj=None):
        if self._settled(obj):
            return ['inventory', 'quantity_ordered', 'unit_cost', 'quantity_received', 'line_total']
        return ['line_total']

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0

    def has_add_permission(self, request, obj=None):
        return super().has_add_permission(request, obj) and not self._settled(obj)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and not self._settled(obj)

    @admin.display(description=_('Line total'))
    def line_total(self, obj):
        if obj is None or obj.quantity_ordered is None or obj.unit_cost is None:
            return MUTED
        return _peso(obj.total_cost)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ModelAdmin):
    form                = PurchaseOrderForm
    list_display        = ['reference', 'supplier', 'show_status', 'show_progress', 'show_expected', 'show_total_cost', 'ordered_at']
    list_filter         = ['status', 'supplier', 'ordered_at']
    search_fields       = ['reference', 'supplier__name', 'items__inventory__name']
    list_select_related = ['supplier']
    inlines             = [PurchaseOrderItemInline]
    actions             = ['mark_sent_action', 'receive_remaining_action', 'cancel_action']
    actions_detail      = ['receive_remaining_detail', 'mark_sent_detail']

    STATUS_COLORS = {
        'draft':     'base',
        'sent':      'info',
        'partial':   'warning',
        'received':  'success',
        'cancelled': 'danger',
    }

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')

    # ── the form ──
    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [(None, {'fields': ['supplier', 'status', 'reference', 'expected_at', 'notes']})]
        return [(None, {'fields': ['supplier', 'status', 'reference', 'expected_at', 'received_at', 'created_by', 'notes']})]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        if purchasing.is_settled(obj):                                   # finished orders are a record, not a form
            return ['supplier', 'status', 'reference', 'expected_at', 'received_at', 'created_by', 'notes']
        return ['received_at', 'created_by']

    def has_delete_permission(self, request, obj=None):
        # Only orders that never brought anything in: deleting a received one
        # would leave its Stock In movements pointing at a PO that's gone.
        return super().has_delete_permission(request, obj) and (obj is None or obj.status in ('draft', 'cancelled'))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if request.method == 'GET':
            po = PurchaseOrder.objects.filter(pk=object_id).first()
            if po and po.status == 'received' and not purchasing.is_settled(po):
                self.message_user(request, (
                    f'{po.reference} is marked “Fully Received”, but not all of it has been received into stock. '
                    'Once the delivery is in, press “Receive all remaining items” (top right) — that adds it to stock.'
                ), messages.WARNING)
        return super().change_view(request, object_id, form_url, extra_context)

    # ── saving ──
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        if not obj.reference:
            obj.reference = purchasing.next_reference()
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        if formset.model is not PurchaseOrderItem:
            return super().save_formset(request, form, formset, change)
        # What just arrived = the new "received so far" minus what was recorded
        # before (`initial` is the value from when the page was loaded).
        arrivals = []
        for line_form in formset.forms:
            data = getattr(line_form, 'cleaned_data', None)
            if not data or data.get('DELETE') or 'quantity_received' not in data:
                continue
            arrived = data['quantity_received'] - Decimal(str(line_form.initial.get('quantity_received') or 0))
            if arrived > 0:
                arrivals.append((line_form.instance, arrived))
        formset.save()
        for line, arrived in arrivals:
            purchasing.record_receipt(line, arrived, request.user)
        request._po_arrivals = arrivals

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        po, before = form.instance, form.initial.get('status')
        purchasing.sync_status(po)
        arrivals = getattr(request, '_po_arrivals', [])
        if arrivals:
            self.message_user(request, f'Added to stock: {self._describe(arrivals)}.', messages.SUCCESS)
        if po.status == 'received' and before != 'received':
            self.message_user(request, f'{po.reference} is now fully received.', messages.SUCCESS)

    @staticmethod
    def _describe(arrivals):
        return ', '.join(f'{show_qty(qty)} {line.inventory.unit} {line.inventory.name}' for line, qty in arrivals)

    # ── actions ──
    # Detail buttons appear only when they make sense for that order (Unfold
    # asks has_<name>_permission per order); the list actions accept anything
    # and report per-order what they did or why they skipped it.

    def has_receive_permission(self, request, object_id=None):
        if not self.has_change_permission(request):
            return False
        if object_id is None:
            return True
        po = PurchaseOrder.objects.filter(pk=object_id).first()
        return bool(po) and po.status in ('draft', 'sent', 'partial') or (
            bool(po) and po.status == 'received' and not purchasing.is_settled(po)
        )

    def has_send_permission(self, request, object_id=None):
        if not self.has_change_permission(request):
            return False
        if object_id is None:
            return True
        po = PurchaseOrder.objects.filter(pk=object_id).first()
        return bool(po) and po.status == 'draft'

    def _receive(self, request, po):
        try:
            received = purchasing.receive_remaining(po, request.user)
        except purchasing.PurchaseOrderError as error:
            self.message_user(request, str(error), messages.ERROR)
            return
        if received:
            self.message_user(request, f'{po.reference}: added to stock — {self._describe(received)}.', messages.SUCCESS)
        else:
            self.message_user(request, f'{po.reference}: nothing left to receive.', messages.INFO)

    def _send(self, request, po):
        try:
            purchasing.mark_sent(po)
        except purchasing.PurchaseOrderError as error:
            self.message_user(request, str(error), messages.WARNING)
            return
        self.message_user(request, f'{po.reference} marked as sent to {po.supplier.name}.', messages.SUCCESS)

    @action(description=_('Mark as sent to supplier'), permissions=['send'], icon='send')
    def mark_sent_action(self, request, queryset):
        for po in queryset:
            self._send(request, po)

    @action(description=_('Receive all remaining items into stock'), permissions=['receive'], icon='inventory')
    def receive_remaining_action(self, request, queryset):
        for po in queryset:
            self._receive(request, po)

    @action(description=_('Cancel selected orders'), permissions=['change'], icon='cancel')
    def cancel_action(self, request, queryset):
        for po in queryset:
            try:
                purchasing.cancel(po)
            except purchasing.PurchaseOrderError as error:
                self.message_user(request, str(error), messages.WARNING)
            else:
                self.message_user(request, f'{po.reference} cancelled.', messages.SUCCESS)

    @action(
        description=_('Receive all remaining items'), permissions=['receive'], icon='inventory',
        variant=ActionVariant.PRIMARY, url_path='receive-remaining',
    )
    def receive_remaining_detail(self, request, object_id):
        po = get_object_or_404(PurchaseOrder, pk=object_id)
        self._receive(request, po)
        return redirect(reverse('admin:inventory_purchaseorder_change', args=[po.pk]))

    @action(description=_('Mark as sent'), permissions=['send'], icon='send', url_path='mark-sent')
    def mark_sent_detail(self, request, object_id):
        po = get_object_or_404(PurchaseOrder, pk=object_id)
        self._send(request, po)
        return redirect(reverse('admin:inventory_purchaseorder_change', args=[po.pk]))

    # ── the list ──
    def show_status(self, obj):
        if obj.status == 'received' and not purchasing.is_settled(obj):
            return _badge('Received — not in stock yet', 'warning')      # marked received while items are still short (old data)
        return _badge(obj.get_status_display(), self.STATUS_COLORS.get(obj.status, 'base'))
    show_status.short_description = 'Status'

    def show_progress(self, obj):
        lines = list(obj.items.all())
        if not lines:
            return MUTED
        done = sum(1 for line in lines if line.is_fully_received)
        pct = int(done / len(lines) * 100)
        return format_html(
            '<div class="flex items-center gap-2"><div class="w-16 h-1.5 bg-base-100 dark:bg-base-800 rounded-full overflow-hidden shrink-0">'
            '<div class="h-full rounded-full {}" style="width:{}%"></div></div>'
            '<span class="text-xs whitespace-nowrap">{} of {} received</span></div>',
            'bg-green-500' if pct == 100 else 'bg-primary-500', pct, done, len(lines),
        )
    show_progress.short_description = 'Progress'

    def show_expected(self, obj):
        if not obj.expected_at:
            return MUTED
        text = date_format(obj.expected_at, 'M j, Y')
        if obj.status in purchasing.OPEN_STATUSES and obj.expected_at < timezone.localdate():
            return format_html('{} {}', text, _badge('Overdue', 'danger'))
        return text
    show_expected.short_description = 'Expected'

    def show_total_cost(self, obj):
        total = obj.total_cost
        if total == 0:
            return mark_safe('<span class="text-base-400 dark:text-base-500">₱0.00</span>')
        return format_html('<span class="font-semibold">₱{}</span>', f"{total:,.2f}")
    show_total_cost.short_description = 'Total Cost'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['reorder'] = purchasing.reorder_report()
        extra_context['auto_generate_url'] = reverse('auto-generate-po')
        return super().changelist_view(request, extra_context=extra_context)

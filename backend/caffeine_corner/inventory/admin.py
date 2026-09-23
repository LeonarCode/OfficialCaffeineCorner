import re
from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.db.models import F, Q, Sum
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponse
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
from unfold.forms import BaseDialogForm
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget, UnfoldAdminTextInputWidget

from caffeine_corner.mailer import peso, shop_time

from . import movement_stats, purchasing
from .models import ( Supplier, Inventory,
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



# ─── Supplier ─────────────────────────────────────────────────────────────────

@admin.register(Supplier)
class SupplierAdmin(ModelAdmin):
    list_display  = ['name', 'contact_name', 'email', 'phone', 'show_website', 'is_active']
    list_editable = ['is_active']
    search_fields = ['name', 'email']
    list_filter   = ['is_active']

    @admin.display(description='Website')
    def show_website(self, obj):
        if not obj.website:
            return MUTED
        return format_html('<a href="{0}" target="_blank" rel="noopener" class="text-primary-600 dark:text-primary-500">{1}</a>',
                           obj.website, obj.website.split('//', 1)[-1].rstrip('/'))


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

# Module-level (not InventoryAdmin methods) so both the changelist columns
# (show_stock_bar / show_stock_status) and the detail page (stock_state) draw
# stock the same way.
def render_stock_bar(obj):
    return _stock_bar(obj.quantity_on_hand, obj.reorder_points, obj.unit)


def render_stock_status(obj):
    if obj.quantity_on_hand == 0:
        return _badge('Out of Stock', 'danger')
    if obj.is_low_stock:
        return _badge('Low Stock', 'warning')
    return _badge('OK', 'success')


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
        'name', 'supplier',
        'show_stock_bar', 'show_stock_status', 'show_on_order',
        'show_expiry_status', 'show_stock_value',
    ]
    list_filter         = [StockStatusFilter, 'supplier']
    search_fields       = ['name', 'sku']
    list_select_related = ['supplier']
    inlines             = [StockMovementEntryInline]
    # Said out loud because the "on order" total below groups the query, and a grouped query
    # silently drops the model's default ordering — which would leave the item pickers on the
    # purchase-order and stock-movement forms (20 items a page) free to repeat or skip items.
    ordering            = ['name', 'pk']

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
        item = (_('Item'), {'fields': ['supplier', 'name', 'sku', 'unit']})
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
        history = reverse('admin:inventory_stockmovement_changelist') + f'?inventory__id__exact={obj.pk}&period=all'
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
        return render_stock_bar(obj)
    show_stock_bar.short_description = _('Stock Level')

    def show_stock_status(self, obj):
        return render_stock_status(obj)
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


class PeriodFilter(admin.SimpleListFilter):
    """
    How far back the list (and the overview above it) looks. The chips in the
    overview panel drive it, and it is also in the Filters box. It defaults to the
    last 30 days: with months of order deductions in it, "everything" is a wall of
    rows, and the overview needs a period to mean anything.

    (It must stay a normal, visible filter: Django drops filters that report
    has_output() False, and with them the period would silently stop applying.)
    """
    title = _('period')
    parameter_name = 'period'

    def lookups(self, request, model_admin):
        return movement_stats.PERIODS

    def value(self):
        return movement_stats.normalize_period(super().value())

    def choices(self, changelist):
        # No "All" entry: with no period chosen the default is the last 30 days,
        # so "All" would have quietly meant something else. "All time" is a period.
        for key, label in self.lookup_choices:
            yield {
                'selected': self.value() == key,
                'query_string': changelist.get_query_string({self.parameter_name: key}, remove=['p']),
                'display': label,
            }

    def queryset(self, request, queryset):
        start, end = movement_stats.period_bounds(self.value(), timezone.localdate())
        if start is not None:
            queryset = queryset.filter(created_at__date__gte=start)
        if end is not None:
            queryset = queryset.filter(created_at__date__lt=end)
        return queryset


# What each kind of movement looks like in the list: (arrow, direction, plain-language reason, colour)
MOVEMENT_KIND = {
    'purchase':   ('▲', 'Stock in',  'Delivery / purchase',  'success'),
    'transfer':   ('▲', 'Stock in',  'Transfer in',          'base'),
    'reversal':   ('▲', 'Stock in',  'Order cancelled',      'base'),
    'usage':      ('▼', 'Stock out', 'Used in an order',     'info'),
    'adjustment': ('▼', 'Stock out', 'Manual adjustment',    'warning'),
    'spoilage':   ('▼', 'Stock out', 'Spoilage / waste',     'danger'),
    'return':     ('▼', 'Stock out', 'Returned to supplier', 'warning'),
}
ORDER_REFERENCE = re.compile(r'^Order #CC-(\d+)$')


@admin.register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display = [
        'show_when', 'show_item', 'show_kind', 'show_quantity_change', 'show_value',
        'show_source', 'show_note', 'show_who',
    ]
    list_filter          = [PeriodFilter, MovementSourceFilter, 'movement_type', 'inventory']
    list_select_related  = ['inventory', 'performed_by']
    list_per_page        = 50
    search_fields        = ['inventory__name', 'inventory__sku', 'reference', 'notes']
    autocomplete_fields  = ['inventory']
    list_before_template = 'admin/inventory/stockmovement/overview.html'

    # ── the overview above the list ──
    def changelist_view(self, request, extra_context=None):
        extra_context = {
            **(extra_context or {}),
            'title': _('Stock Movements'),
            'add_url': reverse('admin:inventory_stockmovement_add'),
        }
        response = super().changelist_view(request, extra_context)
        changelist = getattr(response, 'context_data', {}).get('cl')
        if changelist is None:                                        # a redirect (bad filter value) has nothing to summarise
            return response
        period = next(
            (spec.value() for spec in changelist.filter_specs if isinstance(spec, PeriodFilter)),
            movement_stats.DEFAULT_PERIOD,
        )
        only_the_period = not (set(request.GET) - {'period', 'p', 'o'})   # anything else filtering makes "vs last period" meaningless
        response.context_data['movements'] = movement_stats.build_overview(changelist.queryset, period, only_the_period)
        response.context_data['period_chips'] = [
            {'label': label, 'active': key == period, 'url': changelist.get_query_string({'period': key}, remove=['p'])}
            for key, label in movement_stats.PERIODS
        ]
        return response

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

    # ── the list ──
    @admin.display(description=_('When'), ordering='created_at')
    def show_when(self, obj):
        moment = timezone.localtime(obj.created_at)
        return format_html(
            '<span class="an-two an-nowrap"><span class="an-main">{}</span><span class="an-subline">{}</span></span>',
            date_format(moment, 'M j, Y'), date_format(moment, 'g:i A'),
        )

    @admin.display(description=_('Item'), ordering='inventory__name')
    def show_item(self, obj):
        return format_html(
            '<span class="an-two"><a class="an-link" href="{}">{}</a><span class="an-subline">{}</span></span>',
            reverse('admin:inventory_inventory_change', args=[obj.inventory_id]), obj.inventory.name, obj.inventory.sku,
        )

    @admin.display(description=_('What happened'), ordering='movement_type')
    def show_kind(self, obj):
        arrow, direction, reason, variant = MOVEMENT_KIND.get(obj.movement_type, ('', obj.get_movement_type_display(), '', 'base'))
        return format_html(
            '<span class="an-two"><span class="an-pill an-pill--{}">{} {}</span><span class="an-subline">{}</span></span>',
            variant, arrow, direction, reason,
        )

    @admin.display(description=_('Quantity'), ordering='quantity_change')
    def show_quantity_change(self, obj):
        return render_movement_change(obj, obj.inventory.unit)

    @admin.display(description=_('Value'))
    def show_value(self, obj):
        value = abs(obj.quantity_change) * obj.unit_cost
        return format_html('<span class="an-nowrap">{}</span>', _peso(value)) if value else MUTED

    @admin.display(description=_('Source'), ordering='reference')
    def show_source(self, obj):
        reference = obj.reference
        if not reference:
            return MUTED
        order = ORDER_REFERENCE.match(reference)
        if order:                                                    # "Order #CC-00004" -> that order
            return format_html(
                '<a class="an-link an-nowrap" href="{}">{}</a>',
                reverse('admin:online_shop_order_change', args=[int(order.group(1))]), reference,
            )
        if reference.startswith('PO-'):                              # a purchase order's number -> find it in the PO list
            return format_html(
                '<a class="an-link an-nowrap" href="{}?q={}">{}</a>',
                reverse('admin:inventory_purchaseorder_changelist'), reference, reference,
            )
        return format_html('<span class="an-nowrap">{}</span>', reference)

    @admin.display(description=_('Note'))
    def show_note(self, obj):
        if not obj.notes:
            return MUTED
        short = obj.notes if len(obj.notes) <= 46 else obj.notes[:45].rstrip() + '…'
        return format_html('<span class="an-subline" title="{}">{}</span>', obj.notes, short)

    @admin.display(description=_('By'), ordering='performed_by__email')
    def show_who(self, obj):
        if obj.performed_by:
            return format_html('<span class="an-nowrap">{}</span>', obj.performed_by.get_full_name() or obj.performed_by.email)
        return mark_safe('<span class="an-subline">System</span>')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ─── PurchaseOrder ────────────────────────────────────────────────────────────
# The buttons on a purchase order's page (Email to supplier, Receive all, Mark as
# sent) change things, and Unfold draws them as plain links — which a browser
# fetches with GET. A link someone else planted (in a message, on another site)
# could then email a supplier or add stock the moment a logged-in staff member
# clicked it. So each one opens a confirmation first, and only the POST that the
# dialog submits (with Django's CSRF token) does anything; a bare GET just shows
# the dialog.

class _PurchaseOrderDialog(BaseDialogForm):
    """A confirmation with a sentence or two about what is about to happen."""
    form_before_template = 'admin/inventory/purchaseorder/action_dialog.html'
    note = ''

    def get_before_template_context(self, request, object_id=None):
        return {'note': self.note}


class ReceiveDialog(_PurchaseOrderDialog):
    note = _('Every item still outstanding on this order is added to stock now, as if it arrived in full.')


class MarkSentDialog(_PurchaseOrderDialog):
    note = _('This only marks the order as sent — no email goes out. Use “Email to supplier” to send it.')


class ClosePartialDialog(_PurchaseOrderDialog):
    note = _(
        'For when the supplier isn’t sending the rest: every item still short is lowered to what '
        'actually arrived, and the order becomes Fully Received. This can’t be undone by editing a '
        'quantity back — only by recording a new delivery against it.'
    )


class EmailSupplierDialog(BaseDialogForm):
    """Shows who the email goes to, and what it is about, before it is sent."""
    form_before_template = 'admin/inventory/purchaseorder/email_dialog.html'

    def get_before_template_context(self, request, object_id=None):
        po = PurchaseOrder.objects.select_related('supplier').filter(pk=object_id).first()
        if po is None:
            return {}
        lines = list(po.items.all())
        return {
            'supplier': po.supplier.name,
            'address': (po.supplier.email or '').strip(),
            'supplier_url': reverse('admin:inventory_supplier_change', args=[po.supplier_id]),
            'reference': po.reference,
            'line_count': len(lines),
            'total': peso(sum((line.total_cost for line in lines), Decimal('0'))),
            'expected': date_format(po.expected_at, 'F j, Y') if po.expected_at else '',
            'emailed': date_format(shop_time(po.emailed_at), 'F j, Y \\a\\t g:i A') if po.emailed_at else '',
            'will_be_marked_sent': po.status == 'draft',
        }


# The flow: create (Draft) → mark Sent when you've ordered → items arrive →
# Received. Arrival is what changes stock: whatever you enter under "Received
# so far" (or "Receive all remaining items") is recorded as Stock In against
# this PO, and Partially / Fully Received follow by themselves. If the
# supplier stops short and isn't sending the rest, "Close as partially
# received" is what finishes it instead — see purchasing.close_partial().
# See inventory/purchasing.py for the rules.

class PurchaseOrderForm(forms.ModelForm):
    # Received / Partially Received aren't offered: they follow from what has
    # actually been received, so picking them by hand could only ever be wrong
    # (that's how a PO ended up "Fully Received" with nothing in stock).
    EDITABLE_STATUSES = ('draft', 'sent', 'cancelled')

    class Meta:
        model = PurchaseOrder
        # No 'reference' here — it is never typed, on this form or any other (see
        # PurchaseOrder.save()): numbered from the order's own id the moment it
        # exists, shown read-only once it does (PurchaseOrderAdmin.get_readonly_fields).
        fields = ['supplier', 'status', 'expected_at', 'notes']
        labels = {'expected_at': _('Expected delivery')}
        help_texts = {
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
                'Close it as partially received instead.'
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
        if self.instance.pk:
            # What a line is *for* is fixed the moment it's saved — item, how much,
            # at what cost. A new line (still being added to the order) is unaffected:
            # this only locks a row once it already exists. Reconciling what actually
            # arrived against what was ordered, when they don't match, is a deliberate
            # action instead (PurchaseOrderAdmin.close_partial_detail) — not a value
            # quietly typed over here.
            for name in ('inventory', 'quantity_ordered', 'unit_cost'):
                if name in self.fields:
                    self.fields[name].disabled = True

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
                self.add_error('quantity_received', _('That is more than was ordered.'))
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
    list_display        = ['reference', 'supplier', 'show_status', 'show_progress', 'show_emailed', 'show_expected', 'show_total_cost', 'ordered_at']
    list_filter         = ['status', 'supplier', 'ordered_at']
    search_fields       = ['reference', 'supplier__name', 'items__inventory__name']
    list_select_related = ['supplier']
    inlines             = [PurchaseOrderItemInline]
    actions             = ['email_suppliers_action', 'mark_sent_action', 'receive_remaining_action', 'close_partial_action', 'cancel_action']
    actions_detail      = ['email_supplier_detail', 'receive_remaining_detail', 'close_partial_detail', 'mark_sent_detail']

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
        # No 'reference' on a new order — there is nothing to show yet (it is
        # numbered from the order's own id, which doesn't exist until it's saved).
        if obj is None:
            return [(None, {'fields': ['supplier', 'status', 'expected_at', 'notes']})]
        return [(None, {'fields': ['reference', 'supplier', 'status', 'expected_at', 'received_at', 'emailed_to_supplier', 'created_by', 'notes']})]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        if purchasing.is_settled(obj):                                   # finished orders are a record, not a form
            return ['reference', 'supplier', 'status', 'expected_at', 'received_at', 'emailed_to_supplier', 'created_by', 'notes']
        return ['reference', 'received_at', 'emailed_to_supplier', 'created_by']    # numbered automatically, never typed

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
            elif po and po.status in purchasing.OPEN_STATUSES and not (po.supplier.email or '').strip():
                self.message_user(request, (
                    f'{po.supplier.name} has no email address on file, so this order can’t be emailed to them yet. '
                    'Add one on the supplier’s page.'
                ), messages.WARNING)
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.display(description=_('Emailed to supplier'))
    def emailed_to_supplier(self, obj):
        if not obj.emailed_at:
            return mark_safe('<span class="text-base-500">Not emailed yet</span>')
        return format_html('{} <span class="text-base-500">(to {})</span>',
                           date_format(shop_time(obj.emailed_at), 'F j, Y, g:i A'), obj.supplier.email or obj.supplier.name)

    # ── saving ──
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)          # a blank reference numbers itself — see PurchaseOrder.save()

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

    def has_email_permission(self, request, object_id=None):
        if not self.has_change_permission(request):
            return False
        if object_id is None:
            return True
        po = PurchaseOrder.objects.filter(pk=object_id).first()
        return bool(po) and po.status in purchasing.OPEN_STATUSES

    def has_close_partial_permission(self, request, object_id=None):
        if not self.has_change_permission(request):
            return False
        if object_id is None:
            return True
        po = PurchaseOrder.objects.filter(pk=object_id).first()
        return bool(po) and po.status == 'partial'

    @staticmethod
    def _back_to(request, po):
        """Back to the order's page — from a confirmation dialog (an htmx request) that means telling htmx to load it."""
        url = reverse('admin:inventory_purchaseorder_change', args=[po.pk])
        if request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = url
            return response
        return redirect(url)

    def _email(self, request, po):
        was_draft, before = po.status == 'draft', po.emailed_at
        try:
            address = purchasing.email_to_supplier(po, request.user)
        except purchasing.PurchaseOrderError as error:
            self.message_user(request, str(error), messages.ERROR)
            return False
        text = f'{po.reference} was {"emailed again" if before else "emailed"} to {po.supplier.name} ({address})'
        self.message_user(request, text + (' and marked as sent.' if was_draft else '.'), messages.SUCCESS)
        return True

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

    def _close_partial(self, request, po):
        try:
            purchasing.close_partial(po)
        except purchasing.PurchaseOrderError as error:
            self.message_user(request, str(error), messages.WARNING)
            return
        self.message_user(request, f'{po.reference} closed as fully received — what didn’t arrive was dropped from the order.', messages.SUCCESS)

    @action(description=_('Email selected orders to their suppliers'), permissions=['email'], icon='mail')
    def email_suppliers_action(self, request, queryset):
        for po in queryset.select_related('supplier'):
            self._email(request, po)

    @action(description=_('Mark as sent (without emailing)'), permissions=['send'], icon='send')
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

    @action(description=_('Close as partially received (nothing more is coming)'), permissions=['close_partial'], icon='playlist_add_check')
    def close_partial_action(self, request, queryset):
        for po in queryset:
            self._close_partial(request, po)

    @action(
        description=_('Email to supplier'), permissions=['email'], icon='mail',
        variant=ActionVariant.PRIMARY, url_path='email-supplier',
        dialog={'title': _('Email this order to the supplier?'), 'description': '', 'form_class': EmailSupplierDialog,
                'form_submit_text': _('Send email')},
    )
    def email_supplier_detail(self, request, form, object_id):
        po = get_object_or_404(PurchaseOrder.objects.select_related('supplier'), pk=object_id)
        self._email(request, po)
        return self._back_to(request, po)

    @action(
        description=_('Receive all remaining items'), permissions=['receive'], icon='inventory',
        variant=ActionVariant.PRIMARY, url_path='receive-remaining',
        dialog={'title': _('Receive everything still outstanding?'), 'description': '', 'form_class': ReceiveDialog,
                'form_submit_text': _('Add to stock')},
    )
    def receive_remaining_detail(self, request, form, object_id):
        po = get_object_or_404(PurchaseOrder, pk=object_id)
        self._receive(request, po)
        return self._back_to(request, po)

    @action(
        description=_('Mark as sent (no email)'), permissions=['send'], icon='send',
        variant=ActionVariant.PRIMARY, url_path='mark-sent',
        dialog={'title': _('Mark this order as sent?'), 'description': '', 'form_class': MarkSentDialog,
                'form_submit_text': _('Mark as sent')},
    )
    def mark_sent_detail(self, request, form, object_id):
        po = get_object_or_404(PurchaseOrder, pk=object_id)
        self._send(request, po)
        return self._back_to(request, po)

    @action(
        description=_('Close as partially received'), permissions=['close_partial'], icon='playlist_add_check',
        variant=ActionVariant.PRIMARY, url_path='close-partial',
        dialog={'title': _('Close this order as partially received?'), 'description': '', 'form_class': ClosePartialDialog,
                'form_submit_text': _('Close order')},
    )
    def close_partial_detail(self, request, form, object_id):
        po = get_object_or_404(PurchaseOrder, pk=object_id)
        self._close_partial(request, po)
        return self._back_to(request, po)

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

    @admin.display(description='Emailed')
    def show_emailed(self, obj):
        if obj.emailed_at:
            return format_html('<span class="an-nowrap" title="Last emailed to the supplier">✉ {}</span>',
                               date_format(shop_time(obj.emailed_at), 'M j, g:i A'))
        if obj.status in purchasing.OPEN_STATUSES:
            return mark_safe('<span class="an-subline">Not emailed yet</span>')
        return MUTED

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

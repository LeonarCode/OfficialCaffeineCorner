from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html_join
from unfold.admin import ModelAdmin, TabularInline, format_html, mark_safe
from .models import ActivityLog, Category, Product, Variant, Rating, Order, OrderItem, LoyaltyPoint, Notification, Remittance, TownZone
from . import ratings, remittance, rider_availability
from inventory.models import Ingredient
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


STATUS_COLORS = {
    'pending':    'warning',
    'confirmed':  'info',
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


def _htmx_select(*, url, name, current_value, choices, colors):
    """
    A <select> styled like a colored badge that saves on change via HTMX —
    no page reload, no separate "Save" button. Swaps its own <td> with the
    response HTML (itself, re-rendered with the new value/color) so it
    keeps working for the next change too. Backs OrderAdmin.show_status
    and show_payment_status; see htmx_set_order_status/htmx_set_payment_status
    in views.py for the other half.

    No `name` attribute here — that's deliberate, not an oversight. Every
    row on the Orders changelist has one of these selects, and they all sit
    inside Django's one big #changelist-form (it wraps the whole results
    table, for bulk actions). htmx always merges in every *named* field of
    a triggering element's closest enclosing form for a POST, the same way
    a native form submit would — hx-include only ever adds more sources on
    top of that, it can't turn it off, and hx-params can't selectively drop
    just the duplicates either (it's a same-or-nothing filter over the
    already-merged result, applied *after* hx-vals is merged in too — tried
    hx-params="none" first, thinking it'd suppress only the form; it wiped
    the select's own hx-vals value along with it). Confirmed the original
    bug the hard way against a real multi-order list: changing the newest
    order's status silently overwrote it with the oldest order's status
    instead, since request.POST.get('status') just returns whichever
    same-named field the request happened to list last. A field with no
    `name` isn't a "successful" form control at all (same rule browsers use
    for native submits), so it's invisible to that automatic collection —
    hx-vals below, reading event.target.value at request time, is then the
    *only* source for this field, no collision possible.
    """
    options = mark_safe(''.join(
        format_html(
            '<option value="{}"{}>{}</option>',
            value, ' selected' if value == current_value else '', label,
        )
        for value, label in choices
    ))
    variant = colors.get(current_value, 'base')
    vals = mark_safe('js:{"' + name + '": event.target.value}')
    return format_html(
        '<select hx-post="{}" hx-trigger="change" hx-target="closest td" hx-swap="innerHTML" '
        'hx-vals=\'{}\' '
        'class="font-semibold rounded-default text-[11px] pl-2 pr-6 py-1 border-0 cursor-pointer '
        'focus:outline-none focus:ring-2 focus:ring-primary-500 {}">{}</select>',
        url, vals, BADGE_VARIANTS.get(variant, BADGE_VARIANTS['base']), options,
    )


def render_status_select(order):
    return _htmx_select(
        url=reverse('htmx-order-status', args=[order.pk]),
        name='status',
        current_value=order.status,
        choices=Order.STATUS_CHOICES,
        colors=STATUS_COLORS,
    )


def render_payment_select(order):
    return _htmx_select(
        url=reverse('htmx-order-payment', args=[order.pk]),
        name='payment_status',
        current_value=order.payment_status,
        choices=Order.PAYMENT_STATUS_CHOICES,
        colors=PAYMENT_COLORS,
    )


# NOTE: these loop + call .save() per order instead of queryset.update().
# .update() runs straight in SQL and skips Model.save(), which means it
# never fires pre_save/post_save — so notifications, activity logs, and
# (critically) the ingredient-stock restore-on-cancel signal would silently
# never run. Order counts here are small (admin selections), so the extra
# per-row save is cheap and correctness matters more.

@admin.action(description='✅ Mark as Confirmed')
def mark_confirmed(modeladmin, request, queryset):
    updated = 0
    for order in queryset.exclude(status='cancelled'):
        order.status = 'confirmed'
        order.save()
        updated += 1
    modeladmin.message_user(request, f'{updated} order(s) marked as Confirmed.')

@admin.action(description='🎉 Mark as Delivered')
def mark_delivered(modeladmin, request, queryset):
    updated = 0
    for order in queryset.exclude(status='cancelled'):
        order.status = 'delivered'
        order.save()
        updated += 1
    modeladmin.message_user(request, f'{updated} order(s) marked as Delivered.')

@admin.action(description='❌ Mark as Cancelled')
def mark_cancelled(modeladmin, request, queryset):
    updated = 0
    for order in queryset:
        order.status = 'cancelled'
        order.save()
        updated += 1
    modeladmin.message_user(request, f'{updated} order(s) marked as Cancelled.')

@admin.action(description='💰 Mark Payment as Paid')
def mark_payment_paid(modeladmin, request, queryset):
    updated = 0
    for order in queryset:
        order.payment_status = 'paid'
        order.save()
        updated += 1
    modeladmin.message_user(request, f'{updated} order(s) marked as Paid.')

@admin.action(description='⏳ Mark Payment as Unpaid')
def mark_payment_unpaid(modeladmin, request, queryset):
    updated = 0
    for order in queryset:
        order.payment_status = 'unpaid'
        order.save()
        updated += 1
    modeladmin.message_user(request, f'{updated} order(s) marked as Unpaid.')


# Shared between NotificationAdmin.mark_read_link (changelist column) and
# the dashboard's notifications widget (templates/admin/index.html) — both
# post to htmx_mark_notification_read (inventory/views.py) and swap this
# back in, no page reload either way.
def render_notif_read_cell(notif):
    if notif.is_read:
        return mark_safe('<span class="text-base-400 dark:text-base-500 text-xs">✓ Read</span>')
    return format_html(
        '<a href="#" hx-post="{}" hx-target="closest td" hx-swap="innerHTML" '
        'class="text-primary-600 dark:text-primary-500 hover:text-primary-700 dark:hover:text-primary-400 text-xs font-semibold cursor-pointer">Mark as Read</a>',
        reverse('mark-notification-read', args=[notif.id]),
    )


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
        return render_notif_read_cell(obj)
    mark_read_link.short_description = 'Action'

@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    # Not in the sidebar any more — a category is something you add while
    # adding/editing a product ("+" next to the Category field), not a
    # separate destination. Staying registered keeps that "+" working; this
    # list is still here (linked from that same field) for reordering or
    # deactivating one.
    list_display = ['name', 'sort_order', 'is_active']
    list_editable = ['sort_order', 'is_active']
    search_fields = ['name']


PRICE_CHANGE_NOTE = (
    'Changing a price only affects new orders. Orders already placed keep '
    'the price they were ordered at.'
)


class VariantInline(TabularInline):
    model = Variant
    extra = 0        # ← walang blank rows by default
    min_num = 0      # ← hindi required maglagay ng variant
    can_delete = True

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'additional_price':
            formfield.help_text = PRICE_CHANGE_NOTE
        return formfield


class IngredientInline(TabularInline):
    model = Ingredient
    fk_name = 'product'
    extra = 0
    fields = ['inventory', 'quantity', 'unit', 'notes']
    autocomplete_fields = ['inventory']


class OrderItemInline(TabularInline):
    model = OrderItem
    autocomplete_fields = ['product']  # 'variant' excluded — see CartItemInline in authentication/admin.py
    fields = ['product', 'variant', 'quantity', 'price', 'get_subtotal']

    # Read-only when viewing an existing order (line items are a snapshot of
    # what was actually ordered — editing them after the fact would silently
    # disagree with the inventory deductions already made at order time).
    # On the add form though, there's no snapshot yet to protect — staff
    # need to actually be able to pick products for a manually-entered
    # order, so every field but the computed subtotal opens up there.
    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ['get_subtotal']
        return ['product', 'variant', 'quantity', 'price', 'get_subtotal']

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0

    # Price is auto-filled from the Product/Variant on selection (see
    # static/js/orderitem-price.js) — locked to that instead of a free-typed
    # value, so it can't drift from the actual product price by accident.
    # Subtotal (qty × price, same script) is what staff actually read off
    # this row. `readonly` attr, not `disabled` — disabled inputs are
    # dropped from the submitted form entirely, which would leave price
    # blank (it's required on OrderItem); readonly still submits the value,
    # it just can't be typed into directly.
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'price':
            formfield.widget.attrs['readonly'] = 'readonly'
        return formfield

    def get_subtotal(self, obj):
        if obj.price and obj.quantity:
            return f'₱{obj.price * obj.quantity:.2f}'
        return '—'
    get_subtotal.short_description = 'Subtotal'


class RatingFilter(admin.SimpleListFilter):
    """Products by how customers rated them (uses the average annotated in ProductAdmin.get_queryset)."""
    title = 'customer rating'
    parameter_name = 'rating_band'

    def lookups(self, request, model_admin):
        return [
            ('4', '4 stars & up'),
            ('3', '3 to 4 stars'),
            ('low', 'Under 3 stars'),
            ('none', 'No ratings yet'),
        ]

    def queryset(self, request, queryset):
        band = self.value()
        if band == '4':
            return queryset.filter(avg_rating__gte=4)
        if band == '3':
            return queryset.filter(avg_rating__gte=3, avg_rating__lt=4)
        if band == 'low':
            return queryset.filter(avg_rating__lt=3)                # products with no ratings have a NULL average, so they aren't in here
        if band == 'none':
            return queryset.filter(rating_count=0)
        return queryset


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_available', 'is_featured', 'is_seasonal', 'sort_order']
    list_filter = ['category', RatingFilter, 'is_available', 'is_featured', 'is_seasonal']
    search_fields = ['name', 'sku']
    inlines = [VariantInline, IngredientInline]

    # One query gives every card its rating (the list is a grid of cards: see
    # templates/admin/online_shop/product/change_list.html).
    def get_queryset(self, request):
        return super().get_queryset(request).annotate(avg_rating=Avg('ratings__rating'), rating_count=Count('ratings'))

    # Order lines store their own copy of the price (OrderItem.price), so this
    # is only a reassurance for staff — no code path re-prices old orders.
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'price':
            formfield.help_text = PRICE_CHANGE_NOTE
        if db_field.name == 'category':
            # The "+" next to the field adds one; this is for reordering or
            # deactivating an existing one — not otherwise reachable now that
            # Categories isn't in the sidebar (see CategoryAdmin).
            formfield.help_text = format_html(
                'Use the <span class="material-symbols-outlined align-middle text-sm">more_vert</span> menu to add '
                'one on the spot, or <a class="text-primary-600 dark:text-primary-500 font-medium" href="{}">manage categories</a> '
                'to reorder or deactivate one.',
                reverse('admin:online_shop_category_changelist'),
            )
        return formfield

    # ── customer ratings, on the product itself ──
    def get_readonly_fields(self, request, obj=None):
        return ['rating_summary'] if obj is not None else []

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets
        rest = [(name, {**options, 'fields': [f for f in options['fields'] if f != 'rating_summary']}) for name, options in fieldsets]
        return [('Customer ratings', {'fields': ['rating_summary']})] + rest

    @admin.display(description='')
    def rating_summary(self, obj):
        all_ratings = reverse('admin:online_shop_rating_changelist') + f'?product__id__exact={obj.pk}'
        return mark_safe(render_to_string(
            'admin/online_shop/product/_rating_summary.html',
            {'summary': ratings.summarize(obj), 'all_url': all_ratings},
        ))


# System/other-flow/delivery-only fields — never relevant to a manually
# keyed-in order: the system ones are set by the payment gateway, the rider
# app, or the loyalty logic later on; the delivery ones don't apply because
# manually-added orders are always Dine-in (see OrderAdmin.save_model) — a
# staff member at the counter isn't taking someone's delivery address, zone,
# or a bulk/catering event date. Module-level (not a class attribute) since
# it's referenced from inside OrderAdmin.ADD_FIELDS's list comprehension,
# and comprehensions don't see their enclosing class body.
ORDER_ADD_EXCLUDED_FIELDS = {
    'paymongo_id', 'gcash_ref', 'assigned_rider', 'assigned_rider_at',
    'delivery_proof_photo', 'delivered_at', 'rider_notes',
    'points_earned', 'points_used',
    'order_type', 'address', 'zone',
    'delivery_latitude', 'delivery_longitude', 'delivery_fee', 'event_date',
}


# ─── Order groups: Dine-in / Pick-up / Delivery ───────────────────────────────
# The Orders list is split into these three groups — tabs above the list (see
# templates/admin/order_change_list.html), each with its own count and its own
# columns. Their order here is the order of the tabs. The stored code for a
# delivery order is "regular", so that is the key; its label comes from the model.
ORDER_GROUPS = ('dine_in', 'pickup', 'regular')
ORDER_GROUP_LABELS = dict(Order.ORDER_TYPE_CHOICES)
ORDER_GROUP_ICONS = {'dine_in': 'restaurant', 'pickup': 'shopping_bag', 'regular': 'local_shipping'}
ORDER_GROUP_PILLS = {'dine_in': 'primary', 'pickup': 'info', 'regular': 'success'}

MUTED = mark_safe('<span class="text-base-400 dark:text-base-500">—</span>')


class OrderTypeFilter(admin.SimpleListFilter):
    """
    Which group the list shows. The tabs above the list drive it, and it is in the
    Filters box too, so the two always agree. An unknown value just means "all".

    (It must stay a normal, visible filter: Django drops a filter that reports
    has_output() False, and with it the filtering.)
    """
    title = 'order type'
    parameter_name = 'order_type'

    def lookups(self, request, model_admin):
        return [(key, ORDER_GROUP_LABELS[key]) for key in ORDER_GROUPS]

    def queryset(self, request, queryset):
        if self.value() in ORDER_GROUPS:
            return queryset.filter(order_type=self.value())
        return queryset


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_before_template = 'admin/order_change_list.html'

    # Each group shows the columns that mean something for it: a dine-in order has
    # a table and no address, a delivery has a zone, a rider and a map pin. (Before,
    # every order showed a "Location: No pin" column, which only ever applied to
    # deliveries.) `get_list_display` picks the set from the ?order_type= in the URL.
    LIST_COLUMNS = {
        '': [
            'id', 'show_customer', 'show_order_type', 'show_where', 'show_status', 'payment_method',
            'show_payment_status', 'total_price', 'created_at', 'print_receipt_link',
        ],
        'dine_in': [
            'id', 'show_table', 'show_customer', 'show_status', 'payment_method',
            'show_payment_status', 'total_price', 'created_at', 'print_receipt_link',
        ],
        'pickup': [
            'id', 'show_customer', 'show_status', 'payment_method',
            'show_payment_status', 'total_price', 'created_at', 'print_receipt_link',
        ],
        'regular': [
            'id', 'show_customer', 'show_zone', 'show_rider', 'show_status', 'payment_method',
            'show_payment_status', 'total_price', 'created_at', 'show_map_link', 'print_receipt_link',
        ],
    }
    list_display    = LIST_COLUMNS['']          # (the default; also what Django's admin checks validate)
    list_filter     = ['status', 'payment_method', 'payment_status', OrderTypeFilter]
    list_select_related = ['zone', 'assigned_rider']
    search_fields   = ['email', 'phone', 'id']
    inlines         = [OrderItemInline]
    actions         = [
        mark_confirmed,
        mark_delivered,
        mark_cancelled,
        mark_payment_paid,
        mark_payment_unpaid,
    ]

    # Always shown on the change form, whatever their value.
    ALWAYS_FIELDS = [
        'email', 'phone', 'address', 'order_type', 'status',
        'payment_method', 'payment_status', 'total_price', 'item_count',
        'created_at', 'updated_at',
    ]
    # Shown only when the order actually has a value for them.
    OPTIONAL_FIELDS = [
        'user', 'notes', 'event_date', 'pax', 'table_number', 'zone', 'delivery_fee',
        'gcash_ref', 'paymongo_id', 'delivery_proof_photo', 'delivered_at',
        'rider_notes', 'points_earned', 'points_used', 'discount',
        'downpayment_amount', 'remaining_balance',
        'delivery_latitude', 'delivery_longitude',  # ← dagdag para makita sa detail view
    ]
    ADD_FIELDS = [f.name for f in Order._meta.fields if f.name != 'id' and f.name not in ORDER_ADD_EXCLUDED_FIELDS]
    ADD_READONLY_FIELDS = ['created_at', 'updated_at']

    def get_fields(self, request, obj=None):
        if obj is None:
            return self.ADD_FIELDS
        fields = list(self.ALWAYS_FIELDS)
        for name in self.OPTIONAL_FIELDS:
            if getattr(obj, name, None):
                fields.append(name)
        fields.append('assigned_rider')
        return fields

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return self.ADD_READONLY_FIELDS
        return [f for f in self.get_fields(request, obj) if f != 'assigned_rider']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Who's offered here follows the batching rule (online_shop/rider_availability.py):
        # up to a few same-zone deliveries are fine while their prep time is still
        # running, anything else isn't offered until those orders have had time to
        # actually be made. Their own order (the one being edited right now) doesn't
        # count against them: otherwise saving this same order a second time would
        # find its own rider missing from the list.
        if db_field.name == 'assigned_rider':
            object_id = request.resolver_match.kwargs.get('object_id') if request.resolver_match else None
            order = Order.objects.select_related('zone').filter(pk=object_id).first() if object_id else None
            zone = order.zone if order else None
            available_ids = [
                rider.pk for rider in get_user_model().objects.filter(is_rider=True)
                if rider_availability.is_available_for(rider, zone, object_id)
            ]
            kwargs['queryset'] = get_user_model().objects.filter(pk__in=available_ids)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        # Manually-added orders are always Dine-in — order_type isn't even
        # on the add form anymore (see ORDER_ADD_EXCLUDED_FIELDS): a
        # walk-in/phone-in order staff key in at the counter, never a
        # delivery/pickup order (those come through the customer-facing
        # site). Only forced on creation — never touches an existing order's
        # type on a later save.
        if not change:
            obj.order_type = 'dine_in'
        super().save_model(request, obj, form, change)

    def get_list_display(self, request):
        return self.LIST_COLUMNS.get(request.GET.get(OrderTypeFilter.parameter_name), self.LIST_COLUMNS[''])

    def get_queryset(self, request):
        # total_price reads each order's items: fetch them all at once, not one
        # query per row.
        return super().get_queryset(request).prefetch_related('items')

    # ── the groups (tabs above the list) ──
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        changelist = getattr(response, 'context_data', {}).get('cl')
        if changelist is None:                                   # a redirect (bad filter value): nothing to summarise
            return response
        tabs, current = self._group_tabs(request, changelist)
        response.context_data['order_tabs'] = tabs
        response.context_data['export_group'] = current
        response.context_data['export_group_label'] = ORDER_GROUP_LABELS.get(current, '')
        return response

    def _group_tabs(self, request, changelist):
        """
        One tab per group, plus "All": how many orders, and how many of them are
        still pending. The counts follow every other filter and the search (so with
        "Pending" chosen, each tab counts its pending orders) but not the group
        itself — otherwise choosing Delivery would zero the other tabs.
        """
        spec = next((s for s in changelist.filter_specs if isinstance(s, OrderTypeFilter)), None)
        current = spec.value() if spec is not None and spec.value() in ORDER_GROUPS else ''

        scope = changelist.get_queryset(request, exclude_parameters=[OrderTypeFilter.parameter_name])
        rows = (
            scope.order_by().prefetch_related(None)              # (prefetching makes no sense on a values() query)
            .values('order_type').annotate(n=Count('id'), pending=Count('id', filter=Q(status='pending')))
        )
        counts = {row['order_type']: (row['n'], row['pending']) for row in rows}
        total = sum(n for n, _p in counts.values())
        pending = sum(p for _n, p in counts.values())

        tabs = [{'key': '', 'label': 'All orders', 'icon': 'receipt_long', 'count': total, 'pending': pending}]
        for key in ORDER_GROUPS:
            n, p = counts.get(key, (0, 0))
            tabs.append({'key': key, 'label': ORDER_GROUP_LABELS[key], 'icon': ORDER_GROUP_ICONS[key], 'count': n, 'pending': p})
        for tab in tabs:
            tab['active'] = tab['key'] == current
            # A new group keeps the search and every other filter, but not the sort
            # (the columns differ from group to group, so "sort by column 5" means
            # something else in another one) and not "show all". The page number is
            # never carried over by get_query_string, so a new group starts on page one.
            # None removes exactly that key: `remove=['o']` would also drop everything
            # *starting* with "o" (order_type itself), and `remove=['p']` the payment filters.
            tab['url'] = changelist.get_query_string({'order_type': tab['key'] or None, 'o': None, 'all': None})
        return tabs, current

    # ── columns ──
    @admin.display(description='Customer', ordering='email')
    def show_customer(self, obj):
        # Email and phone in one cell (email on top, the number under it) rather than
        # two columns: it keeps a delivery's twelve columns on one screen, and the
        # number a rider needs stays in view. A dine-in order has no phone.
        if obj.phone:
            return format_html('<span class="an-two"><span class="an-nowrap">{}</span><span class="an-subline an-nowrap">{}</span></span>', obj.email, obj.phone)
        return format_html('<span class="an-nowrap">{}</span>', obj.email)

    @admin.display(description='Type', ordering='order_type')
    def show_order_type(self, obj):
        key = obj.order_type
        if key not in ORDER_GROUPS:                                # an old type that isn't one of the three
            return format_html('<span class="an-pill an-pill--base">{}</span>', obj.get_order_type_display())
        return format_html(
            '<span class="an-pill an-pill--{}"><span class="material-symbols-outlined" style="font-size:14px">{}</span>{}</span>',
            ORDER_GROUP_PILLS[key], ORDER_GROUP_ICONS[key], ORDER_GROUP_LABELS[key],
        )

    @admin.display(description='Where')
    def show_where(self, obj):
        if obj.order_type == 'dine_in':
            return format_html('<span class="an-nowrap">Table {}</span>', obj.table_number) if obj.table_number else MUTED
        if obj.order_type == 'regular':
            return format_html('<span class="an-nowrap">{}</span>', obj.zone.name) if obj.zone_id else MUTED
        if obj.order_type == 'pickup':
            return mark_safe('<span class="an-subline">At the counter</span>')
        return MUTED

    @admin.display(description='Table', ordering='table_number')
    def show_table(self, obj):
        return format_html('<span class="an-main an-nowrap">Table {}</span>', obj.table_number) if obj.table_number else MUTED

    @admin.display(description='Zone', ordering='zone__name')
    def show_zone(self, obj):
        if not obj.zone_id:
            return MUTED
        return format_html(
            '<span class="an-two"><span class="an-main an-nowrap">{}</span><span class="an-subline an-nowrap">₱{} fee</span></span>',
            obj.zone.name, f'{obj.delivery_fee:,.2f}',
        )

    @admin.display(description='Rider', ordering='assigned_rider__email')
    def show_rider(self, obj):
        if obj.assigned_rider_id:
            return format_html('<span class="an-nowrap">{}</span>', obj.assigned_rider.get_full_name() or obj.assigned_rider.email)
        if obj.status == 'confirmed':                              # confirmed but nobody is bringing it yet: that needs doing
            return _badge('Needs a rider', 'warning')
        if obj.status == 'pending':
            return mark_safe('<span class="an-subline">Not assigned yet</span>')
        return MUTED                                               # delivered / cancelled

    # Colored <select> instead of a static badge — changing it saves via
    # HTMX immediately (see render_status_select / htmx_set_order_status),
    # no need to open the order just to flip its status.
    def show_status(self, obj):
        return render_status_select(obj)
    show_status.short_description = 'Status'
    show_status.admin_order_field = 'status'

    def show_payment_status(self, obj):
        return render_payment_select(obj)
    show_payment_status.short_description = 'Payment Status'
    show_payment_status.admin_order_field = 'payment_status'

    def show_map_link(self, obj):
        if obj.delivery_latitude and obj.delivery_longitude:
            url = f'https://www.google.com/maps?q={obj.delivery_latitude},{obj.delivery_longitude}'
            return format_html(
                '<a href="{}" target="_blank" '
                'class="font-medium inline-flex items-center gap-1 rounded-default whitespace-nowrap '
                'px-2.5 py-1 text-[11px] border border-base-200 bg-primary-600 border-transparent '
                'text-white hover:bg-primary-600/80">📍 View Map</a>',
                url
            )
        # format_html() with no substitution args raises TypeError on this
        # Django version ("args or kwargs must be provided") — mark_safe is
        # the right tool for a plain static string with nothing to escape.
        return mark_safe('<span class="text-base-400 text-[11px]">No pin</span>')
    show_map_link.short_description = 'Location'

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
    # Not in the sidebar any more — a product's page shows its ratings, and links
    # here ("Manage all N ratings") for moderating them.
    list_display = ['show_product', 'show_stars', 'show_review', 'user', 'created_at']
    list_filter = ['rating', 'product']
    list_select_related = ['product', 'user']
    search_fields = ['product__name', 'user__email', 'review']

    @admin.display(description='Product', ordering='product__name')
    def show_product(self, obj):
        return format_html('<a class="an-link" href="{}">{}</a>', reverse('admin:online_shop_product_change', args=[obj.product_id]), obj.product.name)

    @admin.display(description='Rating', ordering='rating')
    def show_stars(self, obj):
        return ratings.stars_markup(obj.rating, small=True)

    @admin.display(description='Review')
    def show_review(self, obj):
        if not obj.review:
            return mark_safe('<span class="an-subline">No comment</span>')
        short = obj.review if len(obj.review) <= 80 else obj.review[:79].rstrip() + '…'
        return format_html('<span title="{}">{}</span>', obj.review, short)


@admin.register(LoyaltyPoint)
class LoyaltyPointAdmin(ModelAdmin):
    list_display = ['user', 'points', 'discount_value', 'redeemable_points', 'last_updated']
    search_fields = ['user__email']
    readonly_fields = ['discount_value', 'redeemable_points', 'last_updated']


@admin.register(Remittance)
class RemittanceAdmin(ModelAdmin):
    # A record, not a form — every one is created by authentication.admin.UserAdmin's
    # "Record remittance" button, which is what guarantees the amount actually
    # matches what the rider was holding. Typing one in by hand here could only
    # ever disagree with that, so nothing on it (and nothing about it) is editable.
    list_display          = ['rider', 'show_amount', 'show_order_count', 'remitted_at', 'received_by']
    list_filter           = ['rider']
    list_select_related   = ['rider', 'received_by']
    search_fields         = ['rider__email', 'rider__username', 'received_by__email']
    date_hierarchy        = 'remitted_at'
    fields                = ['rider', 'amount', 'remitted_at', 'received_by', 'notes', 'show_orders']
    readonly_fields       = fields
    list_before_template  = 'admin/online_shop/remittance/overview.html'

    # This list is only ever a history of what's already been turned in —
    # "Record remittance" lives on the rider's own page, not here (see
    # has_add_permission below) — so without this, there'd be no way to tell
    # *which* rider's page to go to without opening each one to check.
    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), 'riders_outstanding': remittance.riders_with_outstanding_cash()}
        return super().changelist_view(request, extra_context=extra_context)

    def has_add_permission(self, request):
        return False                                 # only ever created via record_remittance()

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.display(description='Amount', ordering='amount')
    def show_amount(self, obj):
        return format_html('<span class="font-semibold">₱{}</span>', f'{obj.amount:,.2f}')

    @admin.display(description='Orders')
    def show_order_count(self, obj):
        return obj.orders.count()

    @admin.display(description='Orders covered')
    def show_orders(self, obj):
        orders = list(obj.orders.all())
        if not orders:
            return MUTED
        return format_html_join(
            mark_safe(', '), '<a class="an-link" href="{}">#CC-{}</a>',
            ((reverse('admin:online_shop_order_change', args=[o.pk]), str(o.pk).zfill(5)) for o in orders),
        )


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

def _busted_static(path):
    """
    Static URL with a `?v=<mtime>` query string appended, so the browser
    re-fetches it whenever the file actually changes on disk instead of
    serving a stale cached copy forever (bit us more than once while
    iterating on townzone-map.js — Django's dev static server sets no
    cache-busting on its own).
    """
    from django.contrib.staticfiles import finders
    from django.templatetags.static import static
    import os

    url   = static(path)
    found = finders.find(path)
    version = int(os.path.getmtime(found)) if found else 0
    return f'{url}?v={version}'


class TownZoneAdminForm(forms.ModelForm):
    class Meta:
        model = TownZone
        fields = '__all__'

    @property
    def media(self):
        from django.conf import settings
        from django.urls import reverse
        from urllib.parse import quote

        # townzone-map.js reads its own <script src> to pick up the MapTiler
        # key (via document.currentScript) — no key set yet is fine, it just
        # falls back to the key-free Esri tiles.
        map_js = _busted_static('js/townzone-map.js')
        if settings.MAPTILER_KEY:
            map_js += f'&maptiler_key={settings.MAPTILER_KEY}'
        # Only on the change form — an unsaved zone has no pk yet to auto-save
        # against, so on the add form the pin just fills the fields and the
        # admin still has to hit the normal Save button once.
        if self.instance.pk:
            save_url = reverse('htmx-townzone-center', args=[self.instance.pk])
            map_js += f'&save_url={quote(save_url)}'

        return forms.Media(
            css={'all': (_busted_static('vendor/leaflet/leaflet.css'),)},
            js=(_busted_static('vendor/leaflet/leaflet.js'), map_js),
        )


@admin.register(TownZone)
class TownZoneAdmin(ModelAdmin):
    form          = TownZoneAdminForm
    list_display  = ['name', 'delivery_fee', 'estimated_time', 'is_active']
    list_editable = ['delivery_fee', 'is_active']
    search_fields = ['name']
    fieldsets = (
        (None, {
            'fields': ('name', 'delivery_fee', 'estimated_time', 'is_active')
        }),
        ('Map Center (para sa auto-pan sa checkout)', {
            'fields': ('center_latitude', 'center_longitude'),
            'description': 'I-click ang mapa sa ibaba (o i-drag ang pin) para i-set ang center — awtomatikong mapupunan ang latitude/longitude. Pwede rin direktang i-type kung mayroon nang eksaktong coordinates.'
        }),
    )

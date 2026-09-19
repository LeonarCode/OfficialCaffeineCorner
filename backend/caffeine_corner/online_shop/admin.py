from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django import forms
from django.urls import reverse
from unfold.admin import ModelAdmin, TabularInline, format_html, mark_safe
from .models import ActivityLog, Category, Product, Variant, Rating, Order, OrderItem, LoyaltyPoint, Notification, TownZone
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


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_available', 'is_featured', 'is_seasonal', 'sort_order']
    list_filter = ['category', 'is_available', 'is_featured', 'is_seasonal']
    search_fields = ['name', 'sku']
    inlines = [VariantInline, IngredientInline]

    # Order lines store their own copy of the price (OrderItem.price), so this
    # is only a reassurance for staff — no code path re-prices old orders.
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'price':
            formfield.help_text = PRICE_CHANGE_NOTE
        return formfield


# System/other-flow/delivery-only fields — never relevant to a manually
# keyed-in order: the system ones are set by the payment gateway, the rider
# app, or the loyalty logic later on; the delivery ones don't apply because
# manually-added orders are always Dine-in (see OrderAdmin.save_model) — a
# staff member at the counter isn't taking someone's delivery address, zone,
# or a bulk/catering event date. Module-level (not a class attribute) since
# it's referenced from inside OrderAdmin.ADD_FIELDS's list comprehension,
# and comprehensions don't see their enclosing class body.
ORDER_ADD_EXCLUDED_FIELDS = {
    'paymongo_id', 'gcash_ref', 'assigned_rider',
    'delivery_proof_photo', 'delivered_at', 'rider_notes',
    'points_earned', 'points_used',
    'order_type', 'address', 'zone',
    'delivery_latitude', 'delivery_longitude', 'delivery_fee', 'event_date',
}


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_before_template = 'admin/order_change_list.html'
    list_display    = ['id', 'email', 'phone', 'order_type', 'show_status', 'payment_method', 'show_payment_status', 'total_price', 'created_at', 'show_map_link', 'print_receipt_link']  # ← dagdag show_map_link
    list_filter     = ['status', 'payment_method', 'payment_status', 'order_type']
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
    list_display = ['product', 'user', 'rating', 'created_at']
    list_filter = ['rating']
    search_fields = ['product__name', 'user__email']


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

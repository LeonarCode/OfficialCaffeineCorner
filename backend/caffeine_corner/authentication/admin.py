from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action
from unfold.enums import ActionVariant
from unfold.forms import BaseDialogForm

from caffeine_corner.mailer import peso
from online_shop import remittance
from online_shop.models import CartItem
from .models import User, OTPCode


class CartItemInline(TabularInline):
    model = CartItem
    extra = 0
    fields = ['product', 'variant', 'quantity']
    # 'variant' isn't here: it needs its own registered ModelAdmin to power
    # the autocomplete widget, but Variant is intentionally managed inline
    # only (via ProductAdmin), same as Ingredient/CartItem elsewhere. It
    # still renders fine as a plain FK dropdown.
    autocomplete_fields = ['product']


class RemittanceDialog(BaseDialogForm):
    """Shows the amount and which orders it covers, before it's turned into a Remittance record."""
    form_before_template = 'admin/authentication/user/remittance_dialog.html'

    def get_before_template_context(self, request, object_id=None):
        rider = User.objects.filter(pk=object_id, is_rider=True).first()
        if rider is None:
            return {}
        orders = list(remittance.outstanding_orders(rider))
        return {
            'rider': rider.get_full_name() or rider.email,
            'total': peso(remittance.outstanding_total(rider)),
            'orders': [f'#CC-{str(o.pk).zfill(5)}' for o in orders],
        }


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    list_display    = ['email', 'username', 'is_rider', 'show_rider_status', 'show_cash_to_remit', 'is_staff', 'date_joined']
    list_filter     = ['is_rider', 'rider_status', 'is_staff']
    search_fields   = ['email', 'username', 'phone']
    actions         = ['approve_riders', 'reject_riders']
    actions_detail  = ['record_remittance_detail']
    inlines         = [CartItemInline]
    readonly_fields = ['show_remittance_summary']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Rider Info', {'fields': ('is_rider', 'phone', 'rider_status', 'show_remittance_summary')}),
    )

    RIDER_STATUS_COLORS = {
        'pending':  ('#fff6e0', '#a06010'),
        'approved': ('#eaf5ed', '#2e7d4a'),
        'rejected': ('#fef0ee', '#c04a3a'),
    }

    def show_rider_status(self, obj):
        if not obj.is_rider:
            return mark_safe('<span style="color:#9ca3af;">—</span>')  # ← mark_safe instead of format_html
        bg, fg = self.RIDER_STATUS_COLORS.get(obj.rider_status, ('#f1efe8', '#5f5e5a'))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;border-radius:5px;font-size:11px;font-weight:500;">{}</span>',
            bg, fg, obj.get_rider_status_display()
        )
    show_rider_status.short_description = 'Rider Status'

    # ── remittance: the cash a rider is holding from Cash-on-Delivery deliveries ──
    @admin.display(description='Cash to remit')
    def show_cash_to_remit(self, obj):
        if not obj.is_rider:
            return mark_safe('<span style="color:#9ca3af;">—</span>')
        total = remittance.outstanding_total(obj)
        if not total:
            return mark_safe('<span style="color:#9ca3af;">—</span>')
        return format_html('<span style="color:#a06010;font-weight:600;">₱{}</span>', f'{total:,.2f}')

    @admin.display(description='')
    def show_remittance_summary(self, obj):
        if obj is None or not obj.is_rider:
            return mark_safe('<span style="color:#9ca3af;">Not a rider.</span>')
        orders = list(remittance.outstanding_orders(obj))
        if not orders:
            return mark_safe('<span style="color:#9ca3af;">Nothing outstanding right now.</span>')
        order_links = format_html_join(
            mark_safe(', '), '<a href="{}">#CC-{}</a>',
            ((reverse('admin:online_shop_order_change', args=[o.pk]), str(o.pk).zfill(5)) for o in orders),
        )
        return format_html(
            '<strong>{}</strong> from {} delivered order{} — {}',
            peso(remittance.outstanding_total(obj)), len(orders), '' if len(orders) == 1 else 's', order_links,
        )

    def has_record_remittance_permission(self, request, object_id=None):
        if not self.has_change_permission(request):
            return False
        if object_id is None:
            return True
        rider = User.objects.filter(pk=object_id, is_rider=True).first()
        return bool(rider) and remittance.outstanding_total(rider) > 0

    @staticmethod
    def _back_to(request, rider_pk):
        """Back to the rider's own page — from a confirmation dialog (an htmx request) that means telling htmx to load it."""
        url = reverse('admin:authentication_user_change', args=[rider_pk])
        if request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = url
            return response
        return redirect(url)

    @action(
        description=_('Record remittance'), permissions=['record_remittance'], icon='payments',
        variant=ActionVariant.PRIMARY, url_path='record-remittance',
        dialog={'title': _('Record this remittance?'), 'description': '', 'form_class': RemittanceDialog,
                'form_submit_text': _('Record remittance')},
    )
    def record_remittance_detail(self, request, form, object_id):
        rider = get_object_or_404(User, pk=object_id, is_rider=True)
        try:
            record = remittance.record_remittance(rider, request.user)
        except remittance.RemittanceError as error:
            self.message_user(request, str(error), messages.WARNING)
            return self._back_to(request, rider.pk)
        name = rider.get_full_name() or rider.email
        n = record.orders.count()
        self.message_user(
            request, f'{peso(record.amount)} recorded from {name} ({n} order{"" if n == 1 else "s"}).', messages.SUCCESS,
        )
        return self._back_to(request, rider.pk)

    @admin.action(description='✅ Approve selected riders')
    def approve_riders(self, request, queryset):
        updated = queryset.filter(is_rider=True).update(rider_status='approved', is_active=True)
        self.message_user(request, f'{updated} rider(s) approved.')

    @admin.action(description='❌ Reject selected riders')
    def reject_riders(self, request, queryset):
        updated = queryset.filter(is_rider=True).update(rider_status='rejected', is_active=False)
        self.message_user(request, f'{updated} rider(s) rejected.')


@admin.register(OTPCode)
class OTPCodeAdmin(ModelAdmin):
    list_display = ['email', 'code', 'is_used', 'created_at']
    search_fields = ['email']
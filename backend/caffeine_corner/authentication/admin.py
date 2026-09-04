from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from .models import User, OTPCode
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.decorators import action


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    list_display    = ['email', 'username', 'is_rider', 'show_rider_status', 'is_staff', 'date_joined']
    list_filter     = ['is_rider', 'rider_status', 'is_staff']
    search_fields   = ['email', 'username', 'phone']
    actions         = ['approve_riders', 'reject_riders']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Rider Info', {'fields': ('is_rider', 'phone', 'rider_status')}),
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
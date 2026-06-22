from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from .models import User, OTPCode


@admin.register(User)
class UserAdmin(ModelAdmin, BaseUserAdmin):
    list_display = ['email', 'is_staff', 'is_active']
    search_fields = ['email']
    ordering = ['email']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )


@admin.register(OTPCode)
class OTPCodeAdmin(ModelAdmin):
    list_display = ['email', 'code', 'is_used', 'created_at']
    search_fields = ['email']
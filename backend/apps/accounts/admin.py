from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Business, Membership, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "full_name", "is_staff", "is_active"]
    search_fields = ["email", "full_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "phone", "vat_registered", "created_at"]
    search_fields = ["name", "email", "tpin"]
    inlines = [MembershipInline]

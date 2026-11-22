from django.contrib import admin

from .models import Item


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ["name", "business", "unit_price", "is_active"]
    search_fields = ["name"]

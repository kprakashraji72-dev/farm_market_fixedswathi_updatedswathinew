from django.contrib import admin
from .models import Category, Product, FlowSession, Order


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "name"]
    search_fields = ["name", "id"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "category", "unit_rate", "unit_label"]
    list_filter = ["category"]
    search_fields = ["name", "id"]


@admin.register(FlowSession)
class FlowSessionAdmin(admin.ModelAdmin):
    list_display = [
        "flow_token",
        "customer_phone",
        "current_screen",
        "selected_product",
        "total_payable",
        "status",
        "updated_at",
    ]
    list_filter = ["status", "current_screen", "created_at"]
    search_fields = ["customer_phone", "full_name", "flow_token"]
    readonly_fields = ["flow_token", "created_at", "updated_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "customer_name",
        "product",
        "quantity",
        "total_payable",
        "status",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["customer_phone", "customer_name"]
    readonly_fields = ["created_at"]

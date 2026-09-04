from django.contrib import admin
from .models import Category, Farm, FarmImage, Product, ProductVariant


class FarmImageInline(admin.TabularInline):
    model = FarmImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'location', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'location')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [FarmImageInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'farm', 'category', 'price', 'stock_quantity', 'is_active')
    list_filter = ('is_active', 'category', 'farm')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductVariantInline]

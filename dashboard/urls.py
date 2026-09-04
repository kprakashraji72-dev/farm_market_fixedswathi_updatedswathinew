from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),

    path('users/', views.user_management, name='user_management'),
    path('users/<int:user_id>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    path('users/<int:user_id>/reset-password/', views.user_reset_password, name='user_reset_password'),

    # ---- Driver Management ----
    path('drivers/', views.driver_management, name='driver_management'),
    path('drivers/<int:user_id>/toggle-verified/', views.driver_toggle_verified, name='driver_toggle_verified'),

    # ---- Farmer Management ----
    path('farmers/', views.farmer_management, name='farmer_management'),

    # ---- Employee Management (in-store Employee accounts) ----
    path('employees/', views.employee_management, name='employee_management'),
    path('employees/<int:user_id>/permissions/', views.employee_permissions_update, name='employee_permissions_update'),
    path('staff/audit/', views.employee_audit, name='employee_audit'),
    path('staff/audit/<int:product_id>/report-damage/', views.employee_report_damage, name='employee_report_damage'),
    path('staff/damage-review/', views.damage_review, name='damage_review'),
    path('staff/damage-review/<int:damage_id>/approve/', views.damage_approve, name='damage_approve'),
    path('staff/damage-review/<int:damage_id>/reject/', views.damage_reject, name='damage_reject'),

    path('inventory/farms/', views.inventory_farms, name='inventory_farms'),
    path('inventory/farms/<int:farm_id>/delete/', views.farm_delete, name='farm_delete'),
    path('inventory/categories/', views.inventory_categories, name='inventory_categories'),
    path('inventory/categories/<int:category_id>/delete/', views.category_delete, name='category_delete'),
    path('inventory/products/', views.inventory_products, name='inventory_products'),
    path('inventory/products/<int:product_id>/edit/', views.product_edit, name='product_edit'),
    path('inventory/products/<int:product_id>/delete/', views.product_delete, name='product_delete'),
    path('inventory/products/<int:product_id>/toggle-active/', views.product_toggle_active, name='product_toggle_active'),
    path('inventory/products/<int:product_id>/toggle-approved/', views.product_toggle_approved, name='product_toggle_approved'),
    path('inventory/products/<int:product_id>/reject/', views.product_reject, name='product_reject'),
    path('inventory/products/<int:product_id>/reconsider/', views.product_reconsider, name='product_reconsider'),
    path('inventory/products/<int:product_id>/adjust-stock/', views.product_adjust_stock, name='product_adjust_stock'),
    path('inventory/products/<int:product_id>/variants/', views.product_variants, name='product_variants'),
    path('inventory/products/<int:product_id>/variants/<int:variant_id>/delete/', views.product_variant_delete, name='product_variant_delete'),
    path('inventory/products/<int:product_id>/variants/<int:variant_id>/toggle-active/', views.product_variant_toggle_active, name='product_variant_toggle_active'),
    path('inventory/products/<int:product_id>/variants/<int:variant_id>/adjust-stock/', views.product_variant_adjust_stock, name='product_variant_adjust_stock'),
    path('inventory/products/<int:product_id>/variants/<int:variant_id>/update-price/', views.product_variant_update_price, name='product_variant_update_price'),

    path('orders/', views.order_management, name='order_management'),
    path('orders/<int:order_id>/status/', views.order_update_status, name='order_update_status'),
    path('orders/<int:order_id>/assign-driver/', views.order_assign_driver, name='order_assign_driver'),
    path('orders/<int:order_id>/auto-assign-driver/', views.order_auto_assign_driver, name='order_auto_assign_driver'),

    path('tracking/', views.tracking_overview, name='tracking_overview'),
    path('tracking/rider-locations/', views.rider_locations_api, name='rider_locations_api'),
    path('reports/', views.reports_view, name='reports'),

    # ---- Farmer Partner Portal (self-service) ----
    path('farmer/', views.farmer_home, name='farmer_home'),
    path('farmer/farm/', views.farmer_farm_profile, name='farmer_farm_profile'),
    path('farmer/products/', views.farmer_products, name='farmer_products'),
    path('farmer/products/<int:product_id>/toggle-active/', views.farmer_product_toggle_active, name='farmer_product_toggle_active'),
    path('farmer/products/<int:product_id>/delete/', views.farmer_product_delete, name='farmer_product_delete'),
    path('farmer/products/<int:product_id>/restore/', views.farmer_product_restore, name='farmer_product_restore'),
    path('farmer/report/', views.farmer_report, name='farmer_report'),

    # ---- WhatsApp Follow-Ups & Outreach ----
    path('whatsapp-followups/', views.whatsapp_followups_view, name='whatsapp_followups'),
    path('whatsapp-followups/<int:followup_id>/send-now/', views.whatsapp_followup_send_now, name='whatsapp_followup_send_now'),
]
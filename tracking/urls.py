from django.urls import path
from . import views

app_name = 'tracking'

urlpatterns = [
    path('driver/', views.driver_dashboard, name='driver_dashboard'),
    path('driver/delivery/<int:order_id>/', views.driver_delivery_page, name='driver_delivery_page'),
    path('driver/update-location/', views.update_location, name='update_location'),
    path('driver/order/<int:order_id>/accept/', views.driver_pick_order, name='driver_accept_order'),
    path('driver/order/<int:order_id>/start/', views.driver_start_delivery, name='driver_start_delivery'),
    path('driver/order/<int:order_id>/pick/', views.driver_pick_order, name='driver_pick_order'),
    path('driver/order/<int:order_id>/reject/', views.driver_reject_order, name='driver_reject_order'),
    path('driver/order/<int:order_id>/arrived/', views.driver_confirm_arrival, name='driver_confirm_arrival'),
    path('driver/order/<int:order_id>/complete/', views.driver_complete_order, name='driver_complete_order'),
    path('order/<int:order_id>/location/', views.order_location_api, name='order_location_api'),
    path('order/<int:order_id>/update-customer-location/', views.update_customer_location, name='update_customer_location'),
]

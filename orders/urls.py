from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('cart/', views.cart_detail_view, name='cart_detail'),
    path('cart/add/', views.add_to_cart, name='add_to_cart_variant'),
    path('cart/add-ajax/', views.add_to_cart, name='add_to_cart_ajax'),
    path('cart/add/<int:product_id>/', views.add_to_cart_ajax, name='add_to_cart'),
    path('cart/update/<str:item_key>/', views.update_quantity_ajax, name='update_quantity'),

    path('cart/remove/<str:item_key>/', views.remove_from_cart_ajax, name='remove_from_cart'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('my-orders/', views.my_orders_view, name='my_orders'),
    path('order/<int:order_id>/', views.order_detail_view, name='order_detail'),
    path('order/<int:order_id>/cancel/', views.cancel_order_view, name='cancel_order'),
    path('track/', views.track_lookup_view, name='track_lookup'),
    path('track/<int:order_id>/', views.track_guest_view, name='track_guest'),
    path('track/order/<int:order_id>/', views.track_guest_view, name='track_order'),
]

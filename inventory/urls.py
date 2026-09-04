from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('products/', views.product_list_view, name='product_list'),
    path('products/<slug:slug>/', views.product_detail_view, name='product_detail'),
    path('farms/<slug:slug>/', views.farm_detail_view, name='farm_detail'),
]

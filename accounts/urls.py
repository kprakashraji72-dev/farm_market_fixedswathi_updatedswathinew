from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),

    path('driver/login/', views.driver_login_view, name='driver_login'),
    path('driver/register/', views.driver_register_view, name='driver_register'),
    path('driver/documents/', views.driver_documents_view, name='driver_documents'),

    path('farmer/login/', views.farmer_login_view, name='farmer_login'),
    path('farmer/register/', views.farmer_register_view, name='farmer_register'),
    path('farmer/documents/', views.farmer_documents_view, name='farmer_documents'),

    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
]

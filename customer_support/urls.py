from django.urls import path
from . import views

app_name = 'customer_support'

urlpatterns = [
    path('login/', views.support_staff_login, name='login'),
    path('logout/', views.support_staff_logout, name='logout'),
    path('manage-staff/', views.manage_staff, name='manage_staff'),
    path('manage-staff/<int:user_id>/toggle-status/', views.toggle_staff_status, name='toggle_staff_status'),
    path('', views.support_console, name='console'),
    path('tickets/<int:pk>/', views.ticket_detail, name='detail'),
    path('tickets/<int:pk>/upload/', views.upload_ticket_attachment, name='upload_attachment'),
    path('tickets/<int:pk>/reassign/', views.reassign_ticket, name='reassign'),
    path('reports/', views.reports, name='reports'),
]

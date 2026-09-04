from django.urls import path
from . import views

app_name = 'support'

urlpatterns = [
    path('', views.customer_create, name='create'),
    path('tickets/', views.customer_my_tickets, name='my_tickets'),
    path('tickets/<int:pk>/', views.customer_ticket_detail, name='detail'),
    path('tickets/<int:pk>/upload/', views.upload_ticket_attachment, name='upload_attachment'),
]


from django.urls import path
from . import views

app_name = 'store'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('portals/', views.portals_view, name='portals'),
    path('chat/message/', views.chat_message_view, name='chat_message'),
    path('chat/reset/', views.chat_reset_view, name='chat_reset'),
    path('chat/clear/', views.chat_reset_view, name='chat_clear'),
]

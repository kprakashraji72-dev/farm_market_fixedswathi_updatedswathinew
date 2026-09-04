"""
wa_flow/urls.py
───────────────
URL routing for WhatsApp Flow and Webhook endpoints.
"""

from django.urls import path
from . import views

app_name = "wa_flow"

urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
    path("flow-endpoint/", views.flow_endpoint, name="flow_endpoint"),
]

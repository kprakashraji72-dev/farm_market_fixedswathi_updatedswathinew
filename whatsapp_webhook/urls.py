from django.urls import path
from django.shortcuts import render
from . import views
from .flow_views import whatsapp_flow_endpoint


def flow_order_page(request):
    """Public page embedding the WhatsApp Flow as an iframe."""
    return render(request, "store/flow_order.html")

urlpatterns = [
    # ── 1. CANONICAL REQUIRED ENDPOINTS (Audited Meta Flow Lifecycle) ────────
    path("api/whatsapp/webhook/",      views.whatsapp_webhook,         name="api_whatsapp_webhook"),  # GET (verify) & POST (events)
    path("api/whatsapp/flow/",         whatsapp_flow_endpoint,         name="api_flow_endpoint"),     # POST (Encrypted Flow Data Endpoint)
    path("api/whatsapp/create-flow/",  views.api_create_flow,          name="api_create_flow"),       # POST (Calls Meta /{WABA_ID}/flows)
    path("api/whatsapp/publish-flow/", views.api_publish_flow,         name="api_publish_flow"),      # POST (Calls Meta /{FLOW_ID}/publish)
    path("api/whatsapp/send-flow/",    views.api_send_flow,            name="api_send_flow"),         # POST (Dispatches Flow via Cloud API)

    # ── 2. Backward compatibility & Web Preview Aliases ─────────────────────
    path("webhook/whatsapp/",          views.whatsapp_webhook,         name="whatsapp_webhook"),
    path("whatsapp/webhook/",          views.whatsapp_webhook,         name="whatsapp_webhook_alt"),
    path("whatsapp/flow/",             whatsapp_flow_endpoint,         name="whatsapp_flow"),
    path("order/",                     flow_order_page,                name="flow_order_page"),
    path("whatsapp/replies/latest/",   views.latest_replies_api,       name="whatsapp_latest_replies"),
    path("whatsapp/simulate/",         views.simulate_whatsapp_message, name="whatsapp_simulate"),
    path("whatsapp/debug/",            views.webhook_debug_status,      name="whatsapp_debug"),
]

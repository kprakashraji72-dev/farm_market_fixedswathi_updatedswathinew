from django.urls import path
from .views import MessagesWebhookView, FlowDataExchangeView, FlowHealthCheckView

urlpatterns = [
    path("webhook/messages/", MessagesWebhookView.as_view(), name="webhook_messages"),
    path("webhook/flow-data-exchange/", FlowDataExchangeView.as_view(), name="webhook_flow_data_exchange"),
    path("webhook/flow-data-exchange/health/", FlowHealthCheckView.as_view(), name="webhook_flow_data_exchange_health"),
]


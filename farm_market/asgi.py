"""
ASGI config for fresh_trace / farm_market project.

It exposes the ASGI callable as a module-level variable named ``application``.
Supports both standard HTTP requests and WebSockets via Django Channels.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'farm_market.settings')
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
import customer_support.routing

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                customer_support.routing.websocket_urlpatterns
            )
        )
    ),
})

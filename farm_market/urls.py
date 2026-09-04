"""
Root URL configuration for Fresh Trace.
Each app owns its own urls.py; this file just includes them under
sensible prefixes so the project stays modular as we add apps
module-by-module (accounts -> inventory -> orders -> tracking -> dashboard).
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from orders import views as orders_views

urlpatterns = [
    path('django-admin/', admin.site.urls),  # Django's built-in admin (kept separate from our custom dashboard)

    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('dashboard/', include('dashboard.urls', namespace='dashboard')),
    path('tracking/', include('tracking.urls', namespace='tracking')),
    path('orders/', include('orders.urls', namespace='orders')),
    path('cart/add/', orders_views.add_to_cart, name='cart_add_root'),
    path('support/', include('customer_support.customer_urls', namespace='support')),


    path('support-console/', include('customer_support.urls', namespace='customer_support')),
    path('', include('inventory.urls', namespace='inventory')),

    path('', include('store.urls', namespace='store')),  # customer-facing site at root
    path("", include("whatsapp_webhook.urls")),
    path("", include("wa_flow.urls", namespace="wa_flow")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])

handler404 = 'store.views.error_404'
handler500 = 'store.views.error_500'

# Fresh Trace — Farm Market & Live Order Tracking System

A full Django 5 (works on 6 too) project: farm-to-table e-commerce with
live GPS delivery tracking, built with plain Django MVT + Bootstrap 5 +
vanilla JS (fetch API) + Leaflet/OpenStreetMap. No frontend framework
required.

## Feature Summary

| Area | What's implemented |
|---|---|
| **Accounts** | Custom `User` model with roles (admin/customer/driver/farmer), registration, shared login with role-based redirect, separate verified-only driver login, profile view/edit, logout |
| **Inventory** | Category, Farm (+ gallery + video URL), Product — product grid with search/category filter/pagination, product detail, farm detail page |
| **Orders** | Session-based cart, AJAX add-to-cart, AJAX +/- quantity (no page refresh), checkout, Order/OrderItem models, My Orders |
| **Tracking** | `DriverLocation` model, browser Geolocation API auto-push (no manual lat/lng), Leaflet + OpenStreetMap live map on the customer's track-order page (polls every 5s), admin overview map of all active drivers |
| **Dashboard** | User Management (activate/deactivate), Role Management (change role + verify drivers), Inventory (Farms/Products CRUD-lite), Order Management (status + driver assignment), Tracking overview, Reports (revenue, orders by status, top products) |

## Getting Started

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # edit SECRET_KEY, DEBUG, etc.

python manage.py makemigrations
python manage.py migrate

# Optional: quick demo data (admin/admin12345, driver1/driver12345, customer1/customer12345)
python manage.py seed_demo_data

# Or create your own admin:
python manage.py createsuperuser
# then set role='admin' for that user via /django-admin/

python manage.py runserver
```

Visit:
- `/` — customer storefront
- `/accounts/login/` — customer/admin login
- `/accounts/driver/login/` — driver-only login
- `/dashboard/` — admin dashboard (role=admin required)
- `/tracking/driver/` — driver dashboard (role=driver, is_verified required)
- `/django-admin/` — Django's built-in admin (manage everything directly)

## How Live Tracking Works

1. Admin assigns a **verified** driver to an order in Dashboard → Orders,
   and sets status to Confirmed/Out for Delivery.
2. The driver logs in at `/accounts/driver/login/` and lands on their
   dashboard, which immediately requests browser location permission via
   `navigator.geolocation.watchPosition()`.
3. Every position update is POSTed to `/tracking/driver/update-location/`
   as JSON — no manual coordinate entry anywhere.
4. The customer opens **My Orders → Track Order**, which renders a
   Leaflet/OpenStreetMap map and polls `/tracking/order/<id>/location/`
   every 5 seconds to move the driver's marker and update status/ETA.

## Production Notes

- Switch `DB_ENGINE=postgres` in `.env` and set `DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT`.
- Set `DEBUG=False` and a real `SECRET_KEY` + `ALLOWED_HOSTS` before deploying.
- Run `collectstatic` and serve `STATIC_ROOT`/`MEDIA_ROOT` via your web server or a storage backend (e.g. S3) in production — Django's dev static serving is DEBUG-only.
- This sandbox had no network access, so the code was syntax-checked
  file-by-file but not run against a live Django server — run
  `migrate` + `runserver` as your first smoke test locally.

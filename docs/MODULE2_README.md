# Module 2 — Accounts (Authentication & Roles)

## What's implemented
- Custom `User` model (`accounts.User`) extending `AbstractUser` with a `role`
  field (`admin`, `customer`, `driver`, `farmer`), phone, address, profile
  photo, and `is_verified` (used to gate driver accounts).
- `AUTH_USER_MODEL = 'accounts.User'` wired in settings.
- **Registration** (`/accounts/register/`) — public signup, always creates a
  `customer` role account. Admin/driver accounts are provisioned later via
  the dashboard's User Management (not self-service).
- **Login** (`/accounts/login/`) — shared for customer/admin/farmer.
  Redirects by role via `User.get_dashboard_url_name()`:
  admin → dashboard, customer/farmer → store, and rejects drivers with a
  message pointing them to the driver login page.
- **Driver Login** (`/accounts/driver/login/`) — separate page/form. Enforces
  `role == driver` AND `is_verified == True` before allowing login, then
  redirects to `tracking:driver_dashboard`.
- **Profile** (`/accounts/profile/`, `/accounts/profile/edit/`) — view and
  edit for any logged-in role.
- **Logout** (`/accounts/logout/`, POST only, in navbar dropdown) — drivers
  land back on the driver login page, everyone else lands on store home.
- `accounts/decorators.py` — `role_required`, `admin_required`,
  `driver_required`, `customer_required` — reused by dashboard/tracking apps.
- Base templates (`base.html`, `navbar.html`, `footer.html`, `sidebar.html`)
  with Bootstrap 5, role-aware navbar (driver login link, admin/driver
  dashboard links, cart badge placeholder for customers).

## Next steps to run it
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit SECRET_KEY etc.
python manage.py makemigrations accounts
python manage.py migrate
python manage.py createsuperuser   # set role=admin afterward via /django-admin/
python manage.py runserver
```

## Not yet built (later modules)
Inventory (Farm/Product/Category), Orders (Cart/Checkout), Tracking (GPS +
Leaflet map), Dashboard widgets/Reports, Farm detail pages. Current
placeholder views/templates exist only so Module 2's redirects have
somewhere valid to land.

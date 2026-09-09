"""
Admin Dashboard views. All gated with @admin_required (accounts.decorators),
so only role == 'admin' users can reach any of these.
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import Greatest
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required, role_required, dashboard_access_required
from accounts.models import User, DriverKYC, FarmerKYC, EmployeePermission
from accounts.forms import EmployeeCreateForm, DriverRegistrationForm, FarmerRegistrationForm
from accounts.notifications import send_partner_verification_email, send_password_reset_email
from inventory.models import Farm, Product, Category, ProductVariant, ProductDamage
from inventory.forms import (
    FarmForm, ProductForm, CategoryForm, ProductVariantForm,
    FarmerFarmProfileForm, FarmerProductForm,
)
from orders.models import Order, OrderItem
from orders.services import find_best_driver, assign_driver
from tracking.models import DriverLocation


@role_required('admin', 'employee')
def dashboard_home(request):
    """Landing page for admins AND employees: quick-glance KPI widgets.
    Employees see the same numbers (nothing sensitive) but their sidebar
    (templates/sidebar.html) only links to sections they've been granted."""
    import json
    from datetime import timedelta
    from django.utils import timezone
    from django.db.models.functions import TruncMonth

    now = timezone.now()
    soon = now.date() + timedelta(days=30)

    # 1. Real Products Data for Charts
    products_qs = Product.objects.select_related('category', 'farm').all().order_by('-stock_quantity')
    product_names = [p.name.title() for p in products_qs]
    product_stocks = [p.stock_quantity for p in products_qs]
    product_units = [p.get_unit_display() if hasattr(p, 'get_unit_display') else p.unit for p in products_qs]
    product_values = [float(p.stock_quantity * p.price) for p in products_qs]
    product_prices = [float(p.price) for p in products_qs]

    # 2. Real Category Distribution for Circle / Donut Chart
    palette = ['#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#6f42c1', '#fd7e14', '#20c997']
    categories_qs = Category.objects.annotate(count=Count('products')).filter(count__gt=0).order_by('-count')
    
    category_legend_items = []
    if categories_qs.exists():
        total_cat_prods = sum(c.count for c in categories_qs) or 1
        category_labels = [c.name.title() for c in categories_qs]
        category_counts = [c.count for c in categories_qs]
        for idx, c in enumerate(categories_qs):
            pct = round((c.count / total_cat_prods) * 100, 1)
            color = palette[idx % len(palette)]
            category_legend_items.append({
                'name': c.name.title(),
                'count': c.count,
                'percentage': pct,
                'color': color,
            })
    else:
        category_labels = [p.name.title() for p in products_qs] or ["General Produce"]
        category_counts = [p.stock_quantity for p in products_qs] or [1]
        total_stock = sum(category_counts) or 1
        for idx, p in enumerate(products_qs):
            pct = round((p.stock_quantity / total_stock) * 100, 1) if total_stock else 0
            color = palette[idx % len(palette)]
            category_legend_items.append({
                'name': p.name.title(),
                'count': p.stock_quantity,
                'percentage': pct,
                'color': color,
            })

    # 3. Monthly Real Order Sales
    monthly_sales = [0.0] * 12
    orders_by_month = (
        Order.objects.filter(
            created_at__year=now.year,
            status__in=[Order.Status.CONFIRMED, Order.Status.OUT_FOR_DELIVERY, Order.Status.DELIVERED]
        )
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('total_amount'))
        .order_by('month')
    )
    for entry in orders_by_month:
        if entry.get('month'):
            m = entry['month'].month - 1
            monthly_sales[m] = float(entry['total'] or 0.0)

    total_inventory_value = sum(product_values)

    context = {
        'total_orders': Order.objects.count(),
        'pending_orders': Order.objects.filter(status=Order.Status.PENDING).count(),
        'out_for_delivery': Order.objects.filter(status=Order.Status.OUT_FOR_DELIVERY).count(),
        'total_revenue': Order.objects.exclude(status=Order.Status.CANCELLED).aggregate(
            total=Sum('total_amount'))['total'] or 0,
        'total_customers': User.objects.filter(role=User.Role.CUSTOMER).count(),
        'total_drivers': User.objects.filter(role=User.Role.DRIVER).count(),
        'total_products': Product.objects.count(),
        'total_inventory_value': total_inventory_value,
        'our_products': products_qs[:10],
        'recent_orders': Order.objects.select_related('customer')[:8],

        # JSON data for Chart.js
        'product_names_json': json.dumps(product_names),
        'product_stocks_json': json.dumps(product_stocks),
        'product_units_json': json.dumps(product_units),
        'product_values_json': json.dumps(product_values),
        'product_prices_json': json.dumps(product_prices),
        'category_labels_json': json.dumps(category_labels),
        'category_counts_json': json.dumps(category_counts),
        'category_legend_items': category_legend_items,
        'monthly_sales_json': json.dumps(monthly_sales),

        # Compliance widgets: partners whose docs need admin attention soon.
        'pending_driver_verifications': User.objects.filter(role=User.Role.DRIVER, is_verified=False).count(),
        'pending_farmer_verifications': User.objects.filter(role=User.Role.FARMER, is_verified=False).count(),
        'pending_product_approvals': Product.objects.filter(is_approved=False).count(),
        'pending_damage_reviews': ProductDamage.objects.filter(status=ProductDamage.Status.PENDING).count(),
        'drivers_renewal_due_soon': DriverKYC.objects.filter(
            renewal_due_date__isnull=False, renewal_due_date__lte=soon
        ).select_related('user')[:10],
        'farmers_cert_expiring_soon': FarmerKYC.objects.filter(
            iso_expiry_date__isnull=False, iso_expiry_date__lte=soon
        ).select_related('user')[:10],
    }
    return render(request, 'dashboard/dashboard.html', context)


# ---------- User Management ----------
@admin_required
def user_management(request):
    users = User.objects.exclude(id=request.user.id).order_by('-date_joined')

    role_filter = request.GET.get('role')
    if role_filter:
        users = users.filter(role=role_filter)

    page_obj = Paginator(users, 20).get_page(request.GET.get('page'))
    return render(request, 'dashboard/users.html', {
        'page_obj': page_obj,
        'roles': User.Role.choices,
        'role_filter': role_filter,
    })


@admin_required
@require_POST
def user_toggle_active(request, user_id):
    """Activate/deactivate a user account (block login without deleting data)."""
    user = get_object_or_404(User, id=user_id)
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    messages.success(request, f'{user.username} is now {"active" if user.is_active else "deactivated"}.')
    return redirect('dashboard:user_management')


@admin_required
@require_POST
def user_reset_password(request, user_id):
    """
    Admin-triggered password reset for any user who's forgotten their
    password (drivers, farmers, employees, customers). There's no
    self-service 'forgot password' flow in this app, so this is how an
    admin recovers access: generates a random temporary password, sets
    it on the account, emails it to the user if they have an email on
    file (best-effort — never blocks on a broken mail server, see
    accounts.notifications.send_password_reset_email), and also shows
    it on-screen so the admin can relay it directly if needed.
    """
    user = get_object_or_404(User, id=user_id)
    new_password = get_random_string(10)
    user.set_password(new_password)
    user.save(update_fields=['password'])
    send_password_reset_email(user, new_password)
    messages.success(
        request,
        f"Password reset for {user.username}. New temporary password: {new_password} "
        f"— share this with them securely; they should change it after logging in."
    )
    return redirect('dashboard:user_management')


# ---------- Driver Management ----------
@admin_required
def driver_management(request):
    """
    Dedicated page for delivery-partner accounts: search, review KYC
    documents, verify/unverify, and add a driver directly from the
    admin side (reuses the same DriverRegistrationForm as the public
    self-registration page).
    """
    query = request.GET.get('q', '').strip()
    drivers = User.objects.filter(role=User.Role.DRIVER).select_related('driver_kyc').order_by('username')
    if query:
        drivers = drivers.filter(
            Q(username__icontains=query) | Q(email__icontains=query) |
            Q(phone_number__icontains=query) | Q(driver_kyc__license_number__icontains=query) |
            Q(driver_kyc__vehicle_number__icontains=query)
        )

    if request.method == 'POST':
        form = DriverRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            new_driver = form.save()
            messages.success(request, f'Driver "{new_driver.username}" added. Verify their documents below when ready.')
            return redirect('dashboard:driver_management')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DriverRegistrationForm()

    return render(request, 'dashboard/drivers.html', {
        'drivers': drivers,
        'drivers_verified_count': drivers.filter(is_verified=True).count(),
        'query': query,
        'form': form,
    })


@admin_required
@require_POST
def driver_toggle_verified(request, user_id):
    """
    Toggles is_verified for a driver OR a farmer (both roles submit KYC
    documents and both are gated by this same flag — drivers can't log
    in at /accounts/driver/login/ and farmers can't log in at
    /accounts/farmer/login/ until an admin flips this on).
    """
    partner = get_object_or_404(User, id=user_id, role__in=[User.Role.DRIVER, User.Role.FARMER])
    partner.is_verified = not partner.is_verified
    partner.save(update_fields=['is_verified'])
    send_partner_verification_email(partner, partner.is_verified)
    messages.success(request, f'{partner.username} is now {"verified" if partner.is_verified else "unverified"}.')
    redirect_name = 'dashboard:driver_management' if partner.role == User.Role.DRIVER else 'dashboard:farmer_management'
    return redirect(redirect_name)


# ---------- Farmer Management ----------
@admin_required
def farmer_management(request):
    """
    Dedicated page for farm/seller-partner accounts: search, review the
    ISO/food-safety certificate, verify/unverify, and add a farmer
    directly from the admin side (reuses FarmerRegistrationForm).
    """
    query = request.GET.get('q', '').strip()
    farmers = User.objects.filter(role=User.Role.FARMER).select_related('farmer_kyc').order_by('username')
    if query:
        farmers = farmers.filter(
            Q(username__icontains=query) | Q(email__icontains=query) |
            Q(phone_number__icontains=query) | Q(farmer_kyc__iso_certificate_number__icontains=query)
        )

    if request.method == 'POST':
        form = FarmerRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            new_farmer = form.save()
            messages.success(request, f'Farmer "{new_farmer.username}" added. Verify their certificate below when ready.')
            return redirect('dashboard:farmer_management')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = FarmerRegistrationForm()

    return render(request, 'dashboard/farmers.html', {
        'farmers': farmers,
        'query': query,
        'form': form,
    })


# ---------- Employee Management ----------
@admin_required
def employee_management(request):
    """
    Dedicated page for in-store staff accounts: search, add a new
    employee (username/password), and grant/update which dashboard
    sections each employee can access (accounts.models.EmployeePermission).
    """
    query = request.GET.get('q', '').strip()
    employees = User.objects.filter(role=User.Role.EMPLOYEE).select_related('employee_permission').order_by('username')
    if query:
        employees = employees.filter(
            Q(username__icontains=query) | Q(email__icontains=query) | Q(phone_number__icontains=query)
        )

    if request.method == 'POST':
        form = EmployeeCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            EmployeePermission.objects.create(
                user=user,
                can_manage_orders=request.POST.get('can_manage_orders') == 'on',
                can_manage_inventory=request.POST.get('can_manage_inventory') == 'on',
                can_view_reports=request.POST.get('can_view_reports') == 'on',
                can_report_damage=request.POST.get('can_report_damage') == 'on',
            )
            messages.success(request, f'Employee account "{user.username}" created.')
            return redirect('dashboard:employee_management')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = EmployeeCreateForm()

    return render(request, 'dashboard/employees.html', {
        'employees': employees,
        'query': query,
        'form': form,
    })


@admin_required
@require_POST
def employee_permissions_update(request, user_id):
    """Admin sets which dashboard areas an EMPLOYEE-role user can access."""
    user = get_object_or_404(User, id=user_id, role=User.Role.EMPLOYEE)
    profile, _ = EmployeePermission.objects.get_or_create(user=user)
    profile.can_manage_orders = request.POST.get('can_manage_orders') == 'on'
    profile.can_manage_inventory = request.POST.get('can_manage_inventory') == 'on'
    profile.can_view_reports = request.POST.get('can_view_reports') == 'on'
    profile.can_report_damage = request.POST.get('can_report_damage') == 'on'
    profile.save()
    messages.success(request, f"Updated access for {user.username}.")
    return redirect('dashboard:employee_management')


@dashboard_access_required('can_report_damage')
def employee_audit(request):
    """
    Employee-facing product audit page: every active product across all
    farms, with a "Report damage" form per row. Filing a report here
    does NOT touch stock — it's queued as Pending until an admin reviews
    it on the Damage Review page (see employee_report_damage / damage_review).
    """
    products = Product.objects.select_related('farm', 'category').filter(is_active=True)
    my_reports = ProductDamage.objects.filter(reported_by=request.user).select_related('product')[:20]
    return render(request, 'dashboard/employee_audit.html', {
        'products': products,
        'my_reports': my_reports,
    })


@dashboard_access_required('can_report_damage')
@require_POST
def employee_report_damage(request, product_id):
    """Employee logs a damage report; stock is left untouched until admin approval."""
    product = get_object_or_404(Product, id=product_id)
    try:
        quantity = int(request.POST.get('quantity', 0))
    except (TypeError, ValueError):
        quantity = 0
    note = request.POST.get('note', '').strip()

    if quantity <= 0:
        messages.error(request, 'Enter a positive quantity to report as damaged.')
        return redirect('dashboard:employee_audit')

    ProductDamage.objects.create(
        product=product, quantity=quantity, note=note,
        reported_by=request.user, status=ProductDamage.Status.PENDING,
    )
    messages.success(request, f'Reported {quantity} {product.unit} of {product.name} as damaged — pending admin review.')
    return redirect('dashboard:employee_audit')


@dashboard_access_required('can_manage_inventory')
def damage_review(request):
    """Admin/authorised-employee queue of Pending employee damage reports."""
    reports = ProductDamage.objects.filter(
        status=ProductDamage.Status.PENDING
    ).select_related('product', 'reported_by').order_by('-reported_at')
    return render(request, 'dashboard/damage_review.html', {'reports': reports})


@dashboard_access_required('can_manage_inventory')
@require_POST
def damage_approve(request, damage_id):
    """Approve a pending damage report: deducts stock now and marks it reviewed."""
    report = get_object_or_404(ProductDamage, id=damage_id, status=ProductDamage.Status.PENDING)
    Product.objects.filter(pk=report.product_id).update(
        stock_quantity=Greatest(F('stock_quantity') - report.quantity, 0)
    )
    report.status = ProductDamage.Status.APPROVED
    report.reviewed_by = request.user if request.user.is_admin_role else None
    report.reviewed_at = timezone.now()
    report.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
    messages.success(request, f'Approved: {report.quantity} {report.product.unit} of {report.product.name} deducted from stock.')
    return redirect('dashboard:damage_review')


@dashboard_access_required('can_manage_inventory')
@require_POST
def damage_reject(request, damage_id):
    """Reject a pending damage report: no stock change."""
    report = get_object_or_404(ProductDamage, id=damage_id, status=ProductDamage.Status.PENDING)
    report.status = ProductDamage.Status.REJECTED
    report.reviewed_by = request.user if request.user.is_admin_role else None
    report.reviewed_at = timezone.now()
    report.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
    messages.info(request, f'Rejected damage report for {report.product.name}.')
    return redirect('dashboard:damage_review')


# ---------- Inventory Management (Farms & Products) ----------
@admin_required
def inventory_farms(request):
    farms = Farm.objects.all()
    if request.method == 'POST':
        form = FarmForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Farm added.')
            return redirect('dashboard:inventory_farms')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = FarmForm()
    return render(request, 'dashboard/farms.html', {
        'farms': farms,
        'farms_active_count': farms.filter(is_active=True).count(),
        'form': form,
    })


@dashboard_access_required('can_manage_inventory')
def inventory_categories(request):
    """
    Categories (Fruits, Vegetables, Leafy Greens, etc.) have to exist here
    before they'll show up in the Product form's Category dropdown.
    """
    categories = Category.objects.all()
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category added.')
            return redirect('dashboard:inventory_categories')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = CategoryForm()
    return render(request, 'dashboard/categories.html', {'categories': categories, 'form': form})


@dashboard_access_required('can_manage_inventory')
@require_POST
def category_delete(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category.delete()
    messages.success(request, 'Category removed.')
    return redirect('dashboard:inventory_categories')


@admin_required
@require_POST
def farm_delete(request, farm_id):
    farm = get_object_or_404(Farm, id=farm_id)
    farm.delete()
    messages.success(request, 'Farm removed.')
    return redirect('dashboard:inventory_farms')


@dashboard_access_required('can_manage_inventory')
def inventory_products(request):
    """Admin/employee product catalogue — also where farmer-added products
    show up as 'Pending approval' for review (see pending_count below)."""
    products = Product.objects.select_related('farm', 'category')
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            # Products added directly here (by an admin/authorised employee)
            # are trusted and go live immediately — no approval queue.
            product = form.save(commit=False)
            product.is_approved = True
            product.approved_at = timezone.now()
            product.approved_by = request.user if request.user.is_admin_role else None
            if not product.received_date:
                product.received_date = timezone.now().date()
            if not product.harvest_date:
                product.harvest_date = product.received_date
            product.save()
            messages.success(request, 'Product added.')
            return redirect('dashboard:inventory_products')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductForm()
    return render(request, 'dashboard/products.html', {
        'products': products,
        'form': form,
        'farms': Farm.objects.all(),
        'categories': Category.objects.all(),
        'unit_choices': Product.UNIT_CHOICES,
        # Rejected products (rejected_at set) are no longer "pending" — they've
        # already been reviewed and declined, so they don't count here.
        'pending_count': products.filter(is_approved=False, rejected_at__isnull=True).count(),
    })


@dashboard_access_required('can_manage_inventory')
def product_edit(request, product_id):
    """Admin / staff view to edit and reassign a product's origin farm, category, unit, price, and stock."""
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f'{product.name} reassigned & updated successfully.')
            return redirect('dashboard:inventory_products')
        messages.error(request, 'Please correct the errors in the product edit form.')
    else:
        form = ProductForm(instance=product)

    products = Product.objects.select_related('farm', 'category')
    return render(request, 'dashboard/products.html', {
        'products': products,
        'form': form,
        'edit_product': product,
        'farms': Farm.objects.all(),
        'categories': Category.objects.all(),
        'unit_choices': Product.UNIT_CHOICES,
        'pending_count': products.filter(is_approved=False, rejected_at__isnull=True).count(),
    })


@dashboard_access_required('can_manage_inventory')
@require_POST
def product_toggle_approved(request, product_id):
    """
    Approve (or revoke approval of) a product. Farmer-added products start
    is_approved=False and stay invisible to customers (see
    inventory.models.LIVE_APPROVED_PRODUCT_Q) until this is flipped on.

    Approving (False -> True) requires a `price` in the POST body: the
    farmer only quotes their cost (often a bulk/wholesale lot price, e.g.
    "1 for 22 pieces" — see Product.cost_price/bulk_quantity), so the admin
    sets the actual customer-facing per-unit price here before it can go
    live. Un-approving (True -> False) needs no price.
    """
    product = get_object_or_404(Product, id=product_id)
    now_approving = not product.is_approved

    if now_approving:
        price_raw = request.POST.get('price', '').strip()
        try:
            price = Decimal(price_raw)
        except (InvalidOperation, ValueError):
            price = None
        if not price_raw or price is None or price <= 0:
            messages.error(request, f'Enter a valid store price for {product.name} before approving it.')
            return redirect('dashboard:inventory_products')
        product.price = price
        product.is_approved = True
        product.approved_at = timezone.now()
        product.approved_by = request.user if request.user.is_admin_role else None
        # Approving always clears any earlier rejection, so a reconsidered
        # product doesn't keep showing a stale "Rejected" reason.
        product.rejected_at = None
        product.rejection_reason = ''
        product.save(update_fields=[
            'price', 'is_approved', 'approved_at', 'approved_by',
            'rejected_at', 'rejection_reason',
        ])
        messages.success(request, f'{product.name} approved and live at ₹{price}/{product.get_unit_display()}.')
    else:
        product.is_approved = False
        product.save(update_fields=['is_approved'])
        messages.success(request, f'{product.name} is now unapproved (hidden from customers).')

    return redirect('dashboard:inventory_products')


@dashboard_access_required('can_manage_inventory')
@require_POST
def product_reject(request, product_id):
    """
    Decline a pending (farmer-added) product. Distinct from Unapprove:
    rejecting records a reason, sets rejected_at, and takes the product out
    of the "pending approval" queue/count — the farmer sees why it wasn't
    approved on their own Products page. An admin can still reverse this
    later via 'Reconsider' (product_reconsider), which puts it back into
    the pending queue.
    """
    product = get_object_or_404(Product, id=product_id)
    reason = request.POST.get('reason', '').strip()
    product.is_approved = False
    product.rejected_at = timezone.now()
    product.rejection_reason = reason
    product.save(update_fields=['is_approved', 'rejected_at', 'rejection_reason'])
    messages.success(request, f'{product.name} was rejected.')
    return redirect('dashboard:inventory_products')


@dashboard_access_required('can_manage_inventory')
@require_POST
def product_reconsider(request, product_id):
    """Undo a rejection — moves a product back into the pending approval queue."""
    product = get_object_or_404(Product, id=product_id)
    product.rejected_at = None
    product.rejection_reason = ''
    product.save(update_fields=['rejected_at', 'rejection_reason'])
    messages.success(request, f'{product.name} moved back to pending approval.')
    return redirect('dashboard:inventory_products')


@dashboard_access_required('can_manage_inventory')
@require_POST
def product_adjust_stock(request, product_id):
    """
    Add or remove stock for an existing product, without needing to
    delete/recreate it. action='add' increases stock_quantity by the
    given amount; action='remove' decreases it, floored at 0 (never
    goes negative).
    """
    product = get_object_or_404(Product, id=product_id)
    action = request.POST.get('action')
    try:
        amount = int(request.POST.get('amount', 0))
    except (TypeError, ValueError):
        amount = 0

    if amount <= 0:
        messages.error(request, 'Enter a positive number to adjust stock by.')
        return redirect('dashboard:inventory_products')

    if action == 'add':
        product.stock_quantity = F('stock_quantity') + amount
        product.save(update_fields=['stock_quantity'])
        messages.success(request, f'Added {amount} to {product.name} stock.')
    elif action == 'remove':
        # floor at 0: don't let a rushed click take it negative
        Product.objects.filter(pk=product.pk).update(
            stock_quantity=Greatest(F('stock_quantity') - amount, 0)
        )
        messages.success(request, f'Removed {amount} from {product.name} stock.')
    else:
        messages.error(request, 'Unknown stock action.')

    return redirect('dashboard:inventory_products')


@dashboard_access_required('can_manage_inventory')
@require_POST
def product_delete(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.delete()
    messages.success(request, 'Product removed.')
    return redirect('dashboard:inventory_products')


@dashboard_access_required('can_manage_inventory')
@require_POST
def product_toggle_active(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.is_active = not product.is_active
    product.save(update_fields=['is_active'])
    return redirect('dashboard:inventory_products')


# ---------- Product Variants (weight/size options, e.g. 400g / 1kg / 2kg) ----------
@dashboard_access_required('can_manage_inventory')
def product_variants(request, product_id):
    """List + add sizes for one product. A product sold by weight (kg/g)
    with multiple options is set up here; once it has at least one active
    size, the storefront sells it by size only (see Product.has_variants)."""
    product = get_object_or_404(Product, id=product_id)
    variants = product.variants.all()

    if request.method == 'POST':
        form = ProductVariantForm(request.POST)
        if form.is_valid():
            variant = form.save(commit=False)
            variant.product = product
            variant.save()
            messages.success(request, f'Added size "{variant.label}" to {product.name}.')
            return redirect('dashboard:product_variants', product_id=product.id)
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductVariantForm()

    return render(request, 'dashboard/product_variants.html', {
        'product': product,
        'variants': variants,
        'form': form,
    })


@dashboard_access_required('can_manage_inventory')
@require_POST
def product_variant_delete(request, product_id, variant_id):
    variant = get_object_or_404(ProductVariant, id=variant_id, product_id=product_id)
    variant.delete()
    messages.success(request, 'Size removed.')
    return redirect('dashboard:product_variants', product_id=product_id)


@dashboard_access_required('can_manage_inventory')
@require_POST
def product_variant_toggle_active(request, product_id, variant_id):
    variant = get_object_or_404(ProductVariant, id=variant_id, product_id=product_id)
    variant.is_active = not variant.is_active
    variant.save(update_fields=['is_active'])
    return redirect('dashboard:product_variants', product_id=product_id)


@dashboard_access_required('can_manage_inventory')
@require_POST
def product_variant_adjust_stock(request, product_id, variant_id):
    """
    Add or remove stock for one size option, without needing to
    delete/recreate it. action='add' increases stock_quantity by the
    given amount; action='remove' decreases it, floored at 0 (never
    goes negative). Mirrors product_adjust_stock but for a ProductVariant.
    """
    variant = get_object_or_404(ProductVariant, id=variant_id, product_id=product_id)
    action = request.POST.get('action')
    try:
        amount = int(request.POST.get('amount', 0))
    except (TypeError, ValueError):
        amount = 0

    if amount <= 0:
        messages.error(request, 'Enter a positive number to adjust stock by.')
        return redirect('dashboard:product_variants', product_id=product_id)

    if action == 'add':
        variant.stock_quantity = F('stock_quantity') + amount
        variant.save(update_fields=['stock_quantity'])
        messages.success(request, f'Added {amount} to {variant.label} stock.')
    elif action == 'remove':
        ProductVariant.objects.filter(pk=variant.pk).update(
            stock_quantity=Greatest(F('stock_quantity') - amount, 0)
        )
        messages.success(request, f'Removed {amount} from {variant.label} stock.')
    else:
        messages.error(request, 'Unknown stock action.')

    return redirect('dashboard:product_variants', product_id=product_id)


@dashboard_access_required('can_manage_inventory')
@require_POST
def product_variant_update_price(request, product_id, variant_id):
    """Manually set a size option's price (e.g. correcting/updating $/1kg)."""
    variant = get_object_or_404(ProductVariant, id=variant_id, product_id=product_id)
    try:
        new_price = Decimal(request.POST.get('price', ''))
        if new_price <= 0:
            raise InvalidOperation
    except (TypeError, InvalidOperation, ValueError):
        messages.error(request, 'Enter a valid price.')
        return redirect('dashboard:product_variants', product_id=product_id)

    variant.price = new_price
    variant.save(update_fields=['price'])
    messages.success(request, f'Updated {variant.label} price to ₹{new_price}.')
    return redirect('dashboard:product_variants', product_id=product_id)


# ---------- Order Management ----------
@dashboard_access_required('can_manage_orders')
def order_management(request):
    orders = Order.objects.select_related('customer', 'driver').prefetch_related('items')

    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)

    page_obj = Paginator(orders, 20).get_page(request.GET.get('page'))
    drivers = User.objects.filter(role=User.Role.DRIVER, is_verified=True)

    return render(request, 'dashboard/orders.html', {
        'page_obj': page_obj,
        'status_choices': Order.Status.choices,
        'status_filter': status_filter,
        'drivers': drivers,
    })


@dashboard_access_required('can_manage_orders')
@require_POST
def order_update_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    new_status = request.POST.get('status')
    if new_status in dict(Order.Status.choices):
        old_status = order.status
        order.status = new_status
        order.save(update_fields=['status'])

        # Give the stock back if this order is being cancelled (and wasn't
        # already) — otherwise stock deducted at checkout would stay
        # permanently "lost" from Inventory even though nothing shipped.
        if new_status == Order.Status.CANCELLED and old_status != Order.Status.CANCELLED:
            for item in order.items.all():
                if item.variant_id:
                    ProductVariant.objects.filter(pk=item.variant_id).update(
                        stock_quantity=F('stock_quantity') + item.quantity
                    )
                elif item.product_id:
                    Product.objects.filter(pk=item.product_id).update(
                        stock_quantity=F('stock_quantity') + item.quantity
                    )

        # Dispatch appropriate WhatsApp transactional notification
        try:
            from whatsapp_webhook.services import (
                send_order_confirmation,
                send_out_for_delivery_notification,
                send_delivery_otp_matched_confirmation,
            )
            if new_status == Order.Status.CONFIRMED:
                send_order_confirmation(order)
            elif new_status == Order.Status.OUT_FOR_DELIVERY:
                send_out_for_delivery_notification(order)
            elif new_status == Order.Status.DELIVERED:
                send_delivery_otp_matched_confirmation(order)
        except Exception as wa_err:
            import logging
            logging.getLogger(__name__).warning("WhatsApp notification error on Order #%s update: %s", order.id, wa_err)

        messages.success(request, f'Order #{order.id} marked as {order.get_status_display()}.')
    return redirect('dashboard:order_management')


@dashboard_access_required('can_manage_orders')
@require_POST
def order_assign_driver(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    driver_id = request.POST.get('driver_id')
    if driver_id:
        driver = get_object_or_404(User, id=driver_id, role=User.Role.DRIVER)
        assign_driver(order, driver)
        try:
            from whatsapp_webhook.services import send_order_confirmation
            send_order_confirmation(order)
        except Exception:
            pass
        messages.success(request, f'Order #{order.id} assigned to {driver.username}.')
    return redirect('dashboard:order_management')


@dashboard_access_required('can_manage_orders')
@require_POST
def order_auto_assign_driver(request, order_id):
    """
    Admin-triggered auto-assign: runs the same driver-selection logic
    used at checkout, but always overrides (even if a driver is already
    assigned) since the admin is explicitly asking for a reassignment.
    """
    order = get_object_or_404(Order, id=order_id)
    driver = find_best_driver(order)
    if driver is None:
        messages.warning(request, 'No verified driver is available to auto-assign right now.')
    else:
        assign_driver(order, driver)
        try:
            from whatsapp_webhook.services import send_order_confirmation
            send_order_confirmation(order)
        except Exception:
            pass
        messages.success(request, f'Order #{order.id} auto-assigned to {driver.username}.')
    return redirect('dashboard:order_management')


# ---------- Tracking Overview (all active drivers + orders on one map) ----------
@admin_required
def tracking_overview(request):
    """
    One page for the admin to see everything moving right now:
      - every order that's confirmed (driver assigned, not yet picked up)
        or out-for-delivery (driver en route)
      - every rider (driver), verified or not, online or not, so the
        admin can see who's available even if they have no delivery yet
    """
    active_deliveries = Order.objects.filter(
        status__in=[Order.Status.CONFIRMED, Order.Status.OUT_FOR_DELIVERY],
        driver__isnull=False,
    ).select_related('driver', 'customer')

    riders = User.objects.filter(role=User.Role.DRIVER).select_related('location').annotate(
        active_order_count=Count(
            'deliveries',
            filter=Q(deliveries__status__in=[Order.Status.CONFIRMED, Order.Status.OUT_FOR_DELIVERY]),
        )
    ).order_by('-location__is_online', 'username')

    return render(request, 'dashboard/tracking.html', {
        'active_deliveries': active_deliveries,
        'riders': riders,
    })


@admin_required
def rider_locations_api(request):
    """
    Polled by the tracking overview map. Returns the latest known position
    of every driver who has ever shared their location (online or not),
    plus whichever order they're currently on, if any — so the admin sees
    the whole fleet, not just riders mid-delivery.
    """
    riders = User.objects.filter(
        role=User.Role.DRIVER, location__isnull=False
    ).select_related('location')

    active_orders = {
        o.driver_id: o.id for o in Order.objects.filter(
            driver__isnull=False,
            status__in=[Order.Status.CONFIRMED, Order.Status.OUT_FOR_DELIVERY],
        )
    }

    data = [{
        'driver_id': r.id,
        'driver_name': r.get_full_name() or r.username,
        'latitude': float(r.location.latitude),
        'longitude': float(r.location.longitude),
        'is_online': r.location.is_online,
        'updated_at': r.location.updated_at.isoformat(),
        'order_id': active_orders.get(r.id),
    } for r in riders]

    return JsonResponse({'riders': data})


# ---------- Reports ----------
@dashboard_access_required('can_view_reports')
def reports_view(request):
    context = {
        'orders_by_status': Order.objects.values('status').annotate(count=Count('id')),
        'total_revenue': Order.objects.exclude(status=Order.Status.CANCELLED).aggregate(
            total=Sum('total_amount'))['total'] or 0,
        'top_products': Product.objects.annotate(
            total_sold=Sum('orderitem__quantity')
        ).order_by('-total_sold')[:5],
        'total_farms': Farm.objects.count(),
        'total_categories': Category.objects.count(),
    }
    return render(request, 'dashboard/reports.html', context)


# ---------- Farmer Partner Portal (self-service, role == 'farmer') ----------
@role_required('farmer')
def farmer_home(request):
    """
    Farmer's own dashboard: their farm profile(s), product catalogue,
    ISO certificate/verification status, and order-line revenue for
    products sold from their farm(s).
    """
    farms = Farm.objects.filter(owner=request.user)
    products = Product.objects.filter(farm__in=farms).select_related('category')
    kyc, _ = FarmerKYC.objects.get_or_create(user=request.user)

    context = {
        'farms': farms,
        'products': products,
        'kyc': kyc,
        'total_products': products.count(),
        'active_products': products.filter(is_active=True).count(),
        'low_stock_products': products.filter(stock_quantity__lte=5).count(),
    }
    return render(request, 'dashboard/farmer_home.html', context)


@role_required('farmer')
def farmer_farm_profile(request):
    """Create (if none yet) or edit the farmer's own farm profile."""
    farm = Farm.objects.filter(owner=request.user).first()
    if request.method == 'POST':
        form = FarmerFarmProfileForm(request.POST, request.FILES, instance=farm)
        if form.is_valid():
            new_farm = form.save(commit=False)
            new_farm.owner = request.user
            new_farm.save()
            messages.success(request, 'Farm profile saved.')
            return redirect('dashboard:farmer_farm_profile')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = FarmerFarmProfileForm(instance=farm)
    return render(request, 'dashboard/farmer_farm_profile.html', {'form': form, 'farm': farm})


@role_required('farmer')
def farmer_products(request):
    """Farmer's own product catalogue — add/list products tied to their farm(s)."""
    farm = Farm.objects.filter(owner=request.user).first()
    all_products = Product.objects.filter(farm=farm).select_related('category') if farm else Product.objects.none()
    # hidden_by_farmer only affects what the farmer sees on THIS page — it
    # never touches is_active, so admin's Inventory page and the customer
    # store are completely unaffected either way.
    products = all_products.filter(hidden_by_farmer=False)
    hidden_products = all_products.filter(hidden_by_farmer=True)
    has_categories = Category.objects.exists()

    if request.method == 'POST':
        if not farm:
            messages.error(request, 'Set up your farm profile before adding products.')
            return redirect('dashboard:farmer_farm_profile')
        if not has_categories:
            messages.error(request, 'No product categories exist yet — ask an admin to add one before you can add products.')
            return redirect('dashboard:farmer_products')
        form = FarmerProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.farm = farm
            product.bulk_quantity = 1
            product.price = product.cost_price or 0
            if not product.received_date:
                product.received_date = timezone.now().date()
            if not product.harvest_date:
                product.harvest_date = product.received_date
            # Farmer-added products always need admin approval before they
            # go live on the customer-facing store — see
            # inventory.models.LIVE_APPROVED_PRODUCT_Q and
            # dashboard.views.product_toggle_approved.
            product.is_approved = False
            product.save()
            messages.success(request, 'Product added — an admin will set the store price and approve it before it goes live.')
            return redirect('dashboard:farmer_products')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = FarmerProductForm()

    return render(request, 'dashboard/farmer_products.html', {
        'products': products, 'hidden_products': hidden_products,
        'form': form, 'farm': farm, 'has_categories': has_categories,
    })


@role_required('farmer')
@require_POST
def farmer_product_toggle_active(request, product_id):
    product = get_object_or_404(Product, id=product_id, farm__owner=request.user)
    product.is_active = not product.is_active
    product.save(update_fields=['is_active'])
    return redirect('dashboard:farmer_products')


@role_required('farmer')
def farmer_report(request):
    """
    Farmer's product report for a chosen month: how many products were
    added, how much stock was damaged, and how much revenue their
    products represent — broken down per product and summarised at the
    top.

    Revenue here is entirely self-contained to the farmer's own data:
    their own quoted price (cost_price) times the stock quantity
    THEY entered on the product. It never reads Order or OrderItem, so
    it has zero connection to actual customer purchases, the admin
    dashboard, or the store price — nothing on the admin/customer side
    can ever change what a farmer sees here, and vice versa.
    """
    farm = Farm.objects.filter(owner=request.user).first()
    products = Product.objects.filter(farm=farm) if farm else Product.objects.none()

    # Selected month, defaulting to the current one. Expects ?month=YYYY-MM.
    # Only used to scope "added this month" / "damaged this month" below —
    # revenue itself is a snapshot of current stock, not time-boxed.
    today = timezone.now().date()
    month_param = request.GET.get('month', '')
    try:
        year, month = (int(p) for p in month_param.split('-'))
        period_start = today.replace(year=year, month=month, day=1)
    except (ValueError, TypeError):
        period_start = today.replace(day=1)
        month_param = period_start.strftime('%Y-%m')

    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1)

    month_damages = ProductDamage.objects.filter(
        product__in=products, reported_at__gte=period_start, reported_at__lt=period_end,
    ).select_related('product')

    rows = []
    total_revenue = Decimal('0')
    total_stock_quantity = 0
    for product in products:
        damaged_qty = sum(d.quantity for d in month_damages if d.product_id == product.id)
        # Revenue = the farmer's own quoted price times the stock quantity
        # the farmer themselves entered on the product — plain price x qty,
        # e.g. price=2, stock=1 -> revenue=2; price=5, stock=10 -> revenue=50.
        # Rejected products (rejected_at set) never generated any admin
        # purchase, so they contribute ₹0 here regardless of their stock/
        # cost_price — the admin explicitly declined to stock them.
        # No Order/OrderItem lookup anywhere here — this figure is entirely
        # the farmer's own numbers, disconnected from real sales, the
        # store price, and the admin/customer side of the app.
        if product.rejected_at:
            revenue = Decimal('0')
        else:
            unit_cost = product.cost_price
            revenue = (unit_cost * product.stock_quantity) if unit_cost is not None else Decimal('0')

        total_revenue += revenue
        total_stock_quantity += product.stock_quantity

        rows.append({
            'product': product,
            'added_this_month': period_start <= product.created_at.date() < period_end,
            'stock_quantity': product.stock_quantity,
            'revenue': revenue,
            'damaged_qty': damaged_qty,
        })

    context = {
        'farm': farm,
        'rows': rows,
        'period_start': period_start,
        'month_param': month_param,
        'products_added_this_month': products.filter(
            created_at__gte=period_start, created_at__lt=period_end
        ).count(),
        'total_damaged': sum(d.quantity for d in month_damages),
        'total_revenue': total_revenue,
        'total_stock_quantity': total_stock_quantity,
        'has_cost_prices': products.filter(cost_price__isnull=False).exists(),
    }
    return render(request, 'dashboard/farmer_report.html', context)


@role_required('farmer')
@require_POST
def farmer_product_delete(request, product_id):
    """
    Removes a product from the FARMER'S OWN product list only, via the
    hidden_by_farmer flag. This is intentionally disconnected from
    everything else in the app:
      - is_active is never touched, so the customer store's visibility
        of the product doesn't change either way,
      - admin's Inventory page doesn't filter on hidden_by_farmer, so
        the product still shows up there exactly as before,
      - OrderItem rows are never touched, so past/future orders keep
        their product link and data exactly as they were.
    A real, permanent delete is an admin-only action (see product_delete).
    """
    product = get_object_or_404(Product, id=product_id, farm__owner=request.user)
    product.hidden_by_farmer = True
    product.save(update_fields=['hidden_by_farmer'])
    messages.success(request, f'"{product.name}" removed from your list. This only affects what you see here — it stays exactly as-is for admin and customers.')
    return redirect('dashboard:farmer_products')


@role_required('farmer')
@require_POST
def farmer_product_restore(request, product_id):
    """Brings a product back into the farmer's own product list (undoes farmer_product_delete)."""
    product = get_object_or_404(Product, id=product_id, farm__owner=request.user)
    product.hidden_by_farmer = False
    product.save(update_fields=['hidden_by_farmer'])
    messages.success(request, f'"{product.name}" restored to your list.')
    return redirect('dashboard:farmer_products')


# =============================================================================
# WHATSAPP FOLLOW-UP TRACKING & DISPATCH VIEWS
# =============================================================================

@role_required('admin', 'employee')
def whatsapp_followups_view(request):
    """
    Lists all WhatsAppFollowUp tracking rows with filter tabs, search,
    quick stats, and manual 'Send reminder now' action buttons.
    """
    from whatsapp_webhook.models import WhatsAppFollowUp
    from datetime import timedelta

    qs = WhatsAppFollowUp.objects.select_related('related_order', 'related_order__customer').all()

    # Search filter
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(customer_name__icontains=q) |
            Q(phone_number__icontains=q) |
            Q(related_order__id__icontains=q)
        )

    # Status tab filter
    status_filter = request.GET.get('status', 'all').strip().lower()
    if status_filter == 'replied':
        qs = qs.filter(customer_replied=True)
    elif status_filter == 'sent':
        qs = qs.filter(customer_replied=False, followup_template_sent=True)
    elif status_filter == 'pending':
        qs = qs.filter(customer_replied=False, followup_template_sent=False)

    # Calculate statistics across all rows
    all_qs = WhatsAppFollowUp.objects.all()
    stats = {
        'total': all_qs.count(),
        'replied': all_qs.filter(customer_replied=True).count(),
        'sent': all_qs.filter(customer_replied=False, followup_template_sent=True).count(),
        'pending': all_qs.filter(customer_replied=False, followup_template_sent=False).count(),
        'due_12h': all_qs.filter(
            customer_replied=False,
            followup_template_sent=False,
            interactive_message_sent_at__lte=timezone.now() - timedelta(hours=12)
        ).count(),
    }

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'dashboard/whatsapp_followups.html', {
        'page_obj': page_obj,
        'stats': stats,
        'status_filter': status_filter,
        'q': q,
    })


@role_required('admin', 'employee')
@require_POST
def whatsapp_followup_send_now(request, followup_id):
    """
    Manually sends the 12-hour reminder template to override the 12h wait for a specific customer.
    """
    from whatsapp_webhook.models import WhatsAppFollowUp
    from whatsapp_webhook.services import send_followup_reminder

    followup = get_object_or_404(WhatsAppFollowUp, id=followup_id)

    if followup.customer_replied:
        msg = f"Customer +{followup.phone_number} has already replied. Follow-up is not needed."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': msg}, status=400)
        messages.warning(request, msg)
        return redirect('dashboard:whatsapp_followups')

    res = send_followup_reminder(followup)

    if res.get('success'):
        msg = f"Follow-up reminder sent successfully to {followup.customer_name or followup.phone_number} (+{followup.phone_number})."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': msg,
                'status_code': followup.status_code,
                'status_label': followup.status_label,
                'sent_at': followup.followup_template_sent_at.strftime('%b %d, %Y %I:%M %p') if followup.followup_template_sent_at else ''
            })
        messages.success(request, msg)
    else:
        err = res.get('error', 'Failed to dispatch template via Meta API.')
        msg = f"Could not send reminder to +{followup.phone_number}: {err}"
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': msg}, status=500)
        messages.error(request, msg)

    return redirect('dashboard:whatsapp_followups')
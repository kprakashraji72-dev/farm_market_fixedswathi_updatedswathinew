"""
Global template context for the admin/employee dashboard sidebar: pending
counts so badges (e.g. "3 pending approvals") show up wherever sidebar.html
is included, without every view needing to compute and pass them.
Safe no-op for anonymous/non-staff users.
"""
from inventory.models import Product, ProductDamage


def dashboard_pending_counts(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    if not (user.is_admin_role or user.is_employee_role):
        return {}

    counts = {}
    if user.is_admin_role or user.has_employee_permission('can_manage_inventory'):
        counts['sidebar_pending_product_approvals'] = Product.objects.filter(is_approved=False).count()
        counts['sidebar_pending_damage_reviews'] = ProductDamage.objects.filter(
            status=ProductDamage.Status.PENDING
        ).count()
    return counts

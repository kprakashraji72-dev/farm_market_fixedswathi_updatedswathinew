"""
Role-based access decorators, reused by dashboard/tracking apps in later
modules (e.g. @driver_required on tracking views, @admin_required on
dashboard views).
"""
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect


def role_required(*allowed_roles):
    """Generic decorator: only allows users whose .role is in allowed_roles."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                messages.error(request, "You don't have permission to access that page.")
                return redirect(request.user.get_dashboard_url_name())
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def admin_required(view_func):
    return role_required('admin')(view_func)


def dashboard_access_required(perm):
    """
    Allows admins (always) and employees who have been granted `perm`
    (one of 'can_manage_orders', 'can_manage_inventory', 'can_view_reports'
    — see accounts.models.EmployeePermission). Everyone else, including an
    employee without that specific permission, is redirected with an error.
    Use this instead of @admin_required on views an employee should also
    be able to reach.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not request.user.has_employee_permission(perm):
                messages.error(request, "You don't have permission to access that page.")
                return redirect(request.user.get_dashboard_url_name())
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def driver_required(view_func):
    return role_required('driver')(view_func)


def customer_required(view_func):
    return role_required('customer')(view_func)


def support_staff_required(view_func):
    """Allows support_staff role, admin role, or superuser. Redirects unauthenticated users to /support-console/login/."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.info(request, "Please log in with your Support Staff credentials.")
            return redirect(f"/support-console/login/?next={request.path}")
        if not (request.user.is_superuser or request.user.role in ['support_staff', 'admin']):
            messages.error(request, "This account does not have Support Console access.")
            return redirect('customer_support:login')
        return view_func(request, *args, **kwargs)
    return _wrapped


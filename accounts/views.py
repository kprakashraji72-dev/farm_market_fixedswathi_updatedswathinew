"""
Accounts views:
  - register            : public customer sign-up
  - login_view          : shared login for customer/admin/farmer, redirects by role
  - driver_login_view   : separate login page, only accepts role == DRIVER
  - profile_view/edit   : view & update the logged-in user's own profile
  - logout_view         : logs out and redirects to an appropriate landing page
"""
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse

from .forms import (
    CustomerRegistrationForm, StyledAuthenticationForm, DriverLoginForm, ProfileEditForm,
    DriverRegistrationForm, FarmerRegistrationForm, FarmerLoginForm,
    DriverKYCEditForm, FarmerKYCEditForm,
)
from .decorators import driver_required, role_required
from .models import User, DriverKYC, FarmerKYC
from .notifications import send_partner_application_received_email


def register_view(request):
    """Public registration. Always creates a CUSTOMER account (see forms.py)."""
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url_name())

    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome to Fresh Trace, {user.first_name or user.username}!')
            return redirect('store:home')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomerRegistrationForm()

    return render(request, 'store/register.html', {'form': form})


def login_view(request):
    """
    Shared login for customers, farmers, and admins.
    Drivers are intentionally NOT authenticated here — they must use the
    dedicated /accounts/driver/login/ page (driver_login_view below), even
    if their credentials happen to work here, to keep the driver flow
    separate and to make GPS-tracking-page redirects predictable.
    """
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url_name())

    if request.method == 'POST':
        form = StyledAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            if user.role == User.Role.DRIVER:
                messages.warning(
                    request,
                    'Driver accounts must sign in through the Driver Login page.'
                )
                return redirect('accounts:driver_login')

            if user.role == User.Role.SUPPORT_STAFF:
                messages.warning(
                    request,
                    'Support staff accounts must sign in through the Support Console Login page.'
                )
                return redirect('customer_support:login')

            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name or user.username}!')
            return redirect(user.get_dashboard_url_name())
        messages.error(request, 'Invalid username or password.')
    else:
        form = StyledAuthenticationForm()

    return render(request, 'store/login.html', {'form': form})


def driver_register_view(request):
    """
    Public self-registration for delivery partners. Collects the account
    fields plus KYC docs (Aadhar, license, vehicle) in one form. The new
    account starts unverified — the driver is told to wait for admin
    approval and is redirected to the Driver Login page rather than
    logged straight in.
    """
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url_name())

    if request.method == 'POST':
        form = DriverRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            new_driver = form.save()
            send_partner_application_received_email(new_driver)
            messages.success(
                request,
                'Your delivery partner application was submitted! An admin will verify your '
                'documents shortly — you can log in once your account is verified.'
            )
            return redirect('accounts:driver_login')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DriverRegistrationForm()

    return render(request, 'store/driver_register.html', {'form': form})


def farmer_register_view(request):
    """Public self-registration for farm/seller partners, with ISO certificate upload."""
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url_name())

    if request.method == 'POST':
        form = FarmerRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            new_farmer = form.save()
            send_partner_application_received_email(new_farmer)
            messages.success(
                request,
                'Your farmer partner application was submitted! An admin will verify your ISO '
                'certificate shortly — you can log in once your account is verified.'
            )
            return redirect('accounts:farmer_login')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = FarmerRegistrationForm()

    return render(request, 'store/farmer_register.html', {'form': form})


def farmer_login_view(request):
    """Dedicated login page for the Farmer Partner portal."""
    if request.user.is_authenticated and request.user.role == User.Role.FARMER:
        return redirect('dashboard:farmer_home')

    if request.method == 'POST':
        form = FarmerLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            if user.role != User.Role.FARMER:
                messages.error(request, 'This login is for farm/seller partners only.')
                return redirect('accounts:farmer_login')

            if not user.is_verified:
                messages.error(request, 'Your farmer account is pending admin verification.')
                return redirect('accounts:farmer_login')

            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name or user.username}!')
            return redirect('dashboard:farmer_home')
        messages.error(request, 'Invalid farmer credentials.')
    else:
        form = FarmerLoginForm()

    return render(request, 'store/farmer_login.html', {'form': form})


@driver_required
def driver_documents_view(request):
    """Lets a logged-in driver view/update their KYC & renewal documents."""
    kyc, _ = DriverKYC.objects.get_or_create(user=request.user, defaults={
        'aadhar_number': '', 'license_number': '', 'vehicle_number': '',
    })
    if request.method == 'POST':
        form = DriverKYCEditForm(request.POST, request.FILES, instance=kyc)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your documents were updated. Re-verification may be required.')
            return redirect('accounts:driver_documents')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DriverKYCEditForm(instance=kyc)
    return render(request, 'store/driver_documents.html', {'form': form, 'kyc': kyc})


@role_required('farmer')
def farmer_documents_view(request):
    """Lets a logged-in farmer view/update their ISO certificate."""
    kyc, _ = FarmerKYC.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = FarmerKYCEditForm(request.POST, request.FILES, instance=kyc)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your certificate was updated. Re-verification may be required.')
            return redirect('accounts:farmer_documents')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = FarmerKYCEditForm(instance=kyc)
    return render(request, 'store/farmer_documents.html', {'form': form, 'kyc': kyc})


def driver_login_view(request):
    """
    Dedicated login flow for drivers. After a successful login here,
    the driver is sent straight to the live-tracking dashboard
    (tracking:driver_dashboard), where the browser will prompt for
    Geolocation permission (built in Module: Tracking).
    """
    if request.user.is_authenticated and request.user.role == User.Role.DRIVER:
        return redirect('tracking:driver_dashboard')

    if request.method == 'POST':
        form = DriverLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            if user.role != User.Role.DRIVER:
                messages.error(request, 'This login is for delivery drivers only.')
                return redirect('accounts:driver_login')

            if not user.is_verified:
                messages.error(request, 'Your driver account is pending admin verification.')
                return redirect('accounts:driver_login')

            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name or user.username}!')
            return redirect('tracking:driver_dashboard')
        messages.error(request, 'Invalid driver credentials.')
    else:
        form = DriverLoginForm()

    return render(request, 'store/driver_login.html', {'form': form})


@login_required
def profile_view(request):
    """Read-only profile summary page, with a link into edit mode."""
    return render(request, 'store/profile.html', {'profile_user': request.user})


@login_required
def profile_edit_view(request):
    """Lets the logged-in user update their own info (any role)."""
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('accounts:profile')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ProfileEditForm(instance=request.user)

    return render(request, 'store/profile_edit.html', {'form': form})


def logout_view(request):
    """
    Logs out the current user regardless of role and sends them to the
    right landing page: drivers -> driver login (so a shared device
    doesn't stay on a customer page), everyone else -> store home.
    """
    was_driver = request.user.is_authenticated and request.user.role == User.Role.DRIVER
    logout(request)
    messages.info(request, 'You have been logged out.')
    if was_driver:
        return redirect('accounts:driver_login')
    return redirect('store:home')

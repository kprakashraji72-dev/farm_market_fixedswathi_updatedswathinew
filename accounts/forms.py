"""
Forms for registration, profile editing, and the driver-only login.
Standard login (customer/admin) uses Django's built-in AuthenticationForm
directly in the view, styled via widget attrs here where needed.
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.validators import RegexValidator
from .models import User, DriverKYC, FarmerKYC
from .validators import validate_kyc_document, validate_is_driving_license


BOOTSTRAP_INPUT = 'form-control'

# Registration only: exactly 10 digits, no spaces/dashes/country code.
phone_10_digit_validator = RegexValidator(
    regex=r'^\d{10}$',
    message='Enter a valid 10-digit mobile number (digits only, no spaces or country code).',
)

aadhar_validator = RegexValidator(
    regex=r'^\d{12}$',
    message='Enter a valid 12-digit Aadhar number (digits only).',
)


class CustomerRegistrationForm(UserCreationForm):
    """
    Public self-registration form. Role is fixed to CUSTOMER — customers
    cannot grant themselves admin/driver roles via signup. Driver and
    Admin accounts are provisioned by an admin via the dashboard (Module
    'User Management'), not through this public form.
    """
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(
        required=True,
        max_length=10,
        min_length=10,
        validators=[phone_10_digit_validator],
        widget=forms.TextInput(attrs={
            'maxlength': '10',
            'inputmode': 'numeric',
            'pattern': r'\d{10}',
            'placeholder': '10-digit mobile number',
            'autocomplete': 'tel',
        }),
    )
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

    class Meta:
        model = User
        fields = ['username', 'email', 'phone_number', 'address', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': BOOTSTRAP_INPUT})

    def clean_phone_number(self):
        """Strip whitespace and enforce digits-only, exactly 10 characters."""
        phone = self.cleaned_data.get('phone_number', '').strip()
        if not phone.isdigit() or len(phone) != 10:
            raise forms.ValidationError('Enter a valid 10-digit mobile number (digits only, no spaces or country code).')
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.CUSTOMER
        user.email = self.cleaned_data['email']
        user.phone_number = self.cleaned_data['phone_number']
        user.address = self.cleaned_data.get('address', '')
        if commit:
            user.save()
        return user


class StyledAuthenticationForm(AuthenticationForm):
    """Django's login form, with Bootstrap classes applied to widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': BOOTSTRAP_INPUT, 'autofocus': True})
        self.fields['password'].widget.attrs.update({'class': BOOTSTRAP_INPUT})


class DriverRegistrationForm(UserCreationForm):
    """
    Self-registration for delivery partners. Captures the account fields
    plus the KYC documents (Aadhar, driving license, vehicle number) up
    front, so a driver can't finish signup without them. The account is
    created with is_verified=False — an admin must verify the KYC in
    Dashboard -> Role Management before the driver can actually log in
    (see accounts.views.driver_login_view).
    """
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(
        required=True, max_length=10, min_length=10,
        validators=[phone_10_digit_validator],
        widget=forms.TextInput(attrs={
            'maxlength': '10', 'inputmode': 'numeric', 'pattern': r'\d{10}',
            'placeholder': '10-digit mobile number', 'autocomplete': 'tel',
        }),
    )
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

    date_of_birth = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Driver must be at least 18 years old to register.',
    )
    aadhar_number = forms.CharField(
        required=True, max_length=12, min_length=12, validators=[aadhar_validator],
        widget=forms.TextInput(attrs={'maxlength': '12', 'inputmode': 'numeric', 'placeholder': '12-digit Aadhar number'}),
    )
    aadhar_document = forms.FileField(required=True, validators=[validate_kyc_document],
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}),
        help_text='Upload a clear photo or scan (PDF/JPG/PNG, max 5 MB).')
    license_number = forms.CharField(required=True, max_length=30, widget=forms.TextInput(attrs={'placeholder': 'Driving license number'}))
    license_document = forms.FileField(required=True, validators=[validate_kyc_document, validate_is_driving_license],
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}),
        help_text='Upload your driving license (PDF/JPG/PNG, max 5 MB).')
    license_expiry_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    vehicle_number = forms.CharField(required=True, max_length=20, widget=forms.TextInput(attrs={'placeholder': 'e.g. TN09AB1234'}))
    vehicle_document = forms.FileField(required=False, validators=[validate_kyc_document],
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}),
        help_text='RC book / registration certificate (PDF/JPG/PNG, max 5 MB; optional).')
    renewal_amount = forms.DecimalField(required=False, max_digits=10, decimal_places=2, help_text='Amount paid for last license/vehicle renewal, if any.')
    renewal_due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}), help_text='Next renewal due date, if known.')

    class Meta:
        model = User
        fields = ['username', 'email', 'phone_number', 'address', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.FileInput, forms.DateInput)):
                field.widget.attrs.update({'class': BOOTSTRAP_INPUT})
            else:
                field.widget.attrs.update({'class': BOOTSTRAP_INPUT})

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        if not phone.isdigit() or len(phone) != 10:
            raise forms.ValidationError('Enter a valid 10-digit mobile number (digits only, no spaces or country code).')
        return phone

    def clean_aadhar_number(self):
        aadhar = self.cleaned_data.get('aadhar_number', '').strip()
        if not aadhar.isdigit() or len(aadhar) != 12:
            raise forms.ValidationError('Enter a valid 12-digit Aadhar number.')
        return aadhar

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if not dob:
            raise forms.ValidationError('Date of birth is required.')
        from django.utils import timezone
        today = timezone.now().date()
        if dob > today:
            raise forms.ValidationError('Date of birth cannot be in the future.')
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 18:
            raise forms.ValidationError(
                f'Driver age is {age} years. You must be at least 18 years old to register as a delivery driver. Permission denied.'
            )
        return dob

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.DRIVER
        user.is_verified = False  # admin must verify KYC before driver can log in
        user.email = self.cleaned_data['email']
        user.phone_number = self.cleaned_data['phone_number']
        user.address = self.cleaned_data.get('address', '')
        if commit:
            user.save()
            DriverKYC.objects.create(
                user=user,
                date_of_birth=self.cleaned_data.get('date_of_birth'),
                aadhar_number=self.cleaned_data['aadhar_number'],
                aadhar_document=self.cleaned_data['aadhar_document'],
                license_number=self.cleaned_data['license_number'],
                license_document=self.cleaned_data['license_document'],
                license_expiry_date=self.cleaned_data.get('license_expiry_date'),
                vehicle_number=self.cleaned_data['vehicle_number'],
                vehicle_document=self.cleaned_data.get('vehicle_document'),
                renewal_amount=self.cleaned_data.get('renewal_amount'),
                renewal_due_date=self.cleaned_data.get('renewal_due_date'),
            )
        return user


class FarmerRegistrationForm(UserCreationForm):
    """
    Self-registration for farm/seller partners. Captures the account
    fields plus the ISO (or equivalent) certificate up front. Created
    with is_verified=False until an admin checks the certificate.
    """
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(
        required=True, max_length=10, min_length=10,
        validators=[phone_10_digit_validator],
        widget=forms.TextInput(attrs={
            'maxlength': '10', 'inputmode': 'numeric', 'pattern': r'\d{10}',
            'placeholder': '10-digit mobile number', 'autocomplete': 'tel',
        }),
    )
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

    iso_certificate_number = forms.CharField(required=False, max_length=60, widget=forms.TextInput(attrs={'placeholder': 'Certificate number (optional)'}))
    iso_certificate_document = forms.FileField(required=True, validators=[validate_kyc_document],
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}),
        help_text='Upload your ISO / food-safety / organic certificate (PDF/JPG/PNG, max 5 MB).')
    iso_issue_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    iso_expiry_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'phone_number', 'address', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': BOOTSTRAP_INPUT})

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        if not phone.isdigit() or len(phone) != 10:
            raise forms.ValidationError('Enter a valid 10-digit mobile number (digits only, no spaces or country code).')
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.FARMER
        user.is_verified = False  # admin must verify the ISO certificate first
        user.email = self.cleaned_data['email']
        user.phone_number = self.cleaned_data['phone_number']
        user.address = self.cleaned_data.get('address', '')
        if commit:
            user.save()
            FarmerKYC.objects.create(
                user=user,
                iso_certificate_number=self.cleaned_data.get('iso_certificate_number', ''),
                iso_certificate_document=self.cleaned_data['iso_certificate_document'],
                iso_issue_date=self.cleaned_data.get('iso_issue_date'),
                iso_expiry_date=self.cleaned_data.get('iso_expiry_date'),
            )
        return user


class EmployeeCreateForm(UserCreationForm):
    """
    Admin-only form (Dashboard -> Staff Management -> Create Employee) for
    provisioning in-store staff accounts directly with a username/password,
    instead of promoting an existing customer account on Role Management.
    Role is fixed to EMPLOYEE and the account is active immediately —
    dashboard access is still gated by EmployeePermission until the admin
    grants specific permissions (see dashboard.views.employee_permissions_update).
    """
    email = forms.EmailField(required=False)
    phone_number = forms.CharField(
        required=False, max_length=10, min_length=10,
        validators=[phone_10_digit_validator],
        widget=forms.TextInput(attrs={
            'maxlength': '10', 'inputmode': 'numeric', 'pattern': r'\d{10}',
            'placeholder': '10-digit mobile number (optional)', 'autocomplete': 'tel',
        }),
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'phone_number', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': BOOTSTRAP_INPUT})

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        if phone and (not phone.isdigit() or len(phone) != 10):
            raise forms.ValidationError('Enter a valid 10-digit mobile number (digits only, no spaces or country code).')
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.EMPLOYEE
        user.email = self.cleaned_data.get('email', '')
        user.phone_number = self.cleaned_data.get('phone_number', '')
        if commit:
            user.save()
        return user


class FarmerLoginForm(AuthenticationForm):
    """Dedicated login form for the Farmer Partner portal."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update(
            {'class': BOOTSTRAP_INPUT, 'placeholder': 'Farmer username', 'autofocus': True}
        )
        self.fields['password'].widget.attrs.update(
            {'class': BOOTSTRAP_INPUT, 'placeholder': 'Password'}
        )


class DriverKYCEditForm(forms.ModelForm):
    """Lets an already-registered driver update their KYC/renewal info later."""

    class Meta:
        model = DriverKYC
        fields = [
            'date_of_birth',
            'aadhar_number', 'aadhar_document',
            'license_number', 'license_document', 'license_expiry_date',
            'vehicle_number', 'vehicle_document',
            'renewal_amount', 'renewal_due_date',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'license_expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'renewal_due_date': forms.DateInput(attrs={'type': 'date'}),
            'aadhar_document': forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}),
            'license_document': forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}),
            'vehicle_document': forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': BOOTSTRAP_INPUT})

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            from django.utils import timezone
            today = timezone.now().date()
            if dob > today:
                raise forms.ValidationError('Date of birth cannot be in the future.')
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 18:
                raise forms.ValidationError(
                    f'Driver age is {age} years. Driver must be at least 18 years old. Permission denied.'
                )
        return dob

    def clean_license_document(self):
        doc = self.cleaned_data.get('license_document')
        if doc and 'license_document' in self.changed_data:
            validate_is_driving_license(doc)
        return doc


class FarmerKYCEditForm(forms.ModelForm):
    """Lets an already-registered farmer update their ISO certificate later."""

    class Meta:
        model = FarmerKYC
        fields = ['iso_certificate_number', 'iso_certificate_document', 'iso_issue_date', 'iso_expiry_date']
        widgets = {
            'iso_issue_date': forms.DateInput(attrs={'type': 'date'}),
            'iso_expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'iso_certificate_document': forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': BOOTSTRAP_INPUT})


class DriverLoginForm(AuthenticationForm):
    """
    Separate login form used only on the driver login page. It reuses
    Django's authentication logic but the view enforces that the
    authenticated user actually has role == DRIVER, so a customer/admin
    can't accidentally (or deliberately) land in the driver flow just by
    using this URL.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update(
            {'class': BOOTSTRAP_INPUT, 'placeholder': 'Driver username', 'autofocus': True}
        )
        self.fields['password'].widget.attrs.update(
            {'class': BOOTSTRAP_INPUT, 'placeholder': 'Password'}
        )


class ProfileEditForm(forms.ModelForm):
    """Lets a logged-in user (any role) update their own profile info."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'address', 'profile_image']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != 'profile_image':
                field.widget.attrs.update({'class': BOOTSTRAP_INPUT})
            else:
                field.widget.attrs.update({'class': 'form-control'})

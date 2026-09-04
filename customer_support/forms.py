from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import SupportTicket
from orders.models import Order

User = get_user_model()


class SupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ['order', 'category', 'subject', 'message', 'attachment']
        widgets = {
            'order': forms.Select(attrs={
                'class': 'form-select rounded-3',
            }),
            'category': forms.Select(attrs={
                'class': 'form-select rounded-3',
            }),
            'subject': forms.TextInput(attrs={
                'class': 'form-control rounded-3',
                'placeholder': 'e.g. Question about my delivery or item freshness',
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control rounded-3',
                'rows': 5,
                'placeholder': 'Please provide details regarding your inquiry, issue, or feedback...',
            }),
            'attachment': forms.FileInput(attrs={
                'class': 'form-control rounded-3',
                'accept': 'image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt,.zip'
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.is_authenticated:
            self.fields['order'].queryset = Order.objects.filter(customer=user).order_by('-created_at')
            self.fields['order'].empty_label = "None (General Inquiry / Not Order Specific)"
        else:
            self.fields['order'].queryset = Order.objects.none()
            self.fields['order'].empty_label = "None (General Inquiry)"


class SupportStaffLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'Enter staff username',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'Enter password',
        })
    )


class CreateSupportStaffForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'e.g. agent_sarah',
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'e.g. sarah@freshtrace.com',
        })
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'First Name',
        })
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'Last Name',
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'Create strong password',
        })
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control rounded-3',
            'placeholder': 'Confirm password',
        })
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("This username is already taken. Please choose another.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', "Passwords do not match.")
            else:
                try:
                    validate_password(password)
                except ValidationError as e:
                    self.add_error('password', e)
        return cleaned_data

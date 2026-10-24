import os
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import Document, Folder, PermissionGrant

User = get_user_model()


class DocumentUploadForm(forms.ModelForm):
    parent_folder = forms.ModelChoiceField(queryset=Folder.objects.none(), required=False, label='Folder')

    class Meta:
        model = Document
        fields = ['title', 'file', 'parent_folder']

    def __init__(self, *args, **kwargs):
        owner = kwargs.pop('owner', None)
        super().__init__(*args, **kwargs)
        queryset = Folder.objects.none()
        if owner is not None:
            queryset = Folder.objects.filter(owner=owner)
        self.fields['parent_folder'].queryset = queryset

    def clean_file(self):
        uploaded = self.cleaned_data.get('file')
        if uploaded is None:
            raise ValidationError('A document file is required.')

        if uploaded.size > settings.MAX_UPLOAD_SIZE:
            maximum_mb = settings.MAX_UPLOAD_SIZE / (1024 * 1024)
            raise ValidationError(f'File exceeds the {maximum_mb:g} MB upload limit.')

        return uploaded

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if not title:
            raise ValidationError('Please provide a title for this document.')
        if os.path.basename(title) != title:
            raise ValidationError('Invalid title.')
        return title


class RegistrationForm(UserCreationForm):
    PASSWORD_VALIDATION_MESSAGES = {
        'password_too_similar': 'Your password is too similar to your username or other personal information. Please choose a different password.',
        'password_too_short': 'Your password is too short. Please use a longer password.',
        'password_too_common': 'Your password is too common. Please choose a different password.',
        'password_entirely_numeric': 'Please choose a password that is not entirely numeric.',
    }

    email = forms.EmailField(required=False, help_text='Optional.')

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def clean_username(self):
        username = (self.cleaned_data.get('username') or '').strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('A user with that username already exists.')
        return username

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError('A user with that email already exists.')
        return email

    def _post_clean(self):
        super()._post_clean()
        errors = self.errors.as_data().get('password2', [])
        if not errors:
            return

        friendly_errors = []
        for error in errors:
            if error.code == 'password_mismatch':
                message = 'The two passwords did not match. Please try again.'
            else:
                message = self.PASSWORD_VALIDATION_MESSAGES.get(
                    error.code,
                    'Please choose a different password and try again.',
                )
            friendly_errors.append(ValidationError(message, code=error.code))
        self._errors['password2'] = self.error_class(friendly_errors)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.OWNER
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class FolderForm(forms.ModelForm):
    class Meta:
        model = Folder
        fields = ['name', 'parent']

    def __init__(self, *args, **kwargs):
        owner = kwargs.pop('owner', None)
        super().__init__(*args, **kwargs)
        if owner is not None:
            self.fields['parent'].queryset = Folder.objects.filter(owner=owner)

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise ValidationError('Folder name is required.')
        if os.path.basename(name) != name:
            raise ValidationError('Invalid folder name.')
        return name


class PermissionForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none(), label='User')
    permission = forms.ChoiceField(choices=PermissionGrant.PERMISSION_CHOICES)

    def __init__(self, *args, **kwargs):
        available_users = kwargs.pop('available_users', None)
        super().__init__(*args, **kwargs)
        if available_users is not None:
            self.fields['user'].queryset = available_users


class DocumentEditForm(forms.Form):
    content = forms.CharField(widget=forms.Textarea(attrs={'rows': 18, 'class': 'form-control'}), required=False)


class DocumentRenameForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title']

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if not title:
            raise ValidationError('Please provide a document name.')
        return title

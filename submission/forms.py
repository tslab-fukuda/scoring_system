# 提出物のフォーム

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Submission

# 提出フォーム
class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ['file']

# サインアップフォーム
class SignUpForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('username', 'email', 'password')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        allowed_domain = 'g.nihon-u.ac.jp'  # ← 必要に応じて変更
        if not email.endswith(f'@{allowed_domain}'):
            raise ValidationError(f'{allowed_domain} ドメインのメールアドレスのみ使用できます。')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")

        if password and confirm and password != confirm:
            raise ValidationError("パスワードが一致しません。")
# 提出物のフォーム

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Submission
from django.contrib.auth.forms import UserChangeForm
from .models import UserProfile

# 提出フォーム
class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ['file']

# サインアップフォーム
class SignUpForm(forms.ModelForm):
    username = forms.CharField(label="メールアドレス(日大アカウント)", max_length=150)
    password = forms.CharField(label="パスワード", widget=forms.PasswordInput)
    confirm_password = forms.CharField(label="パスワード（確認）", widget=forms.PasswordInput)
    full_name = forms.CharField(label="名前", max_length=100)
    student_id = forms.CharField(label="学籍番号", max_length=4)
    experiment_day = forms.ChoiceField(
        label="実験曜日",
        choices=[('火', '火'), ('木', '木')]
    )
    experiment_group = forms.ChoiceField(
        label="実験班",
        choices=[(f"{i:02}", f"{i:02}") for i in range(1, 21)]
    )

    class Meta:
        model = User
        fields = ("username", "password")

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

class UserEditForm(forms.ModelForm):
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES, label="ロール")
    
    class Meta:
        model = UserProfile
        fields = ['full_name', 'student_id', 'experiment_day', 'experiment_group', 'role']
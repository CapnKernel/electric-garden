from django.conf import settings
from django.shortcuts import render
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)


# /accounts/password_reset/	authuser.views.MyPasswordResetView	password_reset
class MyPasswordResetView(PasswordResetView):
    from_email = settings.PASSWORD_RESET_FROM_EMAIL
    template_name = 'registration/my_password_reset_form.html'
    email_template_name = 'registration/my_password_reset_email.html'
    subject_template_name = 'registration/my_password_reset_subject.txt'


# /accounts/password_reset/done/	django.contrib.auth.views.MyPasswordResetDoneView	password_reset_done
class MyPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'registration/my_password_reset_done.html'


# /accounts/reset/<uidb64>/<token>/	django.contrib.auth.views.MyPasswordResetConfirmView	password_reset_confirm
class MyPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'registration/my_password_reset_confirm.html'


# /accounts/reset/done/	django.contrib.auth.views.MyPasswordResetCompleteView	password_reset_complete
class MyPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'registration/my_password_reset_complete.html'

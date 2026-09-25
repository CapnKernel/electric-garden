from django.urls import include, path

from . import views

# Rewrite the password reset url handler with our own views that point to our templates
overrides = {
    'password_reset': views.MyPasswordResetView,
    'password_reset_done': views.MyPasswordResetDoneView,
    'password_reset_confirm': views.MyPasswordResetConfirmView,
    'password_reset_complete': views.MyPasswordResetCompleteView,
}

auth_patterns = path('', include('django.contrib.auth.urls'))
for i, pattern in enumerate(auth_patterns.url_patterns):
    if pattern.name in overrides:
        route = auth_patterns.url_patterns[i].pattern._route
        auth_patterns.url_patterns[i] = path(route, overrides[pattern.name].as_view(), name=pattern.name)

urlpatterns = [auth_patterns]

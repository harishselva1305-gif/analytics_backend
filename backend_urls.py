"""URL configuration loaded after Django's application registry is ready."""

from django.contrib import admin
from django.urls import path

import backend
import backend_admin  # noqa: F401  Register report models with Django Admin.

urlpatterns = [
    path("admin/login/", backend.login_page, name="admin-login"),
    path("admin/", backend.admin_dashboard, name="admin-home"),
    path("admin/dashboard/", backend.admin_dashboard, name="admin-dashboard"),
    path("django-admin/", admin.site.urls),
    *backend.urlpatterns,
]

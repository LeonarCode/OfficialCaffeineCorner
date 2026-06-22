"""
URL configuration for caffeine_corner project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView
from inventory.views import SalesReportView, mark_notification_read, sales_report_view, export_orders, auto_generate_purchase_orders
from online_shop.views import dine_in_landing, generate_table_qr, print_order_receipt, table_qr_page

urlpatterns = [
    path('admin/sales-report/', sales_report_view, name='sales-report'),
    path('admin/mark-notification-read/<int:notification_id>/', mark_notification_read, name='mark-notification-read'),
    path('admin/auto-generate-po/', auto_generate_purchase_orders, name='auto-generate-po'),
    path('admin/orders/<int:order_id>/receipt/', print_order_receipt, name='print-receipt'),
    path('admin/export-orders/', export_orders, name='export-orders'),
    path('admin/table-qr/', table_qr_page, name='table-qr-page'),                          # ← page
    path('admin/table-qr/<str:table_number>/', generate_table_qr, name='table-qr'),        # ← download
    path('admin/', admin.site.urls),
    path('table/<str:table_number>/', dine_in_landing, name='dine-in-landing'),
    path('api/', include('online_shop.urls')),
    path('api/auth/', include('authentication.urls')),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('api/reports/sales/', SalesReportView.as_view(), name='sales-report-api'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

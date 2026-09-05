from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('scanner/', views.scanner_ui, name='scanner_ui'),
    path('api/inbound/', views.log_inbound, name='log_inbound'),
    path('api/outbound/', views.log_outbound, name='log_outbound'),
    path('api/return/', views.log_return, name='log_return'),
    path('api/lookup/', views.lookup_product, name='lookup_product'),
    path('catalogue/', views.live_catalogue, name='catalogue'),
    path('dashboard/', views.financial_dashboard, name='dashboard'),

    path('setup/', views.setup_wizard, name='setup_wizard'),
    path('brand-asset/<str:filename>', views.serve_brand_asset, name='serve_brand_asset'),

    path('login/', auth_views.LoginView.as_view(
        template_name='scanner_login.html', redirect_authenticated_user=True
    ), name='scanner_login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='scanner_login'), name='scanner_logout'),

    path('manifest.webmanifest', views.pwa_manifest, name='pwa_manifest'),
    path('sw.js', views.service_worker, name='service_worker'),
]

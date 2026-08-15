from django.urls import path
from . import views

urlpatterns = [
    path('', views.scanner_ui, name='scanner_ui'),
    path('api/inbound/', views.log_inbound, name='log_inbound'),
    path('api/outbound/', views.log_outbound, name='log_outbound'),
    path('api/return/', views.log_return, name='log_return'),
]
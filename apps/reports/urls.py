from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.farm_progress_report, name='farm_progress'),
    path('export/', views.farm_progress_export, name='farm_progress_export'),
]

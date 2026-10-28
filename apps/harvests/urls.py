from django.urls import path

from . import views

app_name = 'harvests'

urlpatterns = [
    # Page
    path('', views.harvest_list_page, name='harvest_list'),
    path('history/', views.harvest_history_page, name='harvest_history'),
    path('history/export/', views.harvest_history_export, name='harvest_history_export'),
    path('history/ajax/quality/save/', views.harvest_quality_save_ajax, name='harvest_quality_save'),
    # Harvest records (AJAX)
    path('ajax/list/', views.harvest_list_ajax, name='harvest_list_ajax'),
    path('ajax/get/<int:pk>/', views.harvest_get_ajax, name='harvest_get_ajax'),
    path('ajax/save/', views.harvest_save_ajax, name='harvest_save_ajax'),
    path('ajax/delete/<int:pk>/', views.harvest_delete_ajax, name='harvest_delete_ajax'),
    # Notifications / readiness (AJAX)
    path('notifications/ajax/read/', views.harvest_notification_read_ajax, name='harvest_notification_read'),
    path('readiness/ajax/refresh/', views.harvest_refresh_readiness_ajax, name='harvest_refresh_readiness'),
]

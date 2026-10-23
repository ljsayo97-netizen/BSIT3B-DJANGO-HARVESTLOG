from django.urls import path

from . import views

app_name = 'harvests'

urlpatterns = [
    # Page
    path('', views.harvest_list_page, name='harvest_list'),
    path('history/', views.harvest_history_page, name='harvest_history'),
    path('history/export/', views.harvest_history_export, name='harvest_history_export'),
    # Harvest records (AJAX)
    path('ajax/list/', views.harvest_list_ajax, name='harvest_list_ajax'),
    path('ajax/get/<int:pk>/', views.harvest_get_ajax, name='harvest_get_ajax'),
    path('ajax/save/', views.harvest_save_ajax, name='harvest_save_ajax'),
    path('ajax/delete/<int:pk>/', views.harvest_delete_ajax, name='harvest_delete_ajax'),
    # Harvest schedules (AJAX)
    path('schedules/ajax/list/', views.harvest_schedule_list_ajax, name='harvest_schedule_list_ajax'),
    path('schedules/ajax/get/<int:pk>/', views.harvest_schedule_get_ajax, name='harvest_schedule_get_ajax'),
    path('schedules/ajax/save/', views.harvest_schedule_save_ajax, name='harvest_schedule_save_ajax'),
    path('schedules/ajax/delete/<int:pk>/', views.harvest_schedule_delete_ajax, name='harvest_schedule_delete_ajax'),
]

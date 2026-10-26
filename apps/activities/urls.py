from django.urls import path

from . import views

app_name = 'activities'

urlpatterns = [
    # Page
    path('', views.activity_list_page, name='activity_list'),
    path('export/', views.activity_export, name='activity_export'),
    # Farm activities (AJAX)
    path('ajax/list/', views.activity_list_ajax, name='activity_list_ajax'),
    path('ajax/get/<int:pk>/', views.activity_get_ajax, name='activity_get_ajax'),
    path('ajax/save/', views.activity_save_ajax, name='activity_save_ajax'),
    path('ajax/status/<int:pk>/', views.activity_status_ajax, name='activity_status_ajax'),
    path('ajax/delete/<int:pk>/', views.activity_delete_ajax, name='activity_delete_ajax'),
]

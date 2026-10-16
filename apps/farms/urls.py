from django.urls import path
from . import views

app_name = 'farms'

urlpatterns = [
    # Page
    path('', views.farm_list_page, name='farm_list'),
    # AJAX
    path('ajax/list/', views.farm_list_ajax, name='farm_list_ajax'),
    path('ajax/get/<int:pk>/', views.farm_get_ajax, name='farm_get_ajax'),
    path('ajax/save/', views.farm_save_ajax, name='farm_save_ajax'),
    path('ajax/delete/<int:pk>/', views.farm_delete_ajax, name='farm_delete_ajax'),
    path('ajax/archive/<int:pk>/', views.farm_archive_ajax, name='farm_archive_ajax'),
]

from django.urls import path
from . import views

app_name = 'crops'

urlpatterns = [
    # Page
    path('', views.crop_list_page, name='crop_list'),
    # AJAX
    path('ajax/list/', views.crop_list_ajax, name='crop_list_ajax'),
    path('ajax/get/<int:pk>/', views.crop_get_ajax, name='crop_get_ajax'),
    path('ajax/save/', views.crop_save_ajax, name='crop_save_ajax'),
    path('ajax/delete/<int:pk>/', views.crop_delete_ajax, name='crop_delete_ajax'),
]

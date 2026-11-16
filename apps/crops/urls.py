from django.urls import path
from . import views

app_name = 'crops'

urlpatterns = [
    # Page
    path('', views.crop_list_page, name='crop_list'),
    # AJAX
    path('ajax/list/', views.crop_list_ajax, name='crop_list_ajax'),
    path('ajax/get/<int:pk>/', views.crop_get_ajax, name='crop_get_ajax'),
    path('ajax/detail/<int:pk>/', views.crop_detail_ajax, name='crop_detail_ajax'),
    path('ajax/inventory/', views.crop_inventory_ajax, name='crop_inventory_ajax'),
    path('ajax/save/', views.crop_save_ajax, name='crop_save_ajax'),
    path('ajax/delete/<int:pk>/', views.crop_delete_ajax, name='crop_delete_ajax'),
    path(
        'ajax/calculate-harvest/',
        views.crop_calculate_harvest_ajax,
        name='crop_calculate_harvest_ajax',
    ),
    path('ajax/varieties/', views.crop_varieties_ajax, name='crop_varieties_ajax'),
    path(
        'ajax/search-images/',
        views.crop_search_images_ajax,
        name='crop_search_images_ajax',
    ),
    path(
        'ajax/user-prior-image/',
        views.crop_user_prior_image_ajax,
        name='crop_user_prior_image_ajax',
    ),
]

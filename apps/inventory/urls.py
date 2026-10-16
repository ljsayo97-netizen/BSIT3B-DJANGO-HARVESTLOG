from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Page
    path('', views.inventory_list_page, name='inventory_list'),
    # AJAX
    path('ajax/list/', views.inventory_list_ajax, name='inventory_list_ajax'),
    path('ajax/get/<int:pk>/', views.inventory_get_ajax, name='inventory_get_ajax'),
    path('ajax/save/', views.inventory_save_ajax, name='inventory_save_ajax'),
    path('ajax/delete/<int:pk>/', views.inventory_delete_ajax, name='inventory_delete_ajax'),
    path('ajax/adjust/<int:pk>/', views.inventory_adjust_ajax, name='inventory_adjust_ajax'),
]

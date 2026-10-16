from django.urls import path
from . import views

app_name = 'harvests'

urlpatterns = [
    # Page
    path('', views.harvest_list_page, name='harvest_list'),
    # AJAX
    path('ajax/list/', views.harvest_list_ajax, name='harvest_list_ajax'),
    path('ajax/get/<int:pk>/', views.harvest_get_ajax, name='harvest_get_ajax'),
    path('ajax/save/', views.harvest_save_ajax, name='harvest_save_ajax'),
    path('ajax/delete/<int:pk>/', views.harvest_delete_ajax, name='harvest_delete_ajax'),
]

from django.urls import path

from . import views

app_name = 'crops'

urlpatterns = [
    path('', views.crop_list, name='crop_list'),
    path('<int:pk>/edit/', views.crop_edit, name='crop_edit'),
    path('<int:pk>/delete/', views.crop_delete, name='crop_delete'),
    path('harvests/', views.harvest_list, name='harvest_list'),
    path('sales/', views.sale_list, name='sale_list'),
    path('yields/', views.yield_report, name='yield_report'),
]

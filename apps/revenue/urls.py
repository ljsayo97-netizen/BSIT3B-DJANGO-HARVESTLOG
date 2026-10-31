from django.urls import path

from . import views

app_name = 'revenue'

urlpatterns = [
    path('', views.revenue_list_page, name='revenue_list'),
    path('analytics/', views.revenue_analytics_page, name='revenue_analytics'),
    path('export/', views.revenue_export, name='revenue_export'),
    path('ajax/save/', views.revenue_save_ajax, name='revenue_save_ajax'),
    path(
        'ajax/delete/<int:pk>/',
        views.revenue_delete_ajax,
        name='revenue_delete_ajax',
    ),
]

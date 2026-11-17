from django.urls import path

from . import views

app_name = 'hectares'

urlpatterns = [
    path('', views.hectare_monitoring, name='hectare_monitoring'),
]

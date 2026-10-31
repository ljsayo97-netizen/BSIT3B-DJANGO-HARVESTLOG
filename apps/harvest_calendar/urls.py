from django.urls import path

from . import views

app_name = 'harvest_calendar'

urlpatterns = [
    path('', views.harvest_calendar_page, name='calendar'),
]

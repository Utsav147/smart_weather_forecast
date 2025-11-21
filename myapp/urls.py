from django.urls import path
from . import views

urlpatterns = [
    path('', views.today_view, name='today'),
    path('hourly/', views.hourly_view, name='hourly'),
    path('10day/', views.tenday_view, name='10day'),
    path('monthly/', views.monthly_view, name='monthly'),
    path('image/', views.image_view, name='image'),
]

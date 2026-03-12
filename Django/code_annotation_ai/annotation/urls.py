from django.urls import path
from . import views

app_name = "anno"

urlpatterns = [
    path('', views.predict, name='predict'),
]
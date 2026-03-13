from django.urls import path
from . import views

app_name = "anno"

urlpatterns = [
    path('', views.predict, name='predict'),
    path('result/<str:task_id>/', views.get_result, name="result")
]
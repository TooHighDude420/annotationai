import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'code_annotation_ai.settings')

app = Celery('code_annotation_ai')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
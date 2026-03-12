from celery import shared_task
from .utils import main
import json

@shared_task(bind=True)
def run_review_task(self, tmprepoloc, annosaveloc):
    main.run_pipeline(str(tmprepoloc), str(annosaveloc))
    with open(annosaveloc, "r") as handle:
        return json.load(handle)
from celery import shared_task
from .utils import main
from git import Repo
import hashlib
import json
import shutil

@shared_task(bind=True)
def run_review_task(self, repo_url, level):
    url_slug = repo_url.replace("https://", "").replace("/", "_").replace(".", "_")
    unique_suffix = hashlib.md5(repo_url.encode()).hexdigest()[:8]
    tmpname = f"{url_slug}_{unique_suffix}"
    
    from django.conf import settings
    BASE_DIR = settings.BASE_DIR
    
    tmprepoloc = BASE_DIR / "annotation" / "utils" / "tmprepo" / tmpname
    
    Repo.clone_from(repo_url, tmprepoloc)
    annotation = main.run_pipeline(str(tmprepoloc), level)
    
    try:
        annotation = main.run_pipeline(str(tmprepoloc), level)
        return {"result": json.loads(annotation)}  # drop "location" from the return value
    finally:
        if tmprepoloc.exists():
            shutil.rmtree(tmprepoloc)
from celery import shared_task
from .utils import main
from git import Repo
from pathlib import Path
import json

@shared_task(bind=True)
def run_review_task(self, repo_url):
    tmpname = str(repo_url).replace("https://", "")
    tmpname = Path(tmpname).stem
    
    from django.conf import settings
    BASE_DIR = settings.BASE_DIR
    
    tmprepoloc = BASE_DIR / "annotation" / "utils" / "tmprepo" / tmpname
    annosaveloc = tmprepoloc / f"{tmpname}.json"
    
    Repo.clone_from(repo_url, tmprepoloc)
    main.run_pipeline(str(tmprepoloc), str(annosaveloc))
    
    with open(annosaveloc, "r") as handle:
        return json.load(handle)
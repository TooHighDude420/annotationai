from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .tasks import run_review_task
from linters.linters.py_linter import *
from code_annotation_ai.settings import BASE_DIR
from git import Repo
from pathlib import Path
import shutil

@csrf_exempt
def predict(request):
    if request.method != 'POST':
        return render(request, "send.html")

    repo = request.POST.get('input')
    level = request.POST.get('level')
    
    if "https" not in repo:
        return JsonResponse({"status": "failed", "reason": "no valid repo entered"})

    try:
        tmpname = str(repo).replace("https://", "")
        tmpname = Path(tmpname).stem
        tmprepoloc = BASE_DIR / "annotation" / "utils" / "tmprepo" / tmpname
        annosaveloc = BASE_DIR / "annotation" / "utils" / "tmprepo" / tmpname / f"{tmpname}.json"
        Repo.clone_from(repo, tmprepoloc)
    except Exception as e:
        return JsonResponse({"status": "failed", "reason": str(e)})

    task = run_review_task.delay(repo, level)
    
    return redirect(f"anno:result", task.id)
    
@csrf_exempt
def get_result(request, task_id):
    from celery.result import AsyncResult
    result = AsyncResult(task_id)
    
    if result.state == 'PENDING':
        return JsonResponse({"status": "pending"})
    elif result.state == 'SUCCESS':
        resdict = dict(result.get())
        res = resdict.get("result", None)
        location = resdict.get("location", None)
        
        if res is None or location is None:
            raise ValueError("result or location is not set")
        else:
            shutil.rmtree(location)
            return JsonResponse({"status": "complete", "result": res})
    elif result.state == 'FAILURE':
        return JsonResponse({"status": "failed", "reason": str(result.info)})
    else:
        return JsonResponse({"status": result.state})
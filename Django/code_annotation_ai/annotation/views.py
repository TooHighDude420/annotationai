from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .tasks import run_review_task
from linters.linters.py_linter import *
from code_annotation_ai.settings import BASE_DIR
from .utils import main
from git import Repo
from pathlib import Path

import ollama
import json
import os

# Initialize the Ollama client
ollama_client = ollama.Client()

@csrf_exempt
def predict(request):
    if request.method != 'POST':
        return render(request, "send.html")

    repo = request.POST.get('input')
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

    # Fire and forget — returns task ID instantly
    task = run_review_task.delay(str(tmprepoloc), str(annosaveloc))
    
    return JsonResponse({"status": "processing", "task_id": task.id, "result_link":f"annotationai-production.up.railway.app/test/result/{task.id}"})

@csrf_exempt
def get_result(request, task_id):
    from celery.result import AsyncResult
    result = AsyncResult(task_id)
    
    if result.state == 'PENDING':
        return JsonResponse({"status": "pending"})
    elif result.state == 'SUCCESS':
        return JsonResponse({"status": "complete", "result": result.get()})
    elif result.state == 'FAILURE':
        return JsonResponse({"status": "failed", "reason": str(result.info)})
    else:
        return JsonResponse({"status": result.state})
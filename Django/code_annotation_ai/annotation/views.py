from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
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

    # Get input (if needed)
    repo = request.POST.get('input')
    
    if "https" not in repo:
        return JsonResponse({"status":"failed", "reason":"no valid repo enterd"})
    
    try:
        tmpname = str(repo).replace("https://", "")
        tmpname = Path(tmpname).stem
        tmprepoloc = BASE_DIR / "annotation" / "utils"/ "tmprepo" / tmpname
        annosaveloc = BASE_DIR / "annotation" / "utils"/ "tmprepo" / tmpname / f"{tmpname}.json"
        repo = Repo.clone_from(repo, tmprepoloc)
    except Exception as e:
        print(f"repo clone failed: {e}")
        
    print("pipline called")
        
    main.run_pipeline(str(tmprepoloc), str(annosaveloc))
    
    with open(annosaveloc, "r") as handle:
        tmpcont = json.load(handle)

    return JsonResponse(tmpcont)
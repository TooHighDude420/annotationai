"""
Multi-Agent Code Review Pipeline
----------------------------------
3 sequential agents powered by Claude via OpenRouter:

  Agent 1 → Code Review     (syntax, lint, style, best practices)
  Agent 2 → Security Expert (vulnerabilities, OWASP, secrets)
  Agent 3 → Project Context (architecture, consistency, big picture)

Each agent receives the code + findings from previous agents.

Setup:
    1. Create a .env file with: OPENROUTER_API_KEY=sk-or-...
    2. python -m venv venv && source venv/bin/activate
    3. pip install -r requirements.txt
    4. python multi_agent_review.py --repo ./my-project
       python multi_agent_review.py --file ./main.py
"""

import os
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

load_dotenv()

# ─────────────────────────────────────────────
# LLM — Claude via OpenRouter
# ─────────────────────────────────────────────

llm = ChatOpenAI(
    model="anthropic/claude-haiku-4.5",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    openai_api_base="https://openrouter.ai/api/v1",
    max_tokens=8192,
)

# ─────────────────────────────────────────────
# AGENT PROMPTS
# ─────────────────────────────────────────────

CODE_REVIEW_PROMPT = """
You are an expert code reviewer specializing in Python syntax, lint errors, and best practices.
Return output **only in JSON**, strictly following this schema:

{
    "agent": "code_review",
    "issues": [
        {
            "file": "<file where error occurred>",
            "line": "<line number>",
            "type": "<syntax | lint | style | performance | best_practice>",
            "severity": "<critical | high | medium | low>",
            "original_code": "<the code that caused the error>",
            "suggested_fix": "<corrected code>",
            "explanation": [
                "<explanation 1>",
                "<explanation 2>",
                "<explanation 3>"
            ]
        }
    ],
    "summary": "<overall code quality summary in 2-3 sentences>"
}

Rules:
- Only return valid JSON. No text outside the JSON.
- At least 3 explanations per issue.
- Cover: unused imports, naming conventions, type hints, docstrings, complexity.
"""

SECURITY_PROMPT = """
You are a senior application security engineer.
You will receive code AND the findings from a code review agent before you.
Use both to inform your security analysis.
Return output **only in JSON**, strictly following this schema:

{
    "agent": "security_expert",
    "vulnerabilities": [
        {
            "file": "<file>",
            "line": "<line number>",
            "type": "<injection | hardcoded_secret | broken_auth | xss | path_traversal | insecure_deserialization | other>",
            "severity": "<critical | high | medium | low | informational>",
            "owasp_category": "<OWASP Top 10 category or null>",
            "original_code": "<vulnerable code>",
            "suggested_fix": "<secure replacement>",
            "explanation": [
                "<what the vulnerability is>",
                "<how it could be exploited>",
                "<why the fix resolves it>"
            ]
        }
    ],
    "risk_score": "<1-10>",
    "summary": "<security posture summary in 2-3 sentences>"
}

Rules:
- Only return valid JSON. No text outside the JSON.
- If no issues found return empty vulnerabilities array with clean summary.
- Check for: SQL injection, hardcoded credentials, insecure randomness,
  path traversal, command injection, unvalidated input, exposed secrets.
"""

CONTEXT_PROMPT = """
You are a senior software architect who understands entire projects holistically.
You will receive the code AND findings from both the code review and security agents before you.
Use all of this to give a complete big-picture assessment.
Return output **only in JSON**, strictly following this schema:

{
    "agent": "project_context",
    "project_overview": {
        "name": "<inferred project name>",
        "purpose": "<what this project does in 1-2 sentences>",
        "architecture": "<monolith | microservice | library | cli | api | other>",
        "tech_stack": ["<detected technologies>"],
        "entry_points": ["<main entry files>"]
    },
    "architectural_issues": [
        {
            "file": "<file>",
            "issue": "<architectural concern>",
            "severity": "<critical | high | medium | low>",
            "recommendation": "<what to do instead>"
        }
    ],
    "consistency_issues": [
        {
            "description": "<inconsistency across files>",
            "files_affected": ["<file1>", "<file2>"],
            "recommendation": "<how to make consistent>"
        }
    ],
    "missing_components": ["<tests | docs | error handling | logging | etc>"],
    "strengths": ["<things done well>"],
    "summary": "<holistic project assessment in 3-4 sentences>"
}

Rules:
- Only return valid JSON. No text outside the JSON.
- Think across ALL files — cross-file big-picture analysis only.
- revieuw the code on level based on the following:
    - junior MBO Software Developer year 1
    - medior MBO Software Developer year 2
    - medior MBO Software Developer year 3
    - senior MBO Software Developer year 4
- give a estimate based on educational level what a rating of 1 / 10 based on level would be
"""

# ─────────────────────────────────────────────
# FILE LOADER
# ─────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".yaml", ".yml", ".toml", ".env.example", ".php", ".html"}
IGNORE_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}

def load_files(path: str) -> dict:
    files = {}
    p = Path(path)

    if p.is_file():
        files[str(p)] = p.read_text(errors="ignore")
        return files

    for root, dirs, filenames in os.walk(p):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for fname in filenames:
            fpath = Path(root) / fname
            if fpath.suffix in SUPPORTED_EXTENSIONS:
                try:
                    files[str(fpath)] = fpath.read_text(errors="ignore")
                except Exception:
                    pass

    return files

def format_files(files: dict) -> str:
    blocks = []
    for path, content in files.items():
        blocks.append(f"### FILE: {path}\n```\n{content}\n```")
    return "\n\n".join(blocks)

# ─────────────────────────────────────────────
# AGENT RUNNER
# ─────────────────────────────────────────────

def run_agent(name: str, system_prompt: str, user_message: str) -> dict:
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message)
    ])

    raw = response.content.strip()

    # Strip markdown fences if model adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Response was likely truncated by token limit — attempt to salvage it
        # by finding the last complete object in the issues/vulnerabilities array
        try:
            # Find the last complete closing brace of an array item
            last_valid = raw.rfind('        }')
            if last_valid != -1:
                truncated = raw[:last_valid + 9]  # include the closing brace
                # Close open array and object
                repaired = truncated + '\n    ],\n    "summary": "Response was truncated due to token limit. Showing partial results."\n}'
                return json.loads(repaired)
        except Exception:
            pass
        return {"agent": name, "error": "JSON truncated — increase max_tokens or reduce codebase size", "raw": raw[:500] + "..."}

# ─────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────

def run_pipeline(path: str, level:str) -> str:
    print(Panel(f"Multi-Agent Code Review\n{path}"))

    # Load files
    files = load_files(path)
    if not files:
        return {}

    code_context = format_files(files)  # used by security + context agents

    results = {
        "files_reviewed": list(files.keys()),
        "agents": {}
    }

    # ── Agent 1: Code Review — batched per file ──
    all_issues = []
    for filepath, content in files.items():
        filename = filepath.split(os.sep)[-1]
        file_context = f"### FILE: {filepath}\n```\n{content}\n```"
        result = run_agent(
            f"Code Review Agent [{filename}]",
            CODE_REVIEW_PROMPT,
            f"Review this file:\n\n{file_context}"
        )
        if "issues" in result:
            all_issues.extend(result["issues"])
        elif "error" in result:
            print(f"{filename}: {result['error']}")

    agent1 = {
        "agent": "code_review",
        "issues": all_issues,
        "summary": f"Batched review complete. Found {len(all_issues)} issue(s) across {len(files)} file(s)."
    }
    results["agents"]["code_review"] = agent1

    # ── Agent 2: Security — receives code + agent 1 findings ──
    agent2 = run_agent(
        "Security Expert Agent",
        SECURITY_PROMPT,
        f"Code:\n\n{code_context}\n\n---\nCode review findings:\n{json.dumps(agent1, indent=2)}"
    )
    results["agents"]["security_expert"] = agent2

    # ── Agent 3: Context — receives code + agent 1 + agent 2 findings ──
    agent3 = run_agent(
        "Project Context Agent",
        CONTEXT_PROMPT,
        f"Code:\n\n{code_context}\n\n---\nCode review findings:\n{json.dumps(agent1, indent=2)}\n\n---\nSecurity findings:\n{json.dumps(agent2, indent=2)}\n\n---\nLevel:\n{level}"
    )
    results["agents"]["project_context"] = agent3

    # ── Print summaries ──
    print("\nReview complete\n")
    for key, data in results["agents"].items():
        if "error" in data:
            print(f"{key}: {data['error']}")
            
    # ── Return output ──
    retres = json.dumps(results)

    return retres

# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent Code Review Pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--repo", type=str, help="Path to a directory or repo")
    group.add_argument("--file", type=str, help="Path to a single file")

    args = parser.parse_args()
    run_pipeline(args.repo or args.file)
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
from rich.panel import Panel

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
You are a code reviewer and teacher giving feedback to a student at the level specified by the user.
Tailor the depth, terminology, and expectations strictly to that educational level.

Level guidance:
- year 1: Focus only on basics — unused imports, naming (snake_case), unnecessary whitespace, obvious logic errors.
          Do NOT mention type hints, docstrings, module guards, dependency injection, or design patterns.
          Keep explanations simple, encouraging, and concrete. Max 3-4 issues per file.
- year 2: Add PEP 8 style consistency, simple refactoring, basic error handling.
          One brief mention of docstrings is fine. Still no advanced patterns.
- year 3: Include DRY violations, basic error handling, function responsibilities, simple code structure.
- year 4: Full professional review — type hints, architecture, testability, docstrings, all best practices.

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
                "<main explanation — what is wrong and why, in terms the student can understand>",
                "<how to fix it or what to do instead>",
                "<why this matters at their level>"
            ]
        }
    ],
    "summary": "<overall code quality summary in 2-3 sentences, encouraging in tone for lower levels>"
}

Rules:
- Only return valid JSON. No text outside the JSON.
- Exactly 3 explanations per issue.
- Only raise issues that are relevant and teachable at the student's level.
- Be encouraging — acknowledge what the student did well where possible.
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
You are a software teacher reviewing a student's project holistically.
You will receive the code AND findings from both the code review and security agents before you.
The student's educational level is provided — calibrate ALL feedback and ratings to that level.

Level definitions:
- "year 1": Just started programming. Assess only: does the code run, is it readable, are basics followed?
             A 7/10 at year 1 means the code works and is reasonably readable. Do NOT penalise for missing
             docstrings, type hints, tests, logging, or architecture. These are not year 1 topics.
- "year 2": Some experience. Begins to learn about structure, basic error handling, consistent style.
- "year 3": Growing professional. Can be expected to know DRY, basic patterns, error handling, some testing.
- "year 4": Near-professional. Full best practices apply.

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
            "issue": "<concern — only include if relevant at the student's level>",
            "severity": "<critical | high | medium | low>",
            "recommendation": "<concrete, actionable advice in terms the student can understand>"
        }
    ],
    "consistency_issues": [
        {
            "description": "<inconsistency across files — only relevant ones for the level>",
            "files_affected": ["<file1>", "<file2>"],
            "recommendation": "<how to make consistent, explained simply>"
        }
    ],
    "missing_components": ["<only list things that are expected at this educational level>"],
    "strengths": ["<specific things the student did well — be concrete and generous>"],
    "summary": "<holistic assessment in 3-4 sentences. Encouraging tone. Mention what works before what to improve.>",
    "educational_level_assessment": {
        "level": "<the level provided>",
        "rating": "<X/10 — calibrated to what is expected at this level, not professional standards>",
        "justification": "<explain the rating relative to peers at the same level, not professional developers>"
    }
}

Rules:
- Only return valid JSON. No text outside the JSON.
- Think across ALL files — cross-file analysis only.
- NEVER penalise a year 1 or year 2 student for missing type hints, docstrings, unit tests, logging, or architectural patterns.
- The rating must reflect the student's level. A working year 1 project with reasonable code is a 6-7, not a 3.
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

def run_pipeline(path: str, level: str) -> str:
    print(Panel(f"Multi-Agent Code Review\n{path}"))

    # Load files
    files = load_files(path)
    if not files:
        return json.dumps({})

    code_context = format_files(files)  # used by security + context agents

    results = {
        "files_reviewed": list(files.keys()),
        "agents": {}
    }

    # ── Agent 1: Code Review — per file, level-aware ──
    all_issues = []
    for filepath, content in files.items():
        filename = filepath.split(os.sep)[-1]
        file_context = f"### FILE: {filepath}\n```\n{content}\n```"
        result = run_agent(
            f"Code Review Agent [{filename}]",
            CODE_REVIEW_PROMPT,
            f"Student level: {level}\n\nReview this file:\n\n{file_context}"
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
    parser.add_argument(
        "--level",
        type=str,
        choices=["year 1", "year 2", "year 3", "year 4"],
        default="year 1",
        help="Educational level of the student being reviewed (default: year 1)"
    )

    args = parser.parse_args()
    run_pipeline(args.repo or args.file, args.level)
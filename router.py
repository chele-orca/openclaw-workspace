#!/usr/bin/env python3
"""
Intelligent Model Router
========================
Routes tasks through a local Ollama model with confidence gating and self-validation.

Usage:
    python router.py "your task here"
    
Module:
    from router import route_task
    result = route_task("your task here")
"""

import json
import sys
import urllib.request
import urllib.error
from typing import Any

OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"
MODEL = "deepseek-r1:14b-qwen-distill-q8_0"
TIMEOUT = 300  # seconds per API call
CONFIDENCE_THRESHOLD = 7


def _chat(messages: list[dict[str, str]], temperature: float = 0.3) -> str:
    """Send a chat completion request to Ollama. Returns the assistant message content."""
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _parse_json_from(text: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from model output."""
    # Try the whole string first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Look for ```json fences or bare { ... }
    for start_tok in ("```json", "```", "{"):
        idx = text.find(start_tok)
        if idx == -1:
            continue
        fragment = text[idx:]
        if fragment.startswith("```"):
            fragment = fragment.split("\n", 1)[-1].rsplit("```", 1)[0]
        # Find outermost braces
        brace_start = fragment.find("{")
        if brace_start == -1:
            continue
        depth, end = 0, brace_start
        for i, ch in enumerate(fragment[brace_start:], brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        try:
            return json.loads(fragment[brace_start:end])
        except json.JSONDecodeError:
            continue
    return {}


# ── Phase functions ──────────────────────────────────────────────────────────

def _evaluate_confidence(task: str) -> tuple[int, list[str], str]:
    """Phase 1: Ask the model to rate its confidence and define success criteria."""
    messages = [
        {"role": "system", "content": (
            "You are a confidence evaluator. Given a task, respond with ONLY a JSON object:\n"
            '{"confidence": <1-10>, "criteria": ["criterion 1", ...], "reasoning": "..."}\n'
            "confidence = how confident you are you can solve this well (1=no idea, 10=trivial).\n"
            "criteria = concrete, checkable success criteria for a good solution.\n"
            "reasoning = brief explanation of your rating."
        )},
        {"role": "user", "content": task},
    ]
    raw = _chat(messages, temperature=0.2)
    parsed = _parse_json_from(raw)
    score = int(parsed.get("confidence", 1))
    criteria = parsed.get("criteria", [])
    reasoning = parsed.get("reasoning", raw[:300])
    return max(1, min(10, score)), criteria, reasoning


def _attempt_task(task: str, criteria: list[str]) -> str:
    """Phase 2: Have the model solve the task."""
    criteria_text = "\n".join(f"  - {c}" for c in criteria) if criteria else "  (none specified)"
    messages = [
        {"role": "system", "content": (
            "You are a helpful expert assistant. Solve the following task thoroughly.\n"
            f"Success criteria to meet:\n{criteria_text}"
        )},
        {"role": "user", "content": task},
    ]
    return _chat(messages, temperature=0.3)


def _validate_solution(task: str, solution: str, criteria: list[str]) -> bool:
    """Phase 3: Ask the model to validate its own solution against the criteria."""
    criteria_text = "\n".join(f"  - {c}" for c in criteria) if criteria else "  (none)"
    messages = [
        {"role": "system", "content": (
            "You are a strict validator. Given a task, its solution, and success criteria, "
            "determine if the solution passes ALL criteria.\n"
            'Respond with ONLY a JSON object: {"pass": true/false, "reasoning": "..."}'
        )},
        {"role": "user", "content": (
            f"TASK:\n{task}\n\n"
            f"SOLUTION:\n{solution}\n\n"
            f"SUCCESS CRITERIA:\n{criteria_text}"
        )},
    ]
    raw = _chat(messages, temperature=0.1)
    parsed = _parse_json_from(raw)
    return bool(parsed.get("pass", False))


# ── Main entry point ─────────────────────────────────────────────────────────

def route_task(task: str) -> dict[str, Any]:
    """
    Route a task through confidence evaluation, attempt, and validation.

    Returns a dict with: confidence_score, success_criteria, solution,
    passed_validation, fallback_needed, reasoning.
    """
    result: dict[str, Any] = {
        "confidence_score": 0,
        "success_criteria": [],
        "solution": None,
        "passed_validation": False,
        "fallback_needed": False,
        "reasoning": "",
    }

    # Phase 1: Confidence evaluation
    try:
        score, criteria, reasoning = _evaluate_confidence(task)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        result["reasoning"] = f"Confidence evaluation failed: {e}"
        result["fallback_needed"] = True
        return result

    result["confidence_score"] = score
    result["success_criteria"] = criteria
    result["reasoning"] = reasoning

    # Decision gate
    if score < CONFIDENCE_THRESHOLD:
        result["fallback_needed"] = True
        result["reasoning"] += f" | Score {score} < threshold {CONFIDENCE_THRESHOLD}; falling back."
        return result

    # Phase 2: Attempt
    try:
        solution = _attempt_task(task, criteria)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        result["reasoning"] += f" | Attempt failed: {e}"
        result["fallback_needed"] = True
        return result

    result["solution"] = solution

    # Phase 3: Validation
    try:
        passed = _validate_solution(task, solution, criteria)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        result["reasoning"] += f" | Validation failed: {e}"
        result["passed_validation"] = False
        return result

    result["passed_validation"] = passed
    if not passed:
        result["reasoning"] += " | Solution did not pass self-validation."

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} \"your task here\"", file=sys.stderr)
        sys.exit(1)

    task_input = " ".join(sys.argv[1:])
    output = route_task(task_input)
    print(json.dumps(output, indent=2, ensure_ascii=False))

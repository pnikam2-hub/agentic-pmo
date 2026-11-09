"""LLM integration — abstracts OpenAI, Anthropic, OpenRouter behind one interface."""
import os
import json
from typing import Optional
import httpx

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")

OPENAI_BASE = "https://api.openai.com/v1"
ANTHROPIC_BASE = "https://api.anthropic.com/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def _resolve_base_url() -> str:
    if LLM_BASE_URL:
        return LLM_BASE_URL.rstrip("/")
    if LLM_PROVIDER == "anthropic":
        return ANTHROPIC_BASE
    if LLM_PROVIDER == "openrouter":
        return OPENROUTER_BASE
    return OPENAI_BASE


async def chat_completion(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Call any LLM with an OpenAI-compatible chat completions endpoint.

    Anthropic messages are automatically translated to OpenAI format
    via the Anthropic SDK if needed — but for simplicity we use the
    OpenAI-compatible layer most providers support.
    """
    base = _resolve_base_url()
    model = model or LLM_MODEL
    api_key = LLM_API_KEY

    if not api_key:
        return _fallback_plan(messages)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if LLM_PROVIDER == "openrouter":
        headers["HTTP-Referer"] = "https://agenticpmo.local"
        headers["X-Title"] = "Agentic PMO"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # DeepSeek enables chain-of-thought by default, and with thinking on, the
    # reasoning tokens can consume the whole max_tokens budget leaving
    # choices[0].message.content empty. Disable it unless asked otherwise.
    # Other providers are left untouched (they reject unknown fields).
    thinking = os.getenv("LLM_THINKING", "").strip().lower()
    if thinking in ("enabled", "disabled"):
        payload["thinking"] = {"type": thinking}
    elif "deepseek" in base.lower():
        payload["thinking"] = {"type": "disabled"}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"[llm] {model} at {base} failed: {exc}", flush=True)
        return _fallback_plan(messages, error=str(exc))


def _fallback_plan(messages: list[dict], error: str = "") -> str:
    """When no LLM is configured, return rule-based output so the tool still
    works. The user gets a working PMO; they just need to add an API key
    for the AI agents to produce smarter outputs."""
    last = messages[-1]["content"] if messages else ""
    return json.dumps({
        "note": "LLM not configured — set LLM_API_KEY in .env for AI-powered planning.",
        "fallback_reason": error or "no API key configured",
        "template_response": (
            "Based on the project brief, here is a structured plan:\n\n"
            "Phase 1: Discovery & Requirements\n"
            "Phase 2: Design & Architecture\n"
            "Phase 3: Implementation\n"
            "Phase 4: Testing & Validation\n"
            "Phase 5: Deployment & Handover\n\n"
            "Set an LLM_API_KEY in your .env file to enable AI-generated plans."
        ),
    })


async def generate_plan(project_name: str, goal: str, description: str) -> str:
    """Generate a project plan from a brief."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior project manager and AI agent. Given a project name, goal, "
                "and description, produce a detailed project plan with:\n"
                "1. A clear breakdown of phases\n"
                "2. Specific, actionable tasks with estimated hours\n"
                "3. Dependencies between tasks\n"
                "4. Key milestones with target dates (relative, e.g. 'Week 2')\n"
                "5. Resource suggestions\n\n"
                "Return your output as a JSON object with keys: "
                "'phases' (list of phase objects with name, tasks list), "
                "'milestones', 'total_estimated_hours', 'summary'.\n"
                "Each task should have: title, description, estimated_hours, priority "
                "(low/medium/high/critical), dependencies (list of titles from other tasks)."
            ),
        },
        {
            "role": "user",
            "content": f"Project: {project_name}\nGoal: {goal}\nDescription: {description}\n\nGenerate a detailed execution plan.",
        },
    ]
    return await chat_completion(messages)


async def monitor_tasks(project_name: str, tasks_summary: str) -> str:
    """Analyse task status and flag issues."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI project monitor. Review the task status summary and identify:\n"
                "1. Tasks at risk of delay\n"
                "2. Blocked dependencies\n"
                "3. Resource bottlenecks\n"
                "4. Overdue items\n"
                "5. Recommended actions\n\n"
                "Return JSON with keys: 'risks' (list), 'blocked_dependencies' (list), "
                "'recommendations' (list), 'health_score' (0-100), 'summary'."
            ),
        },
        {
            "role": "user",
            "content": f"Project: {project_name}\nTasks: {tasks_summary}\n\nAnalyse and report issues.",
        },
    ]
    return await chat_completion(messages)


async def alert_on_anomaly(project_name: str, anomaly_data: str) -> str:
    """Assess an anomaly and generate alert recommendation."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI alerting agent. Assess the situation and determine:\n"
                "1. Severity (info/warning/critical)\n"
                "2. What triggered it\n"
                "3. Recommended response\n"
                "4. Impact on timeline\n\n"
                "Return JSON with keys: 'severity', 'trigger', 'recommended_response', "
                "'timeline_impact', 'summary'."
            ),
        },
        {
            "role": "user",
            "content": f"Project: {project_name}\nSituation: {anomaly_data}\n\nAssess and alert.",
        },
    ]
    return await chat_completion(messages)

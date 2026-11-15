"""Model routing. Two classes (cheap, strong), one config file, a cache in front, a mock mode behind.

    complete('classify', 'cheap', system, prompt, cache_parts=[filing_hash])

Order of work: cache hit -> return it (no cost). Mock mode -> return saved sample output.
Otherwise call the model, store the result in the cache, log tokens.
"""
from __future__ import annotations

import json
import os
import re

from . import config, db
from .cache import cache_get, cache_key, cache_set

PROMPT_VERSION = "v1"   # bump to invalidate every cached model result


def model_for(model_class: str) -> str:
    models = config.settings()["models"]
    if model_class not in ("cheap", "strong"):
        raise ValueError(f"unknown model class: {model_class}")
    return models[model_class]


def is_mock() -> bool:
    if config.env_flag("FINN_MOCK_LLM"):
        return True
    return not os.environ.get("ANTHROPIC_API_KEY")


def _log_call(task, model_class, model, in_tok=0, out_tok=0, cached=False, mock=False) -> None:
    with db.session() as conn:
        conn.execute(
            """INSERT INTO llm_calls(ts, task, model_class, model, input_tokens, output_tokens, cached, mock)
               VALUES (?,?,?,?,?,?,?,?)""",
            (db.now_iso(), task, model_class, model, in_tok, out_tok, int(cached), int(mock)),
        )


def complete(
    task: str,
    model_class: str,
    system: str,
    prompt: str,
    cache_parts=(),
    max_tokens: int | None = None,
    mock_response: str | None = None,
) -> dict:
    """Returns {text, cached, mock, model}. cache_parts should identify the source documents."""
    model = model_for(model_class)
    key = cache_key(PROMPT_VERSION, task, model_class, model, system, prompt, list(cache_parts))

    with db.session() as conn:
        hit = cache_get(conn, key)
    if hit is not None:
        _log_call(task, model_class, model, cached=True)
        return {"text": hit["text"], "cached": True, "mock": False, "model": model}

    if is_mock():
        text = mock_response if mock_response is not None else json.dumps({"mock": True, "task": task})
        _log_call(task, model_class, "mock", mock=True)
        return {"text": text, "cached": False, "mock": True, "model": "mock"}

    import anthropic  # imported late so mock mode needs no key and no network

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens or config.settings()["models"]["max_tokens"],
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
    with db.session() as conn:
        cache_set(conn, key, "llm", {"text": text})
    _log_call(task, model_class, model, resp.usage.input_tokens, resp.usage.output_tokens)
    return {"text": text, "cached": False, "mock": False, "model": model}


def parse_json(text: str):
    """Pull a JSON object or array out of model text, tolerating code fences and chatter."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def usage_summary() -> dict:
    """Totals for the write-up: calls, cache hits, tokens by model class."""
    with db.session() as conn:
        rows = conn.execute(
            """SELECT model_class, COUNT(*) AS calls, SUM(cached) AS cache_hits, SUM(mock) AS mock_calls,
                      SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens
               FROM llm_calls GROUP BY model_class"""
        ).fetchall()
    return {r["model_class"]: dict(r) for r in rows}

"""Shared helpers: Arctic Shift archive access, OpenRouter chat calls, JSONL io."""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
ARCTIC = "https://arctic-shift.photon-reddit.com/api"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
# Fallback key source when OPENROUTER_API_KEY isn't exported (git-ignored).
FALLBACK_ENV = ROOT / ".env"


def openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    if FALLBACK_ENV.exists():
        for line in FALLBACK_ENV.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("OPENROUTER_API_KEY not set")


def http_json(url: str, body: dict | None = None, headers: dict | None = None, timeout: int = 60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "wait-bro-youre-a-bot/0.1", **(headers or {})})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def arctic(path: str, **params) -> list[dict]:
    """GET an Arctic Shift endpoint; retries on its 'slow down' timeouts."""
    url = f"{ARCTIC}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(6):
        try:
            out = http_json(url, timeout=60)
            if out.get("error"):
                raise RuntimeError(out["error"])
            return out.get("data") or []
        except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
            wait = 2 ** attempt
            print(f"  arctic retry {attempt + 1} in {wait}s: {e}")
            time.sleep(wait)
    return []


def chat(
    model: str, system: str, user: str, max_tokens: int = 400, temperature: float = 0.7, reasoning: str | None = None
) -> tuple[str, dict]:
    """One OpenRouter chat call. Returns (text, usage incl. finish_reason). `reasoning` sets effort for thinking models."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "usage": {"include": True},
    }
    if reasoning:
        body["reasoning"] = {"effort": reasoning}
    headers = {"Authorization": f"Bearer {openrouter_key()}"}
    for attempt in range(5):
        try:
            out = http_json(OPENROUTER, body, headers, timeout=180)
            if "error" in out:
                raise RuntimeError(out["error"])
            choice = out["choices"][0]
            usage = {**out.get("usage", {}), "finish_reason": choice.get("finish_reason")}
            return (choice["message"].get("content") or "").strip(), usage
        except (urllib.error.URLError, RuntimeError, TimeoutError, KeyError) as e:
            wait = 2 ** attempt
            print(f"  {model} retry {attempt + 1} in {wait}s: {e}")
            time.sleep(wait)
    raise RuntimeError(f"{model}: gave up")


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")

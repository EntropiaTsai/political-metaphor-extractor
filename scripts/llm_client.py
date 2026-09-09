"""Minimal OpenAI-compatible chat client shared by the pipeline stages.

Standard library only, so the skill runs anywhere Python 3.9+ is available.
Works against any endpoint that speaks /chat/completions: OpenAI, Gemini's
OpenAI-compatible surface, Azure, Ollama, vLLM.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


class LLMError(RuntimeError):
    pass


def load_env_file(path):
    """Read a simple KEY=VALUE .env file without adding a dependency."""
    if not path or not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class LLMClient:
    def __init__(self, cfg, verbose=True):
        self.base_url = cfg["base_url"].rstrip("/")
        self.model = cfg["model"]
        self.temperature = cfg.get("temperature", 0.0)
        self.max_tokens = cfg.get("max_tokens", 4000)
        self.timeout = cfg.get("timeout_seconds", 180)
        self.retries = cfg.get("retries", 3)
        self.retry_backoff = cfg.get("retry_backoff_seconds", 3.0)
        self.extra_body = cfg.get("extra_body") or {}
        self.verbose = verbose

        key_env = cfg.get("api_key_env", "LLM_API_KEY")
        self.api_key = os.environ.get(key_env, "")
        if not self.api_key:
            raise LLMError(
                f"Environment variable {key_env} is not set. Export it or put it in your .env file."
            )

    def _post(self, payload):
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def complete(self, system_prompt, user_prompt, max_tokens=None):
        """Return the raw assistant message text, retrying on transient errors."""
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        payload.update(self.extra_body)

        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                data = self._post(payload)
                choice = data["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise LLMError(
                        "response hit max_tokens and was truncated — raise llm.max_tokens "
                        "or lower the stage batch_size"
                    )
                return choice["message"]["content"]
            except LLMError:
                raise
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:400]
                last_error = f"HTTP {exc.code}: {body}"
                # 4xx other than rate limiting will not fix themselves.
                if exc.code not in (408, 409, 429) and exc.code < 500:
                    break
            except Exception as exc:  # noqa: BLE001 - network layer is broad
                last_error = repr(exc)
            if attempt < self.retries:
                wait = self.retry_backoff * attempt
                if self.verbose:
                    print(f"    retry {attempt}/{self.retries - 1} in {wait:.0f}s ({last_error})", file=sys.stderr)
                time.sleep(wait)
        raise LLMError(f"request failed after {self.retries} attempts: {last_error}")


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def parse_json(text):
    """Parse a model response that should be JSON, tolerating code fences."""
    if not text:
        raise ValueError("empty response")
    cleaned = _FENCE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost braces, which handles stray prose.
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        return json.loads(cleaned[start:end + 1])
    raise ValueError(f"not JSON: {cleaned[:200]}")


def batched(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def load_yaml(path):
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML is required: pip install pyyaml") from exc
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def read_text(path, base=None):
    """Resolve a prompt path relative to the config file when needed."""
    candidate = Path(path)
    if not candidate.is_absolute() and base:
        candidate = Path(base) / candidate
    return candidate.read_text(encoding="utf-8")

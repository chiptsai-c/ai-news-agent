"""Minimal client for the local Ollama server."""
import json
import logging
import re

import httpx

log = logging.getLogger(__name__)
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLM:
    def __init__(self, url: str, model: str, num_thread: int, num_ctx: int):
        self.url, self.model = url.rstrip("/"), model
        self.options = {"num_thread": num_thread, "num_ctx": num_ctx}
        self.think_param = True  # cleared if this model's template rejects the "think" flag
        self.stats = {"calls": 0, "prompt_tokens": 0, "prompt_s": 0.0, "gen_tokens": 0, "gen_s": 0.0}

    def chat(self, system: str, user: str, schema: dict | None = None,
             temperature: float = 0.2, max_tokens: int = 512) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "keep_alive": "30m",
            "options": {**self.options, "temperature": temperature, "num_predict": max_tokens},
        }
        if schema:
            body["format"] = schema
        if self.think_param:
            body["think"] = False  # reasoning tokens are far too slow on CPU
        r = httpx.post(f"{self.url}/api/chat", json=body, timeout=900)
        if r.status_code == 400 and "think" in r.text.lower() and self.think_param:
            log.info("Model does not accept the think flag; continuing without it")
            self.think_param = False
            return self.chat(system, user, schema, temperature, max_tokens)
        r.raise_for_status()
        data = r.json()
        s = self.stats
        s["calls"] += 1
        s["prompt_tokens"] += data.get("prompt_eval_count", 0)
        s["prompt_s"] += data.get("prompt_eval_duration", 0) / 1e9
        s["gen_tokens"] += data.get("eval_count", 0)
        s["gen_s"] += data.get("eval_duration", 0) / 1e9
        return THINK_RE.sub("", data["message"]["content"]).strip()

    def chat_json(self, system: str, user: str, schema: dict, **kw) -> dict:
        for attempt in range(2):
            try:
                return json.loads(self.chat(system, user, schema, **kw))
            except json.JSONDecodeError:
                log.info("Invalid JSON from model (attempt %d)", attempt + 1)
        raise ValueError("model did not return valid JSON")

    def speed(self) -> str:
        s = self.stats
        pp = s["prompt_tokens"] / s["prompt_s"] if s["prompt_s"] else 0
        tg = s["gen_tokens"] / s["gen_s"] if s["gen_s"] else 0
        return (f"{s['calls']} calls, read {s['prompt_tokens']} tok @ {pp:.1f} tok/s, "
                f"wrote {s['gen_tokens']} tok @ {tg:.1f} tok/s")

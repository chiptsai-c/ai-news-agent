"""Cheap, LLM-free narrowing so the slow local model only reads promising items."""
import re
import time

from .models import Item

AI_RE = re.compile(
    r"\b(AI|A\.I\.|AGI|LLMs?|GPT[-\w]*|ChatGPT|OpenAI|Anthropic|Claude|Gemini|DeepMind|Llama|Qwen|Mistral|"
    r"DeepSeek|Grok|xAI|Copilot|machine learning|neural|chatbots?|agents?|agentic|transformers?|"
    r"diffusion|Nvidia|GPUs?|inference|fine-?tun\w*|open-?weights?|reasoning model|multimodal)\b",
    re.IGNORECASE,
)


def recent(items: list[Item], lookback_hours: float) -> list[Item]:
    """Drop old items (some feeds return their whole archive) and off-topic items from general feeds."""
    cutoff = time.time() - lookback_hours * 3600
    return [it for it in items
            if (it.published is None or it.published >= cutoff)
            and (it.ai_only or AI_RE.search(f"{it.title} {it.lead}"))]


def rank(items: list[Item], lookback_hours: float, limit: int) -> list[Item]:
    """Keep the `limit` most promising items: source weight, AI-keyword density, freshness."""
    now = time.time()
    kept = []
    for it in items:
        hits = len(AI_RE.findall(f"{it.title} {it.lead}"))
        age_h = (now - it.published) / 3600 if it.published else lookback_hours / 2
        rank = it.weight * (1 + 0.15 * min(hits, 5)) * (1.5 - 0.5 * min(age_h / lookback_hours, 1))
        kept.append((rank, it))
    kept.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in kept[:limit]]

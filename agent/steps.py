"""The three LLM steps: triage, summarise, digest."""
import logging
import re
from pathlib import Path

from .llm import LLM
from .models import Item

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

CATEGORIES = ["Models & Releases", "Research", "Products & Tools", "Business & Funding",
              "Policy & Safety", "Open Source", "Other"]

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "reason": {"type": "string", "maxLength": 120},
        "score": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["category", "reason", "score"],
}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
        "why_it_matters": {"type": "string"},
    },
    "required": ["headline", "bullets", "why_it_matters"],
}


SAME_SCHEMA = {"type": "object", "properties": {"same": {"type": "boolean"}}, "required": ["same"]}

GENERIC = {"openai", "google", "anthropic", "model", "models", "about", "their", "which", "would", "could",
           "after", "there", "these", "where", "being", "launches", "adds", "using", "people", "today",
           "with", "from", "that", "this", "will", "have", "more", "into", "your", "what", "says", "open",
           "chatgpt", "agent", "agents", "new", "release", "releases", "launch", "here", "just", "over"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower()) if w not in GENERIC}


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def triage(llm: LLM, items: list[Item]) -> None:
    system = _prompt("triage")
    for n, it in enumerate(items, 1):
        try:
            r = llm.chat_json(system, f"Source: {it.source}\nTitle: {it.title}\nLead: {it.lead}",
                              TRIAGE_SCHEMA, max_tokens=120)
            it.score, it.category, it.reason = int(r["score"]), r["category"], r["reason"]
        except Exception as e:
            log.warning("  triage failed for %r: %s", it.title, e)
        log.info("  [%2d/%d] %2d  %s", n, len(items), it.score, it.title[:90])


def merge_duplicates(llm: LLM, items: list[Item]) -> list[Item]:
    """Collapse items about the same event into one (highest score wins; others go to `.also`).

    `items` must be sorted best-first. Code proposes candidate pairs that share an uncommon
    word; the LLM then answers a simple yes/no per pair, which a small model does reliably.
    """
    title_w = [_words(i.title) for i in items]
    all_w = [t | _words(i.lead) for t, i in zip(title_w, items)]
    df: dict[str, int] = {}
    for ws in all_w:
        for w in ws:
            df[w] = df.get(w, 0) + 1
    rare = {w for w, c in df.items() if c <= 4}

    parent = list(range(len(items)))  # union-find: parent index is always the better-ranked item

    def root(n: int) -> int:
        while parent[n] != n:
            n = parent[n]
        return n

    system = _prompt("cluster")
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            if root(a) == root(b):
                continue
            shared_title = title_w[a] & title_w[b] & rare
            shared_all = all_w[a] & all_w[b] & rare
            if not shared_title and len(shared_all) < 2:
                continue
            A, B = items[a], items[b]
            q = (f"Item A [{A.source}]: {A.title}\n{A.lead[:300]}\n\n"
                 f"Item B [{B.source}]: {B.title}\n{B.lead[:300]}\n\nSame news event?")
            try:
                if llm.chat_json(system, q, SAME_SCHEMA, max_tokens=20)["same"]:
                    ra, rb = root(a), root(b)
                    parent[max(ra, rb)] = min(ra, rb)
                    log.info("  duplicate: %r -> %r", B.title[:60], A.title[:60])
            except Exception as e:
                log.warning("  duplicate check failed: %s", e)

    out = []
    for n, it in enumerate(items):
        r = root(n)
        if r == n:
            out.append(it)
        else:
            items[r].also.append(it)
    return out


def summarise(llm: LLM, items: list[Item]) -> None:
    system = _prompt("summarise")
    for n, it in enumerate(items, 1):
        try:
            it.summary = llm.chat_json(system, f"Title: {it.title}\nSource: {it.source}\n\nArticle text:\n{it.text}",
                                       SUMMARY_SCHEMA, max_tokens=350)
        except Exception as e:
            log.warning("  summary failed for %r: %s", it.title, e)
            it.summary = {"headline": it.title, "bullets": [it.lead[:300]], "why_it_matters": it.reason}
        log.info("  [%2d/%d] %s", n, len(items), it.summary["headline"][:90])


def digest(llm: LLM, items: list[Item]) -> str:
    stories = "\n".join(f"{n}. {i.summary['headline']} — {i.summary['why_it_matters']}"
                        for n, i in enumerate(items, 1))
    return llm.chat(_prompt("digest"), stories, temperature=0.3, max_tokens=300)

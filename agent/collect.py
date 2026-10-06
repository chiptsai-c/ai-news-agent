import calendar
import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import feedparser
import httpx

from .models import Item

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ai-news-agent/1.0 (personal digest)"
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean(text: str, limit: int = 500) -> str:
    text = WS_RE.sub(" ", html.unescape(TAG_RE.sub(" ", text or ""))).strip()
    return text[:limit]


def _fetch(url: str, retries: int = 1) -> httpx.Response:
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
        r.raise_for_status()
        return r
    except httpx.TransportError:
        if retries:
            return _fetch(url, retries - 1)
        raise


def _rss(src: dict) -> list[Item]:
    feed = feedparser.parse(_fetch(src["url"]).content)
    items = []
    for e in feed.entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        link, title = e.get("link"), clean(e.get("title", ""), 300)
        if not link or not title:
            continue
        items.append(Item(
            url=link, title=title, source=src["name"],
            published=calendar.timegm(t) if t else None,
            lead=clean(e.get("summary", "")),
            weight=src.get("weight", 1.0), ai_only=src.get("ai_only", True),
        ))
    return items


def _hf_papers(src: dict) -> list[Item]:
    items = []
    for p in _fetch(src["url"]).json():
        paper = p.get("paper", {})
        if paper.get("upvotes", 0) < src.get("min_upvotes", 0):
            continue
        ts = p.get("publishedAt") or paper.get("publishedAt")
        items.append(Item(
            url=f"https://huggingface.co/papers/{paper['id']}",
            title=clean(paper.get("title", ""), 300), source=src["name"],
            published=datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if ts else None,
            lead=clean(paper.get("summary", "")),
            weight=src.get("weight", 1.0), ai_only=True,
        ))
    return items


def _hn(src: dict) -> list[Item]:
    """Hacker News stories via the Algolia search API (query + min points set in sources.yaml)."""
    since = int(datetime.now().timestamp()) - 2 * 86400
    url = (f"https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=100"
           f"&query={src.get('query', '')}&numericFilters=points>={src.get('min_points', 100)},created_at_i>{since}")
    items = []
    for h in _fetch(url).json()["hits"]:
        items.append(Item(
            url=h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
            title=clean(h.get("title", ""), 300), source=src["name"],
            published=float(h["created_at_i"]), lead=f"{h.get('points', 0)} points on Hacker News",
            weight=src.get("weight", 1.0), ai_only=src.get("ai_only", False),
        ))
    return items


FETCHERS = {"rss": _rss, "hf_papers": _hf_papers, "hn": _hn}


def _one(src: dict) -> list[Item]:
    try:
        items = FETCHERS[src.get("type", "rss")](src)
        log.info("  %-26s %3d items", src["name"], len(items))
        return items
    except Exception as e:
        log.warning("  %-26s FAILED: %s", src["name"], e)
        return []


def collect(sources: list[dict]) -> list[Item]:
    with ThreadPoolExecutor(max_workers=6) as ex:
        return [i for batch in ex.map(_one, sources) for i in batch]

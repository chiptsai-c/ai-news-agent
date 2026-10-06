"""SQLite memory: which items were already processed, plus their scores/summaries."""
import difflib
import json
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Item

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    url TEXT PRIMARY KEY,
    title TEXT, norm_title TEXT, source TEXT,
    published REAL, seen_at REAL,
    score INTEGER, category TEXT, reason TEXT,
    summary TEXT, digest_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_seen ON items(seen_at);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def norm_url(url: str) -> str:
    s = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(s.query) if not k.lower().startswith(("utm_", "ref", "fbclid", "gclid"))]
    return urlunsplit((s.scheme.lower(), s.netloc.lower().removeprefix("www."), s.path.rstrip("/"), urlencode(q), ""))


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def filter_new(conn: sqlite3.Connection, items: list[Item], days: int = 3) -> list[Item]:
    """Drop items seen before (same URL) and near-duplicate titles (same story, other outlet)."""
    seen_urls = {r[0] for r in conn.execute("SELECT url FROM items")}
    titles = [r[0] for r in conn.execute("SELECT norm_title FROM items WHERE seen_at > ?", (time.time() - days * 86400,))]
    out = []
    for it in items:
        it.url = norm_url(it.url)
        nt = norm_title(it.title)
        if it.url in seen_urls or any(difflib.SequenceMatcher(None, nt, t).ratio() > 0.85 for t in titles):
            continue
        seen_urls.add(it.url)
        titles.append(nt)
        out.append(it)
    return out


def save(conn: sqlite3.Connection, items: list[Item], digest_date: str | None = None) -> None:
    now = time.time()
    conn.executemany(
        "INSERT OR REPLACE INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(i.url, i.title, norm_title(i.title), i.source, i.published, now, i.score, i.category,
          i.reason, json.dumps(i.summary) if i.summary else None,
          digest_date if i.summary else None) for i in items],
    )
    conn.commit()

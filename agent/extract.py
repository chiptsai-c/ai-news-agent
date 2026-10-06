import logging
from concurrent.futures import ThreadPoolExecutor

import httpx
import trafilatura

from .collect import UA
from .models import Item

log = logging.getLogger(__name__)


def _extract(it: Item, max_chars: int) -> None:
    try:
        r = httpx.get(it.url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
        r.raise_for_status()
        text = trafilatura.extract(r.text, include_comments=False, include_tables=False) or ""
    except Exception as e:
        log.info("  extract failed (%s): %s", e.__class__.__name__, it.url)
        text = ""
    # Fall back to the feed's lead if the page is paywalled/blocked/too short.
    it.text = (text if len(text) > len(it.lead) else it.lead)[:max_chars]


def extract_all(items: list[Item], max_chars: int) -> None:
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(lambda i: _extract(i, max_chars), items))

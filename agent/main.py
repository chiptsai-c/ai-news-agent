"""Daily AI news digest: collect → dedupe → prefilter → triage → extract → summarise → digest → deliver.

Usage:
  python -m agent.main            full run
  python -m agent.main --test     small run (8 items, 3 summaries) that does not mark anything as seen
"""
import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

import yaml

from . import deliver, prefilter, render, steps, store
from .collect import collect
from .extract import extract_all
from .llm import LLM

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("agent")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="small run, nothing is saved as seen")
    ap.add_argument("--send", action="store_true", help="with --test: also send to enabled channels")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    sources = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))["sources"]
    if args.test:
        cfg.update(max_triage=8, top_n=3, min_score=1)
    today = date.today().isoformat()
    t0 = time.time()

    log.info("Collecting from %d sources", len(sources))
    items = collect(sources)
    conn = store.connect(ROOT / cfg["db_path"])
    items = prefilter.recent(items, cfg["lookback_hours"])
    items = store.filter_new(conn, items)
    items = prefilter.rank(items, cfg["lookback_hours"], cfg["max_triage"])
    log.info("%d new candidate items after dedupe + prefilter", len(items))
    if not items:
        log.info("Nothing new; done.")
        return 0

    llm = LLM(cfg["ollama_url"], cfg["model"], cfg["num_thread"], cfg["num_ctx"])
    log.info("Triage with %s", cfg["model"])
    steps.triage(llm, items)

    good = sorted((i for i in items if i.score >= cfg["min_score"]), key=lambda i: i.score, reverse=True)
    log.info("Checking %d items for duplicate stories", min(len(good), cfg["top_n"] * 2))
    picked = steps.merge_duplicates(llm, good[:cfg["top_n"] * 2])[:cfg["top_n"]]
    log.info("%d items picked (score >= %d)", len(picked), cfg["min_score"])
    if picked:
        log.info("Extracting article text")
        extract_all(picked, cfg["article_chars"])
        log.info("Summarising")
        steps.summarise(llm, picked)

        digest_llm = LLM(cfg["ollama_url"], cfg["digest_model"], cfg["num_thread"], cfg["num_ctx"]) \
            if cfg.get("digest_model") else llm
        log.info("Writing TL;DR")
        tldr = steps.digest(digest_llm, picked)

        out = ROOT / cfg["output_dir"]
        out.mkdir(exist_ok=True)
        suffix = "-test" if args.test else ""
        (out / f"{today}{suffix}.md").write_text(render.to_markdown(today, tldr, picked), encoding="utf-8")
        html_path = out / f"{today}{suffix}.html"
        html = render.to_html(today, tldr, picked)
        html_path.write_text(html, encoding="utf-8")
        if not args.test:
            (out / "latest.html").write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
        log.info("Wrote %s", html_path)

        for channel in ("telegram", "email", "whatsapp"):
            if (cfg.get(channel) or {}).get("enabled") and (not args.test or args.send):
                try:
                    getattr(deliver, channel)(cfg[channel], today, tldr, picked, html)
                except Exception as e:
                    log.warning("%s delivery failed: %s", channel, e)

    if not args.test:
        store.save(conn, items, today)
    log.info("LLM: %s", llm.speed())
    log.info("Done in %.1f min", (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
                        handlers=[logging.StreamHandler(sys.stdout)])
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("trafilatura").setLevel(logging.ERROR)
    sys.exit(main())

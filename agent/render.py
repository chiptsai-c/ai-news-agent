from html import escape

from .models import Item
from .steps import CATEGORIES


def _grouped(items: list[Item]) -> list[tuple[str, list[Item]]]:
    return [(c, [i for i in items if i.category == c]) for c in CATEGORIES
            if any(i.category == c for i in items)]


def to_markdown(date: str, tldr: str, items: list[Item]) -> str:
    out = [f"# AI News Digest — {date}", "", "## TL;DR", "", tldr, ""]
    for cat, group in _grouped(items):
        out += [f"## {cat}", ""]
        for i in group:
            s = i.summary
            out.append(f"### [{s['headline']}]({i.url})")
            also = "".join(f" · [{a.source}]({a.url})" for a in i.also)
            out.append(f"*{i.source} · importance {i.score}/10{' · also:' + also[2:] if also else ''}*")
            out.append("")
            out += [f"- {b}" for b in s["bullets"]]
            out += ["", f"**Why it matters:** {s['why_it_matters']}", ""]
    return "\n".join(out)


def to_html(date: str, tldr: str, items: list[Item]) -> str:
    tl = "".join(f"<li>{escape(l.lstrip('-* ').strip())}</li>" for l in tldr.splitlines() if l.strip())
    body = []
    for cat, group in _grouped(items):
        body.append(f"<h2>{escape(cat)}</h2>")
        for i in group:
            s = i.summary
            bullets = "".join(f"<li>{escape(b)}</li>" for b in s["bullets"])
            also = ", ".join(f'<a href="{escape(a.url)}">{escape(a.source)}</a>' for a in i.also)
            body.append(
                f'<article><h3><a href="{escape(i.url)}">{escape(s["headline"])}</a></h3>'
                f'<p class="meta">{escape(i.source)} · importance {i.score}/10'
                f'{" · also: " + also if also else ""}</p>'
                f'<ul>{bullets}</ul><p class="why"><b>Why it matters:</b> {escape(s["why_it_matters"])}</p></article>'
            )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI News {date}</title>
<style>
:root{{--bg:#fafaf8;--fg:#1d1d1f;--muted:#6b6b70;--card:#fff;--line:#e4e4e0;--accent:#2f5bd3}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151517;--fg:#ececee;--muted:#9a9aa0;--card:#1e1e21;--line:#2e2e33;--accent:#8aa8ff}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif;max-width:760px;margin:0 auto;padding:24px 16px}}
h1{{font-size:1.6rem;margin:0 0 16px}} h2{{font-size:1.1rem;margin:32px 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}}
.tldr,article{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin:10px 0}}
h3{{font-size:1.05rem;margin:0 0 2px}} a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}
.meta{{color:var(--muted);font-size:.85rem;margin:0 0 6px}} ul{{margin:6px 0;padding-left:20px}} .why{{margin:6px 0 0}}
</style></head><body><h1>AI News Digest — {date}</h1>
<div class="tldr"><b>TL;DR</b><ul>{tl}</ul></div>
{''.join(body)}</body></html>"""

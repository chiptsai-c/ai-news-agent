"""Send the digest to Telegram, email and/or WhatsApp.

Secrets live in Windows Credential Manager (service "ai-news-agent"); set them with setup_delivery.py.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
import keyring

from .models import Item

log = logging.getLogger(__name__)
SERVICE = "ai-news-agent"


def secret(name: str) -> str | None:
    return keyring.get_password(SERVICE, name)


def _chunks(text: str, size: int) -> list[str]:
    out = []
    while text:
        cut = text.rfind("\n", 0, size) if len(text) > size else len(text)
        if cut <= 0:
            cut = size
        out.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return out


def _text(date: str, tldr: str, items: list[Item], bold: str = "") -> str:
    lines = [f"{bold}AI News Digest — {date}{bold}", "", tldr, ""]
    for n, i in enumerate(items, 1):
        lines += [f"{n}. {bold}{i.summary['headline']}{bold}", f"{i.summary['why_it_matters']}", i.url, ""]
    return "\n".join(lines).strip()


def send_telegram(token: str, chat_id: str, text: str) -> None:
    for chunk in _chunks(text, 4000):
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}, timeout=30)
        r.raise_for_status()


def send_email(address: str, password: str, subject: str, text: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, address, address
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(address, password)
        s.send_message(msg)


def telegram(cfg: dict, date: str, tldr: str, items: list[Item], html: str) -> None:
    token, chat_id = secret("telegram_token"), secret("telegram_chat_id")
    if not (token and chat_id):
        log.info("Telegram not set up (run setup_delivery.py telegram); skipping")
        return
    send_telegram(token, chat_id, _text(date, tldr, items))
    log.info("Sent to Telegram")


def email(cfg: dict, date: str, tldr: str, items: list[Item], html: str) -> None:
    address, password = secret("email_address"), secret("email_password")
    if not (address and password):
        log.info("Email not set up (run setup_delivery.py email); skipping")
        return
    send_email(address, password, f"AI News Digest — {date} ({len(items)} stories)",
               _text(date, tldr, items), html)
    log.info("Sent email to %s", address)


GRAPH = "https://graph.facebook.com"
WA_PARAM_MAX = 900  # template body is capped at 1024 chars including its fixed text


def wa_compact(tldr: str, items: list[Item]) -> str:
    """One-line digest for a WhatsApp template parameter (no newlines/tabs allowed, <= WA_PARAM_MAX)."""
    bullets = [l.lstrip("-*• ").strip() for l in tldr.splitlines() if l.strip()]
    text = " • ".join(bullets)
    extra = [i.summary["headline"] for i in items[len(bullets):]]
    if extra:
        text += " | Also: " + "; ".join(extra)
    text = " ".join(text.split())  # collapse any whitespace runs
    return text if len(text) <= WA_PARAM_MAX else text[:WA_PARAM_MAX - 1].rsplit(" ", 1)[0] + "…"


def send_whatsapp_template(token: str, phone_id: str, to: str, template: str, lang: str,
                           params: list[str], api_version: str) -> dict:
    body = {"messaging_product": "whatsapp", "to": to, "type": "template",
            "template": {"name": template, "language": {"code": lang}}}
    if params:
        body["template"]["components"] = [
            {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
    r = httpx.post(f"{GRAPH}/{api_version}/{phone_id}/messages", json=body,
                   headers={"Authorization": f"Bearer {token}"}, timeout=60)
    data = r.json()
    if r.status_code != 200:
        err = data.get("error", {})
        raise RuntimeError(f"{err.get('code')} {err.get('message')} {err.get('error_data', {}).get('details', '')}")
    return data


def whatsapp(cfg: dict, date: str, tldr: str, items: list[Item], html: str) -> None:
    """Send a compact digest via the official WhatsApp Cloud API (Meta), using an approved template."""
    token, phone_id, to = secret("wa_token"), secret("wa_phone_number_id"), secret("wa_to")
    if not (token and phone_id and to):
        log.info("WhatsApp not set up (run setup_delivery.py whatsapp); skipping")
        return
    send_whatsapp_template(token, phone_id, to, cfg.get("template", "ai_news_digest"), cfg.get("language", "en"),
                           [date, wa_compact(tldr, items)], cfg.get("api_version", "v23.0"))
    log.info("Sent to WhatsApp")

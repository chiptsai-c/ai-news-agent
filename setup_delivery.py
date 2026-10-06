r"""Interactive setup for digest delivery. Secrets go to Windows Credential Manager, never to files.

  .\.venv\Scripts\python.exe setup_delivery.py telegram
  .\.venv\Scripts\python.exe setup_delivery.py email
  .\.venv\Scripts\python.exe setup_delivery.py whatsapp
  .\.venv\Scripts\python.exe setup_delivery.py whatsapp-test   (sends today's real digest template)
"""
import getpass
import smtplib
import sys
import time

import httpx
import keyring

import yaml

from agent.deliver import SERVICE, send_email, send_telegram, send_whatsapp_template, secret


def setup_telegram() -> None:
    print("1. In Telegram, chat with @BotFather, send /newbot and follow the steps.")
    token = getpass.getpass("2. Paste the bot token (input is hidden): ").strip()
    r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=30)
    if r.status_code != 200:
        sys.exit("That token was rejected by Telegram. Check it and try again.")
    bot = r.json()["result"]["username"]
    print(f"3. Now open https://t.me/{bot} in Telegram, press Start (or send 'hi'). Waiting up to 2 minutes...")
    chat_id = None
    for _ in range(24):
        updates = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30).json()["result"]
        chats = [u["message"]["chat"]["id"] for u in updates if "message" in u]
        if chats:
            chat_id = str(chats[-1])
            break
        time.sleep(5)
    if not chat_id:
        sys.exit("No message received. Send your bot a message and run this again.")
    send_telegram(token, chat_id, "✅ AI News Agent is connected. Your daily digest will arrive here.")
    keyring.set_password(SERVICE, "telegram_token", token)
    keyring.set_password(SERVICE, "telegram_chat_id", chat_id)
    print("Done: test message sent to Telegram and settings saved.")


def setup_email() -> None:
    print("Gmail needs an App Password (requires 2-Step Verification on your Google account):")
    print("  https://myaccount.google.com/apppasswords  -> create one named 'AI News Agent'")
    address = input("Your Gmail address: ").strip()
    password = getpass.getpass("App password, 16 letters (input is hidden): ").replace(" ", "")
    try:
        send_email(address, password, "AI News Agent connected",
                   "Your daily AI news digest will arrive at this address.",
                   "<p>✅ Your daily AI news digest will arrive at this address.</p>")
    except smtplib.SMTPAuthenticationError:
        sys.exit("Gmail rejected the login. Use an App Password, not your normal password.")
    keyring.set_password(SERVICE, "email_address", address)
    keyring.set_password(SERVICE, "email_password", password)
    print(f"Done: test email sent to {address} and settings saved.")


def _wa_cfg() -> dict:
    return yaml.safe_load(open("config.yaml", encoding="utf-8")).get("whatsapp") or {}


def setup_whatsapp() -> None:
    print("From developers.facebook.com > your app > WhatsApp > API Setup (see README):")
    token = getpass.getpass("1. Permanent access token (input is hidden): ").strip()
    phone_id = input("2. Phone number ID (digits, NOT the phone number): ").strip()
    to = input("3. Your WhatsApp number with country code, digits only (e.g. 60123456789): ").strip().lstrip("+")
    try:
        send_whatsapp_template(token, phone_id, to, "hello_world", "en_US", [], _wa_cfg().get("api_version", "v23.0"))
    except Exception as e:
        sys.exit(f"WhatsApp rejected the test message: {e}\n"
                 "Check the token, the phone number ID, and that your number is added as a recipient.")
    keyring.set_password(SERVICE, "wa_token", token)
    keyring.set_password(SERVICE, "wa_phone_number_id", phone_id)
    keyring.set_password(SERVICE, "wa_to", to)
    print("Done: Meta's 'hello_world' test message sent to your WhatsApp and settings saved.")
    print("Once your 'ai_news_digest' template is approved, run: setup_delivery.py whatsapp-test")


def test_whatsapp_digest() -> None:
    from datetime import date
    cfg = _wa_cfg()
    sample = ("Test message from your AI News Agent • If you can read this, the daily WhatsApp digest "
              "template works • Tomorrow's 07:00 digest will arrive here")
    try:
        send_whatsapp_template(secret("wa_token"), secret("wa_phone_number_id"), secret("wa_to"),
                               cfg.get("template", "ai_news_digest"), cfg.get("language", "en"),
                               [date.today().isoformat(), sample], cfg.get("api_version", "v23.0"))
    except Exception as e:
        sys.exit(f"Template message failed: {e}\n(Is the template approved, and do name/language match config.yaml?)")
    print("Done: digest template message sent.")


if __name__ == "__main__":
    choice = sys.argv[1] if len(sys.argv) > 1 else ""
    {"telegram": setup_telegram, "email": setup_email, "whatsapp": setup_whatsapp,
     "whatsapp-test": test_whatsapp_digest}.get(choice, lambda: sys.exit(__doc__))()

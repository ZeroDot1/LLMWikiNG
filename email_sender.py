import json
import os
import re
import smtplib
import ssl
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"

def load_smtp_config():
    """Lädt die SMTP-Konfiguration aus config.json."""
    default_config = {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_pass": "",
        "use_tls": True,
        "recipients": ""
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                # Standardwerte ergänzen falls Schlüssel fehlen
                for k, v in default_config.items():
                    if k not in saved:
                        saved[k] = v
                return saved
        except Exception:
            return default_config
    return default_config

def save_smtp_config(config_dict):
    """Speichert die SMTP-Konfiguration in config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

def send_real_email(subject, body_html, to_list_override=None):
    """Sendet den Wochenbericht unter Nutzung der gespeicherten SMTP-Konfiguration."""
    config = load_smtp_config()
    
    smtp_host = config.get("smtp_host", "smtp.gmail.com")
    try:
        smtp_port = int(config.get("smtp_port", 587))
    except ValueError:
        smtp_port = 587
        
    smtp_user = config.get("smtp_user", "").strip()
    smtp_pass = config.get("smtp_pass", "").strip()
    use_tls = bool(config.get("use_tls", True))
    
    # Empfängerliste priorisieren: override > gespeicherte config > env variable
    if to_list_override:
        recipients = to_list_override
    else:
        raw_recipients = config.get("recipients", "")
        recipients = [r.strip() for r in raw_recipients.split(",") if r.strip()]
        
    # Fallback auf env falls Konfiguration leer ist
    if not smtp_user:
        smtp_user = os.environ.get("GMAIL_USER", "").strip()
    if not smtp_pass:
        smtp_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not recipients:
        raw_rec_env = os.environ.get("BRIEFING_RECIPIENTS", "")
        recipients = [r.strip() for r in raw_rec_env.split(",") if r.strip()]

    if not smtp_user or not smtp_pass:
        raise ValueError("SMTP-Benutzer und SMTP-Passwort sind nicht konfiguriert (weder in config.json noch in GMAIL_USER/GMAIL_APP_PASSWORD env vars).")
    if not recipients:
        raise ValueError("Keine E-Mail-Empfänger konfiguriert.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("LLMWikiNG Wochenbericht", smtp_user))
    msg["To"] = formataddr(("LLMWikiNG Empfänger", recipients[0]))
    
    # Text-Fallback
    body_text = re.sub(r'<[^>]+>', '', body_html)
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    
    context = ssl.create_default_context()
    
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipients, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_tls:
                server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipients, msg.as_string())
    return recipients

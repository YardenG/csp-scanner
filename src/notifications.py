"""
CSP Scanner V2.0 - Notification Module
Telegram alerts with rich formatting, cooldown tracking, and alert history.
"""

import json
import os
import time
import smtplib
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT,
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT,
    PUSHOVER_USER_KEY, PUSHOVER_APP_TOKEN,
    ALERT_COOLDOWN_MINUTES,
)

# Track sent alerts to avoid spam
ALERT_HISTORY_FILE = os.path.join(os.path.dirname(__file__), ".alert_history.json")


def load_alert_history():
    try:
        if os.path.exists(ALERT_HISTORY_FILE):
            with open(ALERT_HISTORY_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_alert_history(history):
    try:
        with open(ALERT_HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception:
        pass


def should_alert(ticker, strike, expiration):
    """Check if we already alerted for this ticker/strike/exp recently."""
    history = load_alert_history()
    key = f"{ticker}_{strike}_{expiration}"
    if key in history:
        last_alert = history[key]
        elapsed = time.time() - last_alert
        if elapsed < ALERT_COOLDOWN_MINUTES * 60:
            return False
    return True


def mark_alerted(ticker, strike, expiration):
    """Record that we sent an alert for this opportunity."""
    history = load_alert_history()
    key = f"{ticker}_{strike}_{expiration}"
    history[key] = time.time()
    # Clean old entries (older than 24 hours)
    cutoff = time.time() - 86400
    history = {k: v for k, v in history.items() if v > cutoff}
    save_alert_history(history)


# ── TELEGRAM ──

def send_telegram(message):
    """Send a Telegram message. Returns True if successful."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [WARN] Telegram: {e}")
        return False


def format_telegram_alert(opp):
    """Format a single CSP opportunity as a Telegram message."""
    signal_emoji = {"STRONG": "🟢", "MODERATE": "🟡"}
    emoji = signal_emoji.get(opp["signal"], "⚪")

    rsi_emoji = ""
    rsi_zone = opp.get("rsi_zone", "")
    if rsi_zone in ("VERY_OVERSOLD", "OVERSOLD"):
        rsi_emoji = " 🔥"
    elif rsi_zone in ("OVERBOUGHT", "VERY_OVERBOUGHT"):
        rsi_emoji = " ⚠️"

    approach = ""  # CSP-only mode

    checklist = opp.get("checklist", {})
    grade = checklist.get("grade", "?")

    sweet = opp.get("coc_sweet_spot", "")
    safety = opp.get("expected_move_safety", "")

    lines = [
        f"{emoji} <b>{opp['signal']} CSP: {opp['ticker']}{approach}</b>",
        "",
        f"Price: <b>${opp['current_price']}</b>",
        f"Strike: <b>${opp['strike']}</b> ({opp['distance_below_price_pct']}% below)",
        f"Exp: {opp['expiration']} ({opp['dte']}d {opp['dte_class']})",
        f"Premium: ${opp['premium']} (bid ${opp['bid']} / ask ${opp['ask']})",
        f"CoC: <b>{opp['coc_pct']}%</b> {sweet}",
        f"Cash: ${opp['cash_required_per_contract']:,.0f}/contract",
        "",
        f"KC Zone: {opp.get('sandbox_zone', 'N/A')}",
        f"RSI: {opp.get('rsi', 0):.0f} ({rsi_zone}){rsi_emoji}",
    ]

    if safety:
        lines.append(f"Expected Move: {safety}")

    lines.append(f"Score: <b>{opp['total_score']}/100</b> | Grade: {grade}")

    # Premium breakdown
    lines.extend([
        "",
        f"Time Value: ${opp.get('put_time_value', opp['premium'])}",
        f"Downside Protection: ${opp.get('csp_downside_protection', 0):.2f}",
    ])

    # ITM CC comparison
    if opp.get("itm_cc"):
        cc = opp["itm_cc"]
        lines.append(f"ITM CC (ref): ${cc['time_value_profit']:.2f}")

    # Trade 2 plan
    trade2 = opp.get("trade2_plan")
    if trade2:
        lines.extend(["", f"<i>Trade 2: {trade2['action']}</i>"])

    # Data source
    source = opp.get("data_source", "YAHOO")
    lines.append(f"\n<code>{source} | {datetime.now().strftime('%H:%M')}</code>")

    return "\n".join(lines)


def format_telegram_summary(opportunities):
    """Format scan summary for Telegram."""
    if not opportunities:
        return None

    now = datetime.now().strftime("%H:%M")
    lines = [
        f"<b>CSP Scanner v2.0 | {now}</b>",
        f"Found {len(opportunities)} opportunities:",
        "",
    ]

    for i, opp in enumerate(opportunities[:10], 1):
        emoji = "🟢" if opp["signal"] == "STRONG" else "🟡"
        tag = ""  # CSP-only mode
        sweet = opp.get("coc_sweet_spot", "")
        lines.append(
            f"{i}. {emoji} <b>{opp['ticker']}</b> ${opp['strike']} "
            f"| {opp['dte']}d | {opp['coc_pct']}% {sweet} "
            f"| {opp['total_score']}/100{tag}"
        )

    return "\n".join(lines)


def format_console_alert(opp, include_details=True):
    """Format opportunity for Terminal display."""
    signal_emoji = {"STRONG": "🟢", "MODERATE": "🟡", "WEAK": "🟠", "PASS": "🔴"}
    rsi_emoji = {"VERY_OVERSOLD": "🔥", "OVERSOLD": "✅", "NEUTRAL": "➖",
                 "OVERBOUGHT": "⚠️", "VERY_OVERBOUGHT": "🚫"}

    emoji = signal_emoji.get(opp["signal"], "⚪")
    r_emoji = rsi_emoji.get(opp.get("rsi_zone", "NEUTRAL"), "➖")
    approach_tag = ""  # CSP-only mode

    lines = [
        f"{emoji} {opp['signal']} CSP Signal: {opp['ticker']}{approach_tag}",
        f"{'=' * 50}",
        f"Price: ${opp['current_price']}",
        f"Strike: ${opp['strike']}  ({opp['distance_below_price_pct']}% below price)",
        f"Expiration: {opp['expiration']} ({opp['dte']} DTE, {opp['dte_class']})",
        f"Premium: ${opp['premium']}  (Bid: ${opp['bid']} / Ask: ${opp['ask']})",
        f"CoC%: {opp['coc_pct']}%  (Target: {opp.get('target_coc', 1.8)}%)",
        f"Cash Required: ${opp['cash_required_per_contract']:,.0f} per contract",
        f"Premium Collected: ${opp['premium_per_contract']:,.0f} per contract",
        "",
        f"KC Zone: {opp.get('sandbox_zone', 'N/A')}  |  KC Pos: {opp.get('kc_position', 'N/A')}",
        f"RSI: {opp.get('rsi', 'N/A')} {r_emoji} ({opp.get('rsi_zone', 'N/A')})",
        f"Near Support: {'YES' if opp.get('near_support') else 'No'}",
    ]

    # V1.5 fields
    sweet = opp.get("coc_sweet_spot", "")
    safety = opp.get("expected_move_safety", "")
    checklist = opp.get("checklist", {})

    if sweet:
        lines.append(f"CoC Sweet Spot: {sweet}")
    if safety:
        lines.append(f"Expected Move Safety: {safety}")
    if checklist:
        lines.append(f"Checklist: {checklist.get('checks', [])} Grade: {checklist.get('grade', '?')}")

    # Premium breakdown
    lines.extend([
        "",
        "PREMIUM BREAKDOWN:",
        f"  Time Value (profit): ${opp.get('put_time_value', opp['premium'])}",
        f"  Downside Protection: ${opp.get('csp_downside_protection', 0):.2f}",
    ])

    # ITM CC comparison
    itm_cc = opp.get("itm_cc")
    if itm_cc:
        lines.extend([
            "",
            "ITM CC Reference:",
            f"  CSP profit: ${opp.get('put_time_value', 0):.2f}/share",
            f"  ITM CC time value: ${itm_cc['time_value_profit']:.2f}/share",
        ])

    # Trade 2
    trade2 = opp.get("trade2_plan")
    if trade2:
        lines.extend(["", f"TRADE 2: {trade2['action']}", f"  {trade2['note']}"])

    if include_details and opp.get("scores"):
        lines.extend([
            "",
            f"SCORE ({opp['total_score']}/100):",
            f"  KC: {opp['scores'].get('kc_position', 0)}/25  RSI: {opp['scores'].get('rsi_confirmation', 0)}/15",
            f"  Support: {opp['scores'].get('support_level', 0)}/20  Premium: {opp['scores'].get('premium_quality', 0)}/20",
            f"  Liquidity: {opp['scores'].get('liquidity', 0)}/10  DTE: {opp['scores'].get('dte_sweet_spot', 0)}/10",
        ])

    source = opp.get("data_source", "YAHOO")
    lines.append(f"\nSource: {source} | {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    return "\n".join(lines)


def format_console_summary(opportunities):
    """Format a summary for Terminal display."""
    if not opportunities:
        return "No CSP opportunities found matching criteria."

    lines = [
        f"CSP SCANNER v2.0 RESULTS | {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"{'=' * 60}",
        f"Found {len(opportunities)} opportunities",
        "",
    ]

    for i, opp in enumerate(opportunities, 1):
        emoji = {"STRONG": "🟢", "MODERATE": "🟡", "WEAK": "🟠"}.get(opp["signal"], "⚪")
        rsi = opp.get("rsi", 0)
        tag = ""  # CSP-only mode
        sweet = opp.get("coc_sweet_spot", "")
        grade = opp.get("checklist", {}).get("grade", "")
        lines.append(
            f"{i}. {emoji} {opp['ticker']} | ${opp['strike']} | "
            f"{opp['dte']}d | {opp['coc_pct']}% {sweet} | "
            f"RSI:{rsi:.0f} | Score:{opp['total_score']}/100 "
            f"Grade:{grade}{tag}"
        )

    return "\n".join(lines)


def send_alerts(opportunities):
    """Send alerts for new opportunities. Respects cooldown to avoid spam."""
    if not opportunities:
        return 0

    sent_count = 0

    # Filter to only new (not recently alerted) opportunities
    new_opps = []
    for opp in opportunities:
        if should_alert(opp["ticker"], opp["strike"], opp["expiration"]):
            new_opps.append(opp)

    if not new_opps:
        return 0

    # Send summary
    summary = format_telegram_summary(new_opps)
    if summary and send_telegram(summary):
        sent_count += 1

    # Send detailed alerts for STRONG signals
    strong = [o for o in new_opps if o["signal"] == "STRONG"]
    for opp in strong[:3]:
        detail = format_telegram_alert(opp)
        if send_telegram(detail):
            sent_count += 1

    # Mark all as alerted
    for opp in new_opps:
        mark_alerted(opp["ticker"], opp["strike"], opp["expiration"])

    # Console output
    print(f"  Alerts sent: {sent_count} ({len(new_opps)} new opportunities)")

    # Email (optional, sends all)
    if EMAIL_SENDER and EMAIL_PASSWORD and EMAIL_RECIPIENT:
        try:
            body = format_console_summary(new_opps)
            for opp in new_opps[:5]:
                body += "\n\n" + format_console_alert(opp)
            msg = MIMEMultipart()
            msg["From"] = EMAIL_SENDER
            msg["To"] = EMAIL_RECIPIENT
            msg["Subject"] = f"CSP Scanner: {len(new_opps)} opportunities"
            html = f"<pre style='font-family:monospace;font-size:14px'>{body}</pre>"
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.send_message(msg)
        except Exception as e:
            print(f"  [WARN] Email: {e}")

    return sent_count

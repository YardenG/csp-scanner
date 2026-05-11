import os

"""
CSP Scanner V2.0 Configuration
Based on JohnG (Core Position Trading) methodology.
"""

# ── Watchlist ──
WATCHLIST = {
    "TQQQ": {"name": "ProShares UltraPro QQQ", "leverage": "3x", "tracks": "NASDAQ-100"},
    "TNA": {"name": "Direxion Small Cap Bull 3X", "leverage": "3x", "tracks": "Russell 2000"},
    "SOXL": {"name": "Direxion Semiconductors Bull 3X", "leverage": "3x", "tracks": "Semiconductors"},
    "LABU": {"name": "Direxion S&P Biotech Bull 3X", "leverage": "3x", "tracks": "Biotech"},
    "DPST": {"name": "Direxion Regional Banks Bull 3X", "leverage": "3x", "tracks": "Regional Banks"},
    "YINN": {"name": "Direxion China Bull 3X", "leverage": "3x", "tracks": "China (FTSE China 50)"},
    "BITX": {"name": "Volatility Shares 2x Bitcoin", "leverage": "2x", "tracks": "Bitcoin"},
    "NVDX": {"name": "T-Rex 2x Long NVIDIA", "leverage": "2x", "tracks": "NVIDIA"},
    "AAPU": {"name": "Direxion 2x Long Apple", "leverage": "2x", "tracks": "Apple"},
    "AMZU": {"name": "Direxion 2x Long Amazon", "leverage": "2x", "tracks": "Amazon"},
    "METU": {"name": "Direxion 2x Long Meta", "leverage": "2x", "tracks": "Meta"},
    "MSFU": {"name": "Direxion 2x Long Microsoft", "leverage": "2x", "tracks": "Microsoft"},
    "SMCX": {"name": "2x Long Super Micro", "leverage": "2x", "tracks": "Super Micro"},
    "IREN": {"name": "IREN Ltd", "leverage": "1x", "tracks": "IREN (Crypto Mining)"},
    "CONL": {"name": "GraniteShares 2x Long Coinbase", "leverage": "2x", "tracks": "Coinbase"},
    "PTIR": {"name": "GraniteShares 2x Long Palantir", "leverage": "2x", "tracks": "Palantir"},
    "NAIL": {"name": "Direxion 3x Homebuilders", "leverage": "3x", "tracks": "US Homebuilders"},
}

# ── Keltner Channel (JohnG defaults) ──
KC_EMA_PERIOD = 20
KC_ATR_PERIOD = 10
KC_MULTIPLIER = 2.0

# ── RSI ──
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_VERY_OVERSOLD = 20
RSI_OVERBOUGHT = 70
RSI_VERY_OVERBOUGHT = 80

# ── Sandbox Zones (KC position: 0=bottom, 1=top) ──
KC_BOTTOM_ZONE = 0.15
KC_MID_ZONE = 0.50
KC_DANGER_ZONE = 0.75
KC_PROXIMITY_THRESHOLD = 0.03

# ── CSP Trade Criteria ──
MIN_WEEKLY_COC = 1.2
TARGET_WEEKLY_COC = 1.8   # V2.0: JohnG's actual target (not 2.0)
MIN_MONTHLY_COC = 3.0
TARGET_MONTHLY_COC = 5.0

WEEKLY_DTE_MIN = 1
WEEKLY_DTE_MAX = 10
MONTHLY_DTE_MIN = 11
MONTHLY_DTE_MAX = 35

MIN_OPEN_INTEREST = 10
MIN_VOLUME = 5
SUPPORT_LOOKBACK_DAYS = 60

# ── Buyback ──
BUYBACK_MIN_PROFIT_PCT = 50
BUYBACK_TARGET_PROFIT_PCT = 72

# ── Auto-Scan Settings (V2.0) ──
SCAN_INTERVAL_MINUTES = int(os.environ.get("SCAN_INTERVAL_MINUTES", "15"))
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
# US Eastern timezone offset from UTC (EDT = -4, EST = -5)
MARKET_TZ_OFFSET = -4

# Alert thresholds: only notify for these signal levels
ALERT_MIN_SIGNAL = os.environ.get("ALERT_MIN_SIGNAL", "MODERATE")   # STRONG or MODERATE
ALERT_COOLDOWN_MINUTES = 60     # Don't re-alert same ticker/strike within this window

# ── IBKR Settings ──
IBKR_HOST = "127.0.0.1"
IBKR_LIVE_PORT = 7496
IBKR_PAPER_PORT = 7497
IBKR_CLIENT_ID = 1

# ── Telegram Alerts (V2.0) ──
# To set up:
# 1. Message @BotFather on Telegram, send /newbot, follow prompts
# 2. Copy the bot token and paste it below
# 3. Message your new bot, then run: python3 src/setup_telegram.py
# 4. It will find your chat ID automatically
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Email (optional) ──
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587
EMAIL_SENDER = ""
EMAIL_PASSWORD = ""
EMAIL_RECIPIENT = ""

# ── Pushover (optional) ──
PUSHOVER_USER_KEY = ""
PUSHOVER_APP_TOKEN = ""

# ── Scoring Weights ──
SCORE_WEIGHTS = {
    "kc_position": 25,
    "rsi_confirmation": 15,
    "support_level": 20,
    "premium_quality": 20,
    "liquidity": 10,
    "dte_sweet_spot": 10,
}

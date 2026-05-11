# CSP Scanner - Web App

JohnG Greathouse's Core Position Trading methodology.
Auto-scans every 15 min during market hours. Sends Telegram alerts.

## Deploy to Render (free)

### Step 1: Push to GitHub

1. Create a new repo at github.com (e.g. `csp-scanner`)
2. Upload all these files into the repo root
3. Make sure the structure looks like:
   ```
   app.py
   requirements.txt
   render.yaml
   src/
     config.py
     technical.py
     options_scanner.py
     scoring.py
     expected_move.py
     notifications.py
     version.py
   ```

### Step 2: Deploy on Render

1. Go to render.com, sign in with GitHub
2. Click **New > Web Service**
3. Connect your `csp-scanner` repo
4. Render auto-detects `render.yaml` and fills in settings
5. Click **Create Web Service**

### Step 3: Add Telegram credentials

In Render dashboard > your service > **Environment**:

| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID |

To get these:
1. Message @BotFather on Telegram, send `/newbot`
2. Copy the token
3. Message your new bot anything
4. Visit: `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Find `"id"` inside `"chat"` - that's your chat ID

### Step 4: Done

Your scanner is live at `https://csp-scanner.onrender.com`

- Opens to the dashboard
- Click **Scan Now** anytime
- Turn on **Auto-Refresh** to re-scan every 15 min in your browser
- Background auto-scan runs on the server every 15 min during market hours
- Telegram alerts fire automatically when setups are found

## What it scans

14 tickers: TQQQ, TNA, SOXL, LABU, DPST, YINN, BITX, NVDX, AAPU, AMZU, METU, MSFU, SMCX, IREN

## Notes

- Uses Yahoo Finance (no IBKR needed)
- Free Render tier sleeps after 15 min of inactivity
  - Upgrade to Render Starter ($7/mo) for always-on
  - Or use UptimeRobot (free) to ping /health every 10 min
- All 19 JohnG rules implemented in scoring engine

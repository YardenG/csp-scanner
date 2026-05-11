"""
CSP Scanner - Web App
Deployable to Render. Scans every 15 min during market hours.
Sends Telegram alerts. No IBKR (Yahoo Finance only).
"""

import sys
import os
import json
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, render_template_string

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.config import WATCHLIST, SCAN_INTERVAL_MINUTES, ALERT_MIN_SIGNAL, MARKET_TZ_OFFSET
from src.technical import screen_all_tickers
from src.options_scanner import scan_csp_opportunities
from src.scoring import rank_opportunities, filter_top_opportunities
from src.notifications import send_alerts, send_telegram, format_console_summary
from src.version import VERSION

app = Flask(__name__)

# ── State ──
state = {
    "scanning": False,
    "last_scan": None,
    "next_scan": None,
    "scan_count": 0,
    "opportunities": [],
    "kc_summary": [],
    "log": [],
}

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    print(entry)
    state["log"].insert(0, entry)
    if len(state["log"]) > 100:
        state["log"] = state["log"][:100]

def is_market_hours():
    utc = datetime.now(timezone.utc)
    et = utc + timedelta(hours=MARKET_TZ_OFFSET)
    if et.weekday() >= 5:
        return False
    mins = et.hour * 60 + et.minute
    return (9 * 60 + 30) <= mins <= (16 * 60)

def run_scan():
    if state["scanning"]:
        log("Scan already running, skipping")
        return
    state["scanning"] = True
    state["scan_count"] += 1
    log(f"Scan #{state['scan_count']} started ({len(WATCHLIST)} tickers)")

    try:
        tech = screen_all_tickers(WATCHLIST)
        log(f"Technical analysis done: {len(tech)} tickers")

        kc = sorted([{
            "ticker": t["ticker"],
            "current_price": t["current_price"],
            "kc_lower": t["kc_lower"],
            "kc_mid": t["kc_mid"],
            "kc_upper": t["kc_upper"],
            "kc_position": t["kc_position"],
            "rsi": t["rsi"],
            "rsi_zone": t["rsi_zone"],
            "sandbox_zone": t["sandbox_zone"],
            "in_danger_zone": t["in_danger_zone"],
            "rsi_reject": t["rsi_reject"],
            "is_down_day": t.get("is_down_day", False),
            "day_change_pct": t.get("day_change_pct", 0),
        } for t in tech], key=lambda x: x["kc_position"])

        state["kc_summary"] = kc

        all_opps = []
        for a in sorted(tech, key=lambda x: x["kc_position"]):
            if a["in_danger_zone"] or a["rsi_reject"]:
                continue
            opps = scan_csp_opportunities(
                ticker=a["ticker"],
                current_price=a["current_price"],
                kc_lower=a["kc_lower"],
                support_levels=a["support_levels"],
                nearest_support=a["nearest_support"],
                rsi=a["rsi"],
                rsi_zone=a["rsi_zone"],
                sandbox_zone=a["sandbox_zone"],
                in_danger_zone=a["in_danger_zone"],
                rsi_reject=a["rsi_reject"],
            )
            for opp in opps:
                opp["is_down_day"] = a.get("is_down_day", False)
                opp["has_weekly_options"] = a.get("has_weekly_options", True)
                opp["gap_strikes"] = a.get("gap_strikes", [])
                opp["data_source"] = "YAHOO"
            all_opps.extend(opps)
            if opps:
                log(f"  {a['ticker']}: {len(opps)} candidates")

        ranked = rank_opportunities(all_opps)
        top = filter_top_opportunities(ranked, min_signal=ALERT_MIN_SIGNAL, max_results=20)

        state["opportunities"] = top
        state["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        log(f"Scan #{state['scan_count']} complete: {len(top)} opportunities")

        if top:
            sent = send_alerts(top)
            if sent:
                log(f"Telegram: {sent} alert(s) sent")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        state["scanning"] = False


def schedule_loop():
    """Background thread: scan every SCAN_INTERVAL_MINUTES during market hours."""
    import time
    log(f"Scheduler started. Interval: {SCAN_INTERVAL_MINUTES} min")
    send_telegram(f"CSP Scanner v{VERSION} deployed.\nScanning every {SCAN_INTERVAL_MINUTES} min during market hours.")

    while True:
        try:
            if is_market_hours():
                run_scan()
            else:
                et = datetime.now(timezone.utc) + timedelta(hours=MARKET_TZ_OFFSET)
                log(f"Market closed ({et.strftime('%H:%M ET %a')}). Waiting.")
        except Exception as e:
            log(f"Scheduler error: {e}")
        time.sleep(SCAN_INTERVAL_MINUTES * 60)


# ── Dashboard HTML ──
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>CSP Scanner v{{ version }}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#07070f;--surface:#0f0f1a;--border:#1e1e32;--accent:#ef4444;--green:#22c55e;--blue:#3b82f6;--amber:#f59e0b;--text:#e2e2e2;--muted:#666;--radius:10px}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;justify-content:space-between;align-items:center}
header h1{font-size:18px;font-weight:700;color:#fff}header h1 span{color:var(--accent)}
header p{font-size:11px;color:var(--muted);margin-top:2px}
.meta{font-size:11px;color:var(--muted);text-align:right}
.meta b{color:var(--text)}
.toolbar{padding:12px 24px;display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--border);background:var(--surface)}
.btn{border:none;padding:9px 18px;border-radius:7px;font-size:12px;font-weight:600;cursor:pointer;transition:.15s}
.btn-scan{background:var(--blue);color:#fff}.btn-scan:hover{background:#2563eb}.btn-scan:disabled{background:#333;color:var(--muted);cursor:not-allowed}
.btn-auto{background:#14532d;color:#4ade80}.btn-auto.on{background:#4ade80;color:#000}
.status{font-size:11px;color:var(--muted)}.status.scanning{color:var(--amber)}.status.ok{color:var(--green)}
.main{padding:20px 24px;display:grid;grid-template-columns:1fr 340px;gap:16px;max-width:1400px}
@media(max-width:900px){.main{grid-template-columns:1fr;padding:12px}}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.panel-hdr{padding:12px 16px;border-bottom:1px solid var(--border);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);display:flex;justify-content:space-between;align-items:center}
.panel-hdr b{color:var(--text)}

/* KC Table */
table{width:100%;border-collapse:collapse;font-size:12px}
th{padding:7px 10px;text-align:left;color:var(--muted);font-weight:500;font-size:10px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border)}
td{padding:7px 10px;border-bottom:1px solid #0d0d18}
tr:hover td{background:#111120}
.badge{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700}
.b-prime{background:#14532d;color:#4ade80}
.b-entry{background:#1e3a5f;color:#93c5fd}
.b-neutral{background:#292929;color:#888}
.b-skip{background:#1c1010;color:#ef4444}
.b-rsi{background:#3b2900;color:#fbbf24}

/* Opportunity Cards */
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;padding:14px}
.card{background:#0c0c18;border:1px solid var(--border);border-radius:8px;padding:14px;transition:.15s}
.card:hover{border-color:#2a2a45}
.card.strong{border-left:3px solid var(--green)}
.card.moderate{border-left:3px solid var(--amber)}
.card-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
.ticker{font-size:18px;font-weight:800;color:#fff}
.ticker .tag{font-size:10px;font-weight:600;padding:2px 6px;border-radius:3px;margin-left:6px;vertical-align:middle}
.tag-csp{background:#1e3a5f;color:#93c5fd}
.tag-cc{background:#2e1a4a;color:#c4b5fd}
.tag-down{background:#1a0a0a;color:#f87171;font-size:9px}
.sig{padding:3px 8px;border-radius:5px;font-size:10px;font-weight:700}
.sig-strong{background:#14532d;color:#4ade80}
.sig-moderate{background:#451a03;color:#fb923c}
.score{font-size:28px;font-weight:800;line-height:1;color:var(--green)}
.score small{font-size:13px;color:var(--muted);font-weight:400}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:5px 10px;font-size:12px;margin:10px 0}
.lbl{color:var(--muted)}.val{color:var(--text);font-weight:500;text-align:right}
.val.hi{color:var(--green)}.val.warn{color:var(--amber)}
.divider{border:none;border-top:1px solid var(--border);margin:10px 0}
.mini-hdr{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:5px}
.plan{font-size:11px;color:#93c5fd;line-height:1.5}
.plan-note{font-size:10px;color:var(--muted);margin-top:2px}

/* Right sidebar */
.log-wrap{max-height:300px;overflow-y:auto;padding:10px 14px}
.log-line{font-size:11px;color:var(--muted);padding:2px 0;border-bottom:1px solid #0d0d18;font-family:monospace}
.log-line:first-child{color:var(--text)}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--border)}
.stat{background:var(--surface);padding:14px;text-align:center}
.stat-val{font-size:22px;font-weight:800;color:var(--green)}
.stat-lbl{font-size:10px;color:var(--muted);margin-top:2px}
.empty{padding:40px 20px;text-align:center;color:var(--muted)}
.empty h3{font-size:15px;margin-bottom:6px;color:#555}
.progress{display:none;height:2px;background:var(--border);overflow:hidden}
.progress.show{display:block}
.progress-bar{height:100%;background:linear-gradient(90deg,var(--blue),var(--green));animation:prog 2s linear infinite}
@keyframes prog{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
</style>
</head>
<body>
<header>
  <div>
    <h1><span>CSP</span> Scanner v{{ version }}</h1>
    <p>JohnG Methodology | KC + RSI + Expected Move | Telegram Alerts</p>
  </div>
  <div class="meta">
    <div>Last scan: <b id="last-scan">{{ last_scan or "Never" }}</b></div>
    <div>Scans run: <b id="scan-count">{{ scan_count }}</b></div>
  </div>
</header>
<div class="toolbar">
  <button class="btn btn-scan" id="scan-btn" onclick="triggerScan()">Scan Now</button>
  <button class="btn btn-auto" id="auto-btn" onclick="toggleAuto()">Auto-Refresh: OFF</button>
  <span class="status" id="status-txt">Ready</span>
</div>
<div class="progress" id="progress"><div class="progress-bar"></div></div>

<div style="padding:0 24px;max-width:1400px">

<!-- KC Summary Table -->
<div class="panel" style="margin:16px 0">
  <div class="panel-hdr"><span>Keltner Channel + RSI Summary</span><b id="kc-count"></b></div>
  <div id="kc-table"><div class="empty"><h3>No data</h3></div></div>
</div>

<!-- Two column layout -->
<div style="display:grid;grid-template-columns:1fr 320px;gap:16px;margin-bottom:20px">

  <!-- Opportunities -->
  <div>
    <div class="panel-hdr" style="padding:12px 0 8px">
      <span>Opportunities</span>
      <b id="opp-count"></b>
    </div>
    <div id="opp-cards"><div class="empty"><h3>No opportunities yet</h3><p>Click Scan Now to start</p></div></div>
  </div>

  <!-- Sidebar -->
  <div>
    <div class="panel" style="margin-bottom:12px">
      <div class="panel-hdr">Stats</div>
      <div class="stat-grid">
        <div class="stat"><div class="stat-val" id="st-total">0</div><div class="stat-lbl">Total Opps</div></div>
        <div class="stat"><div class="stat-val" id="st-strong">0</div><div class="stat-lbl">Strong</div></div>
        <div class="stat"><div class="stat-val" id="st-scans">0</div><div class="stat-lbl">Scans</div></div>
        <div class="stat"><div class="stat-val" id="st-skip">0</div><div class="stat-lbl">Skipped</div></div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-hdr">Activity Log</div>
      <div class="log-wrap" id="log-wrap">
        <div class="log-line">Ready</div>
      </div>
    </div>
  </div>
</div>
</div>

<script>
var autoTimer = null;

async function triggerScan() {
  var btn = document.getElementById('scan-btn');
  var st = document.getElementById('status-txt');
  var prog = document.getElementById('progress');
  btn.disabled = true;
  btn.textContent = 'Scanning...';
  st.className = 'status scanning';
  st.textContent = 'Scanning ' + {{ tickers }} + ' tickers...';
  prog.className = 'progress show';
  try {
    var r = await fetch('/api/scan', {method:'POST'});
    if (!r.ok) throw new Error('Server returned ' + r.status);
    poll();
  } catch(e) {
    st.className = 'status';
    st.textContent = 'Error: ' + e.message;
    btn.disabled = false;
    btn.textContent = 'Scan Now';
    prog.className = 'progress';
    console.error('Scan error:', e);
  }
}

function poll() {
  var check = async function() {
    try {
      var r = await fetch('/api/state');
      if (!r.ok) throw new Error('Server error: ' + r.status);
      var d = await r.json();
      updateLog(d.log);
      document.getElementById('scan-count').textContent = d.scan_count;
      document.getElementById('st-scans').textContent = d.scan_count;
      if (d.scanning) { setTimeout(check, 2000); return; }
      document.getElementById('last-scan').textContent = d.last_scan || 'Never';
      document.getElementById('scan-btn').disabled = false;
      document.getElementById('scan-btn').textContent = 'Scan Now';
      document.getElementById('status-txt').className = 'status ok';
      document.getElementById('status-txt').textContent = 'Done: ' + (d.last_scan || '');
      document.getElementById('progress').className = 'progress';
      renderKC(d.kc_summary);
      renderOpps(d.opportunities);
    } catch(e) {
      document.getElementById('status-txt').className = 'status';
      document.getElementById('status-txt').textContent = 'Error: ' + e.message;
      document.getElementById('scan-btn').disabled = false;
      document.getElementById('scan-btn').textContent = 'Scan Now';
      document.getElementById('progress').className = 'progress';
      console.error('Poll error:', e);
    }
  };
  check();
}

function updateLog(lines) {
  if (!lines || !lines.length) return;
  var w = document.getElementById('log-wrap');
  w.innerHTML = lines.map(function(l) { return '<div class="log-line">'+escHtml(l)+'</div>'; }).join('');
}

function renderKC(kc) {
  if (!kc || !kc.length) return;
  var skipped = kc.filter(function(t) { return t.in_danger_zone || t.rsi_reject; }).length;
  document.getElementById('kc-count').textContent = skipped + ' skipped';
  document.getElementById('st-skip').textContent = skipped;
  var h = '<table><thead><tr><th>Ticker</th><th>Price</th><th>KC Bot</th><th>KC Pos</th><th>RSI</th><th>Zone</th><th>Status</th><th>Day</th></tr></thead><tbody>';
  for (var t of kc) {
    var bc, bl;
    if (t.in_danger_zone) { bc='b-skip'; bl='SKIP'; }
    else if (t.rsi_reject) { bc='b-rsi'; bl='RSI OB'; }
    else if ((t.sandbox_zone==='BELOW_KC'||t.sandbox_zone==='KC_BOTTOM') && t.rsi<=30) { bc='b-prime'; bl='PRIME'; }
    else if (t.sandbox_zone==='BELOW_KC'||t.sandbox_zone==='KC_BOTTOM') { bc='b-entry'; bl='Entry'; }
    else { bc='b-neutral'; bl=t.sandbox_zone.replace('KC_',''); }
    var dd = t.is_down_day ? ('<span style="color:#f87171;font-size:10px">▼'+Math.abs(t.day_change_pct||0).toFixed(1)+'%</span>') : '';
    h += '<tr><td><b>'+t.ticker+'</b></td>'
      + '<td>$'+t.current_price.toFixed(2)+'</td>'
      + '<td>$'+t.kc_lower.toFixed(2)+'</td>'
      + '<td style="color:'+(t.kc_position<0.5?'#4ade80':'#888')+'">'+t.kc_position.toFixed(2)+'</td>'
      + '<td style="color:'+(t.rsi<30?'#4ade80':t.rsi>70?'#ef4444':'#ccc')+'">'+t.rsi.toFixed(0)+'</td>'
      + '<td style="font-size:10px;color:#888">'+t.sandbox_zone+'</td>'
      + '<td><span class="badge '+bc+'">'+bl+'</span></td>'
      + '<td>'+dd+'</td></tr>';
  }
  h += '</tbody></table>';
  document.getElementById('kc-table').innerHTML = h;
}

function renderOpps(opps) {
  var cnt = document.getElementById('opp-count');
  var cards = document.getElementById('opp-cards');
  var total = document.getElementById('st-total');
  var strong = document.getElementById('st-strong');
  if (!opps || !opps.length) {
    cnt.textContent = '0';
    total.textContent = '0';
    strong.textContent = '0';
    cards.innerHTML = '<div class="empty"><h3>No opportunities</h3><p>No setups meeting criteria right now.</p></div>';
    return;
  }
  cnt.textContent = opps.length;
  total.textContent = opps.length;
  strong.textContent = opps.filter(function(o){return o.signal==='STRONG';}).length;
  var h = '<div class="cards">';
  for (var o of opps) {
    var cls = o.signal === 'STRONG' ? 'strong' : 'moderate';
    var sc = o.signal === 'STRONG' ? 'sig-strong' : 'sig-moderate';
    // CSP-only mode - no approach tag
    var sw = o.coc_sweet_spot || '';
    var gr = (o.checklist||{}).grade || '';
    var safety = o.expected_move_safety || '';
    var dd = o.is_down_day ? '<span class="tag tag-down">DOWN DAY</span>' : '';
    h += '<div class="card '+cls+'">';
    h += '<div class="card-top"><div><span class="ticker">'+o.ticker+'<span class="tag '+tc+'">'+ap+'</span>'+dd+'</span></div><span class="sig '+sc+'">'+o.signal+'</span></div>';
    h += '<div class="score">'+o.total_score+'<small>/100 '+gr+'</small></div>';
    h += '<div class="grid2">';
    h += lv('Strike','$'+o.strike.toFixed(2)+' ('+o.distance_below_price_pct+'% below)','hi');
    h += lv('Premium','$'+o.premium.toFixed(2)+' ('+o.coc_pct.toFixed(2)+'% '+sw+')','hi');
    h += lv('Expiration',o.expiration+' ('+o.dte+'d '+o.dte_class+')','');
    h += lv('Cash/contract','$'+(o.cash_required_per_contract||0).toLocaleString(),'');
    h += lv('KC Zone',o.sandbox_zone,'');
    h += lv('RSI',((o.rsi||0).toFixed(0))+' '+o.rsi_zone,o.rsi<30?'hi':o.rsi>70?'warn':'');
    if (safety) h += lv('Exp Move',safety,'');
    h += '</div><hr class="divider">';
    h += '<div class="mini-hdr">Premium Breakdown</div>';
    h += '<div class="grid2">';
    h += lv('Time Value','$'+(o.put_time_value||o.premium).toFixed(2),'hi');
    h += lv('Protection','$'+(o.csp_downside_protection||0).toFixed(2),'');
    h += '</div>';
    if (o.itm_cc) {
      h += '<hr class="divider"><div class="mini-hdr">ITM CC (reference only)</div>';
      h += '<div class="grid2">';
      h += lv('CSP profit','$'+(o.put_time_value||0).toFixed(2),ap==='CSP'?'hi':'');
      h += lv('ITM CC (ref)','$'+o.itm_cc.time_value_profit.toFixed(2),'');
      h += '</div>';
    }
    if (o.trade2_plan) {
      h += '<hr class="divider"><div class="mini-hdr">Trade 2</div>';
      h += '<div class="plan">'+escHtml(o.trade2_plan.action)+'</div>';
      h += '<div class="plan-note">'+escHtml(o.trade2_plan.note)+'</div>';
    }
    h += '</div>';
  }
  h += '</div>';
  cards.innerHTML = h;
}

function lv(l,v,cls) {
  return '<span class="lbl">'+l+'</span><span class="val '+(cls||'')+'">' + escHtml(String(v))+'</span>';
}
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function toggleAuto() {
  var b = document.getElementById('auto-btn');
  if (autoTimer) {
    clearInterval(autoTimer);
    autoTimer = null;
    b.textContent = 'Auto-Refresh: OFF';
    b.classList.remove('on');
  } else {
    triggerScan();
    autoTimer = setInterval(triggerScan, {{ interval }} * 60 * 1000);
    b.textContent = 'Auto-Refresh: ON';
    b.classList.add('on');
  }
}

// Load on startup
fetch('/api/state').then(function(r){return r.json();}).then(function(d){
  updateLog(d.log);
  renderKC(d.kc_summary);
  renderOpps(d.opportunities);
  document.getElementById('last-scan').textContent = d.last_scan || 'Never';
  document.getElementById('scan-count').textContent = d.scan_count;
  document.getElementById('st-scans').textContent = d.scan_count;
});
</script>
</body>
</html>"""


# ── Routes ──

@app.route("/")
def index():
    return render_template_string(
        HTML,
        version=VERSION,
        last_scan=state["last_scan"] or "Never",
        scan_count=state["scan_count"],
        interval=SCAN_INTERVAL_MINUTES,
        tickers=len(WATCHLIST),
    )

@app.route("/api/scan", methods=["POST"])
def api_scan():
    if state["scanning"]:
        return jsonify({"status": "already_scanning"})
    t = threading.Thread(target=run_scan, daemon=True)
    t.start()
    return jsonify({"status": "started"})

@app.route("/api/state")
def api_state():
    return jsonify({
        "scanning":      state["scanning"],
        "last_scan":     state["last_scan"],
        "scan_count":    state["scan_count"],
        "opportunities": state["opportunities"],
        "kc_summary":    state["kc_summary"],
        "log":           state["log"][:30],
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": VERSION, "scans": state["scan_count"]})


# ── Background Scheduler ──

def start_scheduler():
    import time
    log(f"Background scanner started. Interval: {SCAN_INTERVAL_MINUTES} min.")
    send_telegram(f"CSP Scanner v{VERSION} is live.\nScanning every {SCAN_INTERVAL_MINUTES} min during market hours.")
    while True:
        try:
            if is_market_hours():
                run_scan()
            else:
                et = datetime.now(timezone.utc) + timedelta(hours=MARKET_TZ_OFFSET)
                log(f"Market closed ({et.strftime('%H:%M ET %a')}). Waiting.")
        except Exception as e:
            log(f"Scheduler error: {e}")
        time.sleep(SCAN_INTERVAL_MINUTES * 60)


# Start background thread when app starts
scheduler_thread = threading.Thread(target=start_scheduler, daemon=True)
scheduler_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\nCSP Scanner v{VERSION} - http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)

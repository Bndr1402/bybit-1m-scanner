import json
import time
import urllib.parse
import urllib.request
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

BYBIT_KLINE_URL = "https://delicate-butterfly-5800.bjoo10072-998.workers.dev/v5/market/kline"
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]

HTML_PAGE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ماسح Bybit 1m</title>
  <style>
    body { font-family: Tahoma, Arial, sans-serif; background: #0b1220; color: #f8fafc; margin: 0; padding: 16px; }
    .top { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 16px; }
    input { flex: 1; min-width: 180px; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #fff; }
    button { padding: 10px 16px; border-radius: 8px; border: 0; background: #2563eb; color: #fff; font-weight: bold; cursor: pointer; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px; }
    .sym { font-size: 18px; font-weight: bold; margin-bottom: 8px; }
    .row { display: flex; justify-content: space-between; margin: 4px 0; font-size: 14px; }
    .up { color: #22c55e; font-weight: bold; }
    .down { color: #ef4444; font-weight: bold; }
    .err { background: #450a0a; border: 1px solid #dc2626; color: #fecaca; padding: 12px; border-radius: 8px; margin-bottom: 12px; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h2>ماسح Bybit 1m</h2>
  <div class="top">
    <input id="symbolsInput" value="{{ default_symbols_str }}" placeholder="BTCUSDT, ETHUSDT, SOLUSDT">
    <button onclick="runScan()">فحص</button>
  </div>
  <div id="errorBox"></div>
  <div id="results" class="grid"></div>

  <script>
    async function runScan() {
      const errBox = document.getElementById("errorBox");
      const resBox = document.getElementById("results");
      const symbols = document.getElementById("symbolsInput").value.trim();
      errBox.innerHTML = "";
      resBox.innerHTML = "جاري الفحص...";

      try {
        const resp = await fetch("/api/scan?symbols=" + encodeURIComponent(symbols));
        const data = await resp.json();
        if (!resp.ok || data.error) {
          errBox.innerHTML = '<div class="err">' + (data.error || "خطأ غير معروف") + '</div>';
          resBox.innerHTML = "";
          return;
        }
        resBox.innerHTML = data.items.map(item => {
          if (item.error) {
            return `<div class="card"><div class="sym">${item.symbol}</div><div class="down">${item.error}</div></div>`;
          }
          const cls = item.change_pct >= 0 ? "up" : "down";
          return `
            <div class="card">
              <div class="sym">${item.symbol}</div>
              <div class="row"><span>السعر:</span><span>${item.close}</span></div>
              <div class="row"><span>التغير (1m):</span><span class="${cls}">${item.change_pct}%</span></div>
              <div class="row"><span>الأعلى / الأدنى:</span><span>${item.high} / ${item.low}</span></div>
              <div class="row"><span>الحجم:</span><span>${item.volume}</span></div>
            </div>
          `;
        }).join("");
      } catch (e) {
        errBox.innerHTML = '<div class="err">فشل الاتصال بالخادم: ' + e.message + '</div>';
        resBox.innerHTML = "";
      }
    }
    runScan();
  </script>
</body>
</html>
"""

def fetch_kline_1m(symbol: str, limit: int = 5):
    query = urllib.parse.urlencode({
        "category": "linear",
        "symbol": symbol.upper(),
        "interval": "1",
        "limit": limit
    })
    url = f"{BYBIT_KLINE_URL}?{query}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        payload = json.loads(raw)

    if payload.get("retCode") != 0:
        raise RuntimeError(f"Bybit retCode {payload.get('retCode')}: {payload.get('retMsg')}")

    candles = payload.get("result", {}).get("list", [])
    if not candles:
        raise RuntimeError("لا توجد بيانات شموع")

    latest = candles[0]
    open_p = float(latest[1])
    high_p = float(latest[2])
    low_p = float(latest[3])
    close_p = float(latest[4])
    vol = float(latest[5])
    change_pct = round(((close_p - open_p) / open_p) * 100, 3) if open_p else 0.0

    return {
        "symbol": symbol.upper(),
        "open": open_p,
        "high": high_p,
        "low": low_p,
        "close": close_p,
        "volume": vol,
        "change_pct": change_pct,
        "ts": int(time.time())
    }

@app.route("/")
def index():
    return render_template_string(HTML_PAGE, default_symbols_str=", ".join(DEFAULT_SYMBOLS))

@app.route("/api/scan")
def api_scan():
    raw_symbols = request.args.get("symbols", "")
    symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()] or DEFAULT_SYMBOLS
    items = []
    for sym in symbols:
        try:
            items.append(fetch_kline_1m(sym))
        except Exception as exc:
            items.append({"symbol": sym, "error": str(exc)})
    return jsonify({"items": items})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

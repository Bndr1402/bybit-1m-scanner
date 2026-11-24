import math
import time
import urllib.request
import json
from flask import Flask, render_template_string, request

app = Flask(__name__)

BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]

HTML_PAGE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <title>ماسح Bybit 1m</title>
  <style>
    body { font-family: Tahoma, Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 16px; }
    .card { background: #1e293b; border-radius: 12px; padding: 14px; margin-bottom: 12px; border: 1px solid #334155; }
    .top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .sym { font-size: 18px; font-weight: bold; }
    .buy { background: #16a34a; color: #fff; padding: 4px 10px; border-radius: 8px; font-weight: bold; }
    .sell { background: #dc2626; color: #fff; padding: 4px 10px; border-radius: 8px; font-weight: bold; }
    .wait { background: #475569; color: #fff; padding: 4px 10px; border-radius: 8px; font-weight: bold; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; font-size: 13px; color: #cbd5e1; }
    .box { background: #0f172a; padding: 8px; border-radius: 8px; text-align: center; }
    .reason { margin-top: 8px; font-size: 12px; color: #94a3b8; }
    form { display: flex; gap: 8px; margin-bottom: 14px; }
    input { flex: 1; padding: 10px; border-radius: 10px; border: 1px solid #475569; background: #1e293b; color: #fff; }
    button { padding: 10px 16px; border-radius: 10px; border: none; background: #2563eb; color: #fff; font-weight: bold; }
  </style>
</head>
<body>
  <h2>فاحص عقود Bybit الآجلة (1m)</h2>
  <form method="get">
    <input name="symbols" value="{{ symbols_str }}" placeholder="BTCUSDT,ETHUSDT,SOLUSDT">
    <button type="submit">فحص</button>
  </form>
  {% for r in results %}
  <div class="card">
    <div class="top">
      <span class="sym">{{ r.symbol }}</span>
      <span class="{{ r.css }}">{{ r.signal }}</span>
    </div>
    <div class="grid">
      <div class="box">الدخول<br><b>{{ r.entry }}</b></div>
      <div class="box">الوقف (SL)<br><b>{{ r.sl }}</b></div>
      <div class="box">الهدف (TP 1:1.5)<br><b>{{ r.tp }}</b></div>
    </div>
    <div class="reason">{{ r.reason }}</div>
  </div>
  {% endfor %}
</body>
</html>
"""

def fetch_klines(symbol: str, limit: int = 120):
    url = f"{BYBIT_KLINE_URL}?category=linear&symbol={symbol}&interval=1&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    rows = data.get("result", {}).get("list", [])
    rows.reverse()
    candles = []
    for row in rows:
        candles.append({
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
        })
    return candles

def ema(values, period: int):
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out

def atr(candles, period: int = 10):
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    val = sum(trs[:period]) / period
    for tr in trs[period:]:
        val = (val * (period - 1) + tr) / period
    return val

def supertrend(candles, period: int = 10, mult: float = 3.0):
    if len(candles) < period + 2:
        return None
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr_series = []
    cur = sum(trs[:period]) / period
    atr_series.append(cur)
    for tr in trs[period:]:
        cur = (cur * (period - 1) + tr) / period
        atr_series.append(cur)

    start = period
    final_up = []
    final_dn = []
    trend = []
    for idx, c in enumerate(candles[start:]):
        a = atr_series[idx]
        hl2 = (c["high"] + c["low"]) / 2.0
        basic_up = hl2 - mult * a
        basic_dn = hl2 + mult * a
        if idx == 0:
            final_up.append(basic_up)
            final_dn.append(basic_dn)
            trend.append(1 if c["close"] >= basic_dn else -1)
        else:
            prev_close = candles[start + idx - 1]["close"]
            up = basic_up if (basic_up > final_up[-1] or prev_close < final_up[-1]) else final_up[-1]
            dn = basic_dn if (basic_dn < final_dn[-1] or prev_close > final_dn[-1]) else final_dn[-1]
            final_up.append(up)
            final_dn.append(dn)
            if trend[-1] == -1 and c["close"] > final_dn[-1]:
                trend.append(1)
            elif trend[-1] == 1 and c["close"] < final_up[-1]:
                trend.append(-1)
            else:
                trend.append(trend[-1])
    return trend[-1]

def fmt_price(p: float) -> str:
    if p >= 100:
        return f"{p:.2f}"
    if p >= 1:
        return f"{p:.4f}"
    return f"{p:.6f}"

def analyze_symbol(symbol: str):
    try:
        candles = fetch_klines(symbol)
        closes = [c["close"] for c in candles]
        ema20_list = ema(closes, 20)
        st_dir = supertrend(candles, 10, 3.0)
        cur_atr = atr(candles, 10)
        if not ema20_list or st_dir is None or cur_atr is None:
            return {"symbol": symbol, "signal": "انتظار", "css": "wait", "entry": "-", "sl": "-", "tp": "-", "reason": "بيانات غير كافية"}

        last_c = candles[-1]
        prev_c = candles[-2]
        e20 = ema20_list[-1]
        price = last_c["close"]
        swing_low = min(c["low"] for c in candles[-5:-1])
        swing_high = max(c["high"] for c in candles[-5:-1])

        if st_dir == 1 and price > e20 and last_c["close"] > last_c["open"] and prev_c["close"] <= e20 * 1.003:
            sl = min(swing_low, last_c["low"])
            risk = price - sl
            if risk > 0:
                tp = price + risk * 1.5
                return {
                    "symbol": symbol,
                    "signal": "شراء (Buy)",
                    "css": "buy",
                    "entry": fmt_price(price),
                    "sl": fmt_price(sl),
                    "tp": fmt_price(tp),
                    "reason": "SuperTrend صاعد + السعر فوق EMA20 + شمعة صاعدة"
                }

        if st_dir == -1 and price < e20 and last_c["close"] < last_c["open"] and prev_c["close"] >= e20 * 0.997:
            sl = max(swing_high, last_c["high"])
            risk = sl - price
            if risk > 0:
                tp = price - risk * 1.5
                return {
                    "symbol": symbol,
                    "signal": "بيع (Sell)",
                    "css": "sell",
                    "entry": fmt_price(price),
                    "sl": fmt_price(sl),
                    "tp": fmt_price(tp),
                    "reason": "SuperTrend هابط + السعر تحت EMA20 + شمعة هابطة"
                }

        return {
            "symbol": symbol,
            "signal": "انتظار",
            "css": "wait",
            "entry": fmt_price(price),
            "sl": "-",
            "tp": "-",
            "reason": "لم تكتمل شروط الدخول على فريم 1m"
        }
    except Exception as exc:
        return {"symbol": symbol, "signal": "انتظار", "css": "wait", "entry": "-", "sl": "-", "tp": "-", "reason": f"تعذر الجلب: {exc}"}

@app.route("/")
def index():
    raw = request.args.get("symbols", ",".join(DEFAULT_SYMBOLS))
    syms = [s.strip().upper() for s in raw.split(",") if s.strip()][:10]
    if not syms:
        syms = DEFAULT_SYMBOLS
    results = [analyze_symbol(s) for s in syms]
    return render_template_string(HTML_PAGE, results=results, symbols_str=",".join(syms))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

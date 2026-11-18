import json
import os
from pathlib import Path

import requests

COINS = [c.strip().upper() for c in (os.getenv("COINS") or "BTC,ETH,SOL,XRP,ADA,LTC,ZEC,BNB").split(",") if c.strip()]
TIMEFRAMES = [t.strip() for t in (os.getenv("TIMEFRAMES") or "1h,4h").split(",")]
PERIODS = [int(p) for p in (os.getenv("EMA_PERIODS") or "21,50,200").split(",")]
TOL = float(os.getenv("TOUCH_TOL") or "0.001")
BASE = "https://data-api.binance.vision/api/v3/klines"
STATE = Path("state.json")


def ema(values, n):
    k = 2 / (n + 1)
    e = sum(values[:n]) / n
    out = [None] * (n - 1) + [e]
    for v in values[n:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def candles(coin, tf):
    r = requests.get(BASE, params={"symbol": coin + "USDT", "interval": tf, "limit": 500}, timeout=15)
    r.raise_for_status()
    return [(int(k[0]), float(k[2]), float(k[3]), float(k[4])) for k in r.json()]


def send(text):
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        print(text)
        return
    requests.post(
        f"https://ntfy.sh/{topic}",
        data=text.encode("utf-8"),
        headers={"Title": "EMA alert"},
        timeout=15,
    )


def main():
    seen = json.loads(STATE.read_text()) if STATE.exists() else []
    alerts = []
    for coin in COINS:
        for tf in TIMEFRAMES:
            try:
                c = candles(coin, tf)
            except Exception as e:
                print(f"skip {coin} {tf}: {e}")
                continue
            closes = [x[3] for x in c]
            t, hi, lo, price = c[-1]
            prev_close = c[-2][3]
            for p in PERIODS:
                e = ema(closes, p)[-1]
                if e is None:
                    continue
                if lo * (1 - TOL) <= e <= hi * (1 + TOL):
                    key = f"{coin}|{tf}|{p}|{t}"
                    if key in seen:
                        continue
                    seen.append(key)
                    side = "from above (support test)" if prev_close > e else "from below (resistance test)"
                    alerts.append(f"{coin} {tf} touched EMA{p} at {e:.4f} | price {price:.4f} | {side}")
    for a in alerts:
        send(a)
    STATE.write_text(json.dumps(seen[-1000:]))


if __name__ == "__main__":
    main()

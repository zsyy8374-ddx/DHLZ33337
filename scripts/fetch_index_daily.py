"""抓上证/创业板/科创板每日涨跌幅, 用于"市场风向"特征"""
import json, urllib.request, time

INDEX = {
    "sh000001": "上证综指",      # sh
    "sz399006": "创业板指",      # sz
    "sh000688": "科创50",        # sh
}

def fetch_sina_kline(code, days=120):
    """新浪历史 K 线"""
    # http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData
    url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={code}&scale=240&ma=5&datalen={days}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn"
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        txt = r.read().decode()
    # 新浪返回的是 JS 数组, 解析
    import re
    # 替换无引号 key 为引号
    txt = re.sub(r'(\w+):', r'"\1":', txt)
    data = json.loads(txt)
    return data

result = {}
for code, name in INDEX.items():
    print(f"抓 {name} ({code}) ...", end="")
    try:
        kl = fetch_sina_kline(code, 120)
        # 计算每日涨跌幅
        rows = []
        for i, k in enumerate(kl):
            day = k["day"]
            close = float(k["close"])
            if i == 0:
                chg = 0
            else:
                prev_close = float(kl[i-1]["close"])
                chg = (close - prev_close) / prev_close * 100
            rows.append({"date": day, "close": close, "chg_pct": round(chg, 3)})
        result[code] = {"name": name, "rows": rows}
        print(f" {len(rows)} 天")
    except Exception as e:
        print(f" 失败 {e}")
    time.sleep(0.5)

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/index_daily.json", "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("\n样本最近 5 天:")
for code, d in result.items():
    print(f"\n{d['name']} ({code}):")
    for r in d["rows"][-5:]:
        print(f"  {r['date']}  close={r['close']:.2f}  chg={r['chg_pct']:+.2f}%")

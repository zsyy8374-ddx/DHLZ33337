"""测试: 拉长期 K 线 (1 年+) 看数据源支持度"""
from urllib.request import urlopen, Request
import json

def http_get(url, timeout=10):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

# 测 1: 腾讯长期日K (600330)
url1 = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param=sh600330,day,2024-01-01,2026-04-30,2000,qfq"
print("测试腾讯长期日 K (600330, 2024-01 至今)...")
r = http_get(url1)
try:
    j = json.loads(r)
    rows = j.get("data", {}).get("sh600330", {}).get("day") or j.get("data", {}).get("sh600330", {}).get("qfqday", [])
    print(f"  返回 {len(rows)} 条 K 线")
    if rows:
        print(f"  范围: {rows[0][0]} 至 {rows[-1][0]}")
except Exception as e:
    print(f"  解析失败: {e}")

# 测 2: 新浪长期日 K
url2 = "https://finance.sina.com.cn/realstock/company/sh600330/hisdata/klc_kl.js"
print("\n测试新浪历史 K 线 (600330)...")
r = http_get(url2)
if r:
    print(f"  返回 {len(r)} bytes")
    # 解析 var KLC = ... 
    idx = r.find("=")
    if idx > 0:
        try:
            data_str = r[idx+1:].rstrip(";\n ")
            j = json.loads(data_str)
            rows = j.get("KLC") or []
            print(f"  KLC 数据: {len(rows)} 条")
            if rows:
                print(f"  范围: {rows[0][0]} 至 {rows[-1][0]}")
        except Exception as e:
            print(f"  解析失败: {e}")

# 测 3: 东方财富长期 K
url3 = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.600330&fields1=f1&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&beg=20240101&end=20260430"
print("\n测试东方财富长期 K (600330)...")
r = http_get(url3)
try:
    j = json.loads(r)
    klines = j.get("data", {}).get("klines", [])
    print(f"  返回 {len(klines)} 条 K 线")
    if klines:
        print(f"  首: {klines[0]}")
        print(f"  末: {klines[-1]}")
except Exception as e:
    print(f"  解析失败: {e}")

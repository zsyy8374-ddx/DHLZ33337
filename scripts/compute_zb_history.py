#!/usr/bin/env python3
"""
compute_zb_history.py — 给每个候选股计算"历史炸板率" (v3.1 新特征)

定义:
  zb_rate_60d = 过去 60 天内, 该股涨停后次日炸板的次数 / 涨停总次数

炸板定义: 涨停后次日开盘 > +3% 但收盘 < +5% (冲高失败)
        或 次日开盘 > 涨停价但收盘下跌

输出:
  features/zb_history-{date}.json: {code: {zt_count, zb_count, zb_rate}}

用法:
  python3 compute_zb_history.py            # 给今日 picks 算
  python3 compute_zb_history.py 2026-04-28 # 历史日期 (用于回测扩特征)
"""
import json, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
PICKS_DIR = WORKSPACE / "picks"
FEATURES_DIR = WORKSPACE / "features"
FEATURES_DIR.mkdir(exist_ok=True)
BJT = timezone(timedelta(hours=8))


def http_get(url, timeout=8):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as r:
            data = r.read().decode("utf-8", errors="ignore")
            # 腾讯 K 线返回的是 JSON, 但有时包了 jsonp callback
            if data.startswith("v="):
                data = data[2:].rstrip(";")
            return json.loads(data) if data.strip().startswith("{") else None
    except Exception as e:
        return None


def is_zt(code, chg):
    if code.startswith(('300', '688')): return chg >= 19.5
    if code.startswith(('8', '4', '9')): return chg >= 29.5
    return chg >= 9.7


def fetch_kline(code, end_date, days_back=80):
    sym = ("sh" if code.startswith('6') else "sz") + code
    end = end_date
    beg = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=days_back+30)).strftime("%Y-%m-%d")
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{beg},{end},{days_back+30},qfq"
    d = http_get(url)
    if not d: return []
    sd = d.get("data", {}).get(sym, {})
    return sd.get("qfqday") or sd.get("day") or []


def compute_zb_stats(code, end_date, lookback_days=60):
    """计算该股在 end_date 之前 lookback_days 天的涨停/炸板统计"""
    klines = fetch_kline(code, end_date, days_back=lookback_days+10)
    if not klines or len(klines) < 5:
        return None
    
    # 只取 end_date 之前 (含) 的, 不能用未来数据
    valid = [k for k in klines if k[0] <= end_date]
    if len(valid) < 5: return None
    
    zt_count = 0
    zb_count = 0       # 次日炸板 (开盘冲高收盘没再涨停)
    promoted_count = 0 # 次日继续涨停
    next_red_count = 0 # 次日直接收阴
    
    for i in range(1, len(valid) - 1):  # 留 1 天看次日
        k = valid[i]
        prev = valid[i-1]
        nxt = valid[i+1]
        if len(k) < 5 or len(prev) < 5 or len(nxt) < 5: continue
        c = float(k[2]); pc = float(prev[2])
        if pc <= 0: continue
        chg = (c - pc) / pc * 100
        if not is_zt(code, chg): continue
        zt_count += 1
        
        # 次日表现
        no = float(nxt[1]); nc = float(nxt[2]); nh = float(nxt[3])
        if c <= 0: continue
        next_open_pct = (no - c) / c * 100      # 次日开盘相对涨停价
        next_close_pct = (nc - c) / c * 100     # 次日收盘相对涨停价
        next_high_pct = (nh - c) / c * 100      # 次日最高相对涨停价
        
        if is_zt(code, next_close_pct):
            promoted_count += 1
        elif next_high_pct >= 3 and next_close_pct < next_high_pct - 3:
            # 冲高 3% 但收盘比最高低 3% 以上 = 炸板
            zb_count += 1
        elif next_close_pct < 0:
            next_red_count += 1
    
    if zt_count == 0:
        return {"zt_count": 0, "zb_count": 0, "zb_rate": 0.0,
                "promoted_count": 0, "promotion_rate": 0.0}
    
    return {
        "zt_count": zt_count,
        "zb_count": zb_count,
        "zb_rate": round(zb_count / zt_count, 3),
        "promoted_count": promoted_count,
        "promotion_rate": round(promoted_count / zt_count, 3),
    }


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else datetime.now(BJT).strftime("%Y-%m-%d")
    
    # 加载候选股
    picks_file = PICKS_DIR / f"{target_date}.json"
    if not picks_file.exists():
        print(f"❌ 找不到 picks: {picks_file}", flush=True)
        sys.exit(1)
    
    with open(picks_file, "r", encoding="utf-8") as f:
        d = json.load(f)
    candidates = d.get("candidates", [])
    if not candidates:
        print(f"⚠️ 候选股为空", flush=True)
        sys.exit(0)
    
    print(f"📊 计算 {len(candidates)} 只候选股的历史炸板率 ({target_date})", flush=True)
    
    out = {}
    for i, c in enumerate(candidates):
        code = c["code"]
        name = c["name"]
        stats = compute_zb_stats(code, target_date, lookback_days=60)
        if stats:
            out[code] = stats
            print(f"  [{i+1}/{len(candidates)}] {code} {name}: "
                  f"涨停{stats['zt_count']}次, 炸板{stats['zb_count']} ({stats['zb_rate']*100:.0f}%), "
                  f"晋级{stats['promoted_count']} ({stats['promotion_rate']*100:.0f}%)", flush=True)
        else:
            out[code] = None
            print(f"  [{i+1}/{len(candidates)}] {code} {name}: 数据不足", flush=True)
        time.sleep(0.05)  # 避免被腾讯限流
    
    # 落档
    save_file = FEATURES_DIR / f"zb_history-{target_date}.json"
    with open(save_file, "w", encoding="utf-8") as f:
        json.dump({"date": target_date, "stats": out}, f, ensure_ascii=False, indent=2)
    print(f"\n📁 已落档: {save_file}", flush=True)
    
    # 统计概览
    valid = [v for v in out.values() if v]
    if valid:
        avg_zb = sum(v["zb_rate"] for v in valid) / len(valid)
        avg_prom = sum(v["promotion_rate"] for v in valid) / len(valid)
        print(f"\n📈 全样本均值: 炸板率 {avg_zb*100:.1f}%, 晋级率 {avg_prom*100:.1f}%", flush=True)


if __name__ == "__main__":
    main()

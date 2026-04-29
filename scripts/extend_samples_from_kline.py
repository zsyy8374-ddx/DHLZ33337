#!/usr/bin/env python3
"""
extend_samples_from_kline.py
从已有 v2.4 样本的 240 只股票, 用 K 线反推 3-18 ~ 4-08 的涨停历史
扩充训练样本到 ~20-25 天
"""
import json, urllib.request, time, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
OUT_DIR = WORKSPACE / "backtest"
UA = "Mozilla/5.0"
BJT = timezone(timedelta(hours=8))


def http_get(url, retries=3, timeout=15):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(0.5)
    return None


def is_zt(code, chg):
    if chg is None: return False
    if code.startswith(('300', '688')): return chg >= 19.5
    if code.startswith(('8', '4', '9')): return chg >= 29.5
    return chg >= 9.7


def fetch_kline(code, beg="2026-03-01", end="2026-04-29"):
    sym = ("sh" if code.startswith('6') else "sz") + code
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{beg},{end},80,qfq"
    d = http_get(url)
    if not d: return [], None
    sd = d.get("data", {}).get(sym, {})
    klines = sd.get("qfqday") or sd.get("day") or []
    name = sd.get("qt", {}).get(sym, [None]*2)[1] if sd.get("qt") else None
    return klines, name


def extract_zt_events(klines, code, name):
    """从 K 线提取所有涨停日, 返回每个涨停日及其前置特征"""
    events = []
    for i in range(1, len(klines)):
        k = klines[i]
        if len(k) < 6: continue
        date, o, c, h, l, v = k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])
        prev_c = float(klines[i-1][2])
        if prev_c <= 0: continue
        chg = (c - prev_c) / prev_c * 100
        if not is_zt(code, chg): continue
        
        # 计算后续 1 天表现 (晋级 = 次日继续涨停)
        promoted = False
        next_open_chg = None
        next_close_chg = None
        if i + 1 < len(klines):
            nk = klines[i+1]
            if len(nk) >= 5:
                no = float(nk[1]); nc = float(nk[2])
                if c > 0:
                    next_open_chg = (no - c) / c * 100
                    next_close_chg = (nc - c) / c * 100
                    if is_zt(code, next_close_chg):
                        promoted = True
        else:
            continue  # 最后一天没法判定晋级
        
        # 提取特征 (近似 v2.4 涨停池的字段, 但用 K 线推导)
        # 连板数 lbc: 看前面连续多少天涨停
        lbc = 1
        for j in range(i-1, max(0, i-10), -1):
            pk = klines[j]
            if len(pk) < 5: break
            pprev_c = float(klines[j-1][2]) if j > 0 else 0
            if pprev_c <= 0: break
            pchg = (float(pk[2]) - pprev_c) / pprev_c * 100
            if is_zt(code, pchg):
                lbc += 1
            else:
                break
        
        # vol_ratio: 当日量 / 5日均量
        if i >= 5:
            avg_vol5 = sum(float(klines[j][5]) for j in range(i-5, i)) / 5
            vol_ratio = v / avg_vol5 if avg_vol5 > 0 else 1.0
        else:
            vol_ratio = 1.0
        
        # is_yizi: 开 = 收 = 高 (一字板)
        is_yizi = abs(o - c) < 0.001 and abs(h - c) < 0.001
        
        # zt_5d: 近 5 个交易日涨停次数
        zt_5d = 0
        for j in range(max(0, i-5), i):
            pk = klines[j]
            if len(pk) < 5: continue
            pprev_c = float(klines[j-1][2]) if j > 0 else 0
            if pprev_c <= 0: continue
            pchg = (float(pk[2]) - pprev_c) / pprev_c * 100
            if is_zt(code, pchg): zt_5d += 1
        
        events.append({
            "date": date,
            "code": code,
            "name": name,
            "promoted": promoted,
            "next_open_chg": next_open_chg,
            "next_close_chg": next_close_chg,
            # 注意: K 线反推没有的字段标 None, LR 模型需要兼容
            "kline_only": True,
            "features": {
                "lbc": lbc,
                "is_yizi": is_yizi,
                "zt_5d": zt_5d,
                "vol_ratio": round(vol_ratio, 3),
                "kline_chg": round(chg, 2),
                # 占位 (没有涨停池字段)
                "fbt": 0,         # 没有封板时间
                "fund_yi": 0,     # 没有封单
                "ltsz_yi": 0,     # 没有流通市值 (需要另查)
                "hs": 0,          # 没有换手率 (需要另查 → 但可以用 vol/total_share 估算)
                "zbc": 0,         # 没有炸板数
                "sector_zt": 1,
                "market_strength": 1.0,
                "hybk": "",
            },
            "in_lhb": False,  # 没法判断
            "total": None,     # 没有 v2.4 评分 (需要另算)
        })
    return events


def main():
    src = OUT_DIR / "v24-results-2026-04-28.json"
    print(f"📂 加载现有样本: {src}", flush=True)
    d = json.load(open(src, encoding="utf-8"))
    samples = d["samples"]
    
    # 找出所有不同的股票代码
    codes = list(set(s["code"] for s in samples))
    print(f"   独立股票: {len(codes)}", flush=True)
    
    # 已有日期 (避免重复)
    existing_keys = set((s["code"], s["date"]) for s in samples)
    
    # 拉这些股票的完整 K 线 (3-01 ~ 4-29)
    new_events = []
    print(f"\n🔥 拉 K 线反推历史涨停...", flush=True)
    for i, code in enumerate(codes):
        if (i+1) % 30 == 0:
            print(f"   [{i+1}/{len(codes)}] {len(new_events)} 个新涨停事件", flush=True)
        try:
            klines, name = fetch_kline(code)
            if not klines or len(klines) < 5: continue
            events = extract_zt_events(klines, code, name or code)
            for ev in events:
                key = (ev["code"], ev["date"])
                # 只要 4-09 之前的, 且没在原样本里
                if ev["date"] < "2026-04-09" and key not in existing_keys:
                    new_events.append(ev)
            time.sleep(0.05)  # 防限频
        except Exception as e:
            pass
    
    print(f"\n📊 反推结果:", flush=True)
    print(f"   新涨停事件: {len(new_events)}", flush=True)
    promoted = sum(1 for e in new_events if e["promoted"])
    print(f"   晋级数: {promoted} ({promoted/len(new_events)*100:.1f}%)" if new_events else "")
    
    # 按日期统计
    from collections import Counter
    by_date = Counter(e["date"] for e in new_events)
    print(f"   日期分布:")
    for date in sorted(by_date.keys()):
        n = by_date[date]
        p = sum(1 for e in new_events if e["date"]==date and e["promoted"])
        print(f"     {date}: {n:>3} 涨停, {p:>2} 晋级")
    
    # 保存
    out = OUT_DIR / "v24-extended-samples.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "version": "v2.4-extended",
            "extended_at": datetime.now(BJT).strftime("%Y-%m-%d"),
            "n_original": len(samples),
            "n_extended": len(new_events),
            "samples": new_events,
            "note": "K线反推, 只有 lbc/is_yizi/vol_ratio/zt_5d 等 K 线推导特征. fbt/fund_yi/ltsz_yi/hs/zbc/hybk 缺失."
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n   ✅ 落档: {out}", flush=True)


if __name__ == "__main__":
    main()

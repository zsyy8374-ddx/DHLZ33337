#!/usr/bin/env python3
"""
enrich_samples_with_zb.py — 给 v24-results 的训练样本补上历史炸板率

输入: backtest/v24-results-{date}.json
输出: backtest/v24-results-{date}-enriched.json (附加 zb_rate_60d 和 promotion_rate_60d 到每个 sample.features)

用法:
  python3 enrich_samples_with_zb.py 2026-04-28
"""
import json, sys, time
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
sys.path.insert(0, str(WORKSPACE / "scripts"))
from compute_zb_history import compute_zb_stats

BACKTEST_DIR = WORKSPACE / "backtest"


def main():
    if len(sys.argv) < 2:
        print("用法: python3 enrich_samples_with_zb.py <YYYY-MM-DD>", flush=True)
        sys.exit(1)
    
    end_date = sys.argv[1]
    src = BACKTEST_DIR / f"v24-results-{end_date}.json"
    dst = BACKTEST_DIR / f"v24-results-{end_date}-enriched.json"
    
    if not src.exists():
        print(f"❌ 找不到: {src}", flush=True)
        sys.exit(1)
    
    with open(src, "r", encoding="utf-8") as f:
        d = json.load(f)
    
    samples = d["samples"]
    print(f"📊 给 {len(samples)} 个样本补充历史炸板率 (lookback=60天, 截止 sample_date)", flush=True)
    
    # 缓存每个 (code, sample_date) 的统计 (避免重复算)
    cache = {}
    
    success = 0
    fail = 0
    for i, s in enumerate(samples):
        code = s["code"]
        sample_date = s.get("sample_date") or s.get("date")
        if not sample_date:
            fail += 1
            continue
        
        key = (code, sample_date)
        if key in cache:
            stats = cache[key]
        else:
            stats = compute_zb_stats(code, sample_date, lookback_days=60)
            cache[key] = stats
            time.sleep(0.05)
        
        if stats:
            s["features"]["zb_rate_60d"] = stats["zb_rate"]
            s["features"]["promotion_rate_60d"] = stats["promotion_rate"]
            s["features"]["zt_count_60d"] = stats["zt_count"]
            success += 1
        else:
            s["features"]["zb_rate_60d"] = None
            s["features"]["promotion_rate_60d"] = None
            s["features"]["zt_count_60d"] = 0
            fail += 1
        
        if (i+1) % 50 == 0:
            print(f"  进度 {i+1}/{len(samples)} (成功 {success}, 失败 {fail})", flush=True)
    
    # 落档
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"\n📁 已落档: {dst}", flush=True)
    print(f"   成功: {success}, 失败: {fail}", flush=True)
    
    # 看一下分布
    valid = [s for s in samples if s["features"].get("zb_rate_60d") is not None]
    if valid:
        avg = sum(s["features"]["zb_rate_60d"] for s in valid) / len(valid)
        print(f"\n📈 平均 zb_rate_60d: {avg:.3f}", flush=True)
        # 按炸板率分箱看胜率 (验证特征是否有效)
        bins = [(0, 0.1, "<10%"), (0.1, 0.25, "10-25%"), (0.25, 0.4, "25-40%"),
                (0.4, 0.55, "40-55%"), (0.55, 1.01, "≥55%")]
        print(f"\n   按炸板率分箱看晋级率:", flush=True)
        for lo, hi, lab in bins:
            sub = [s for s in valid if lo <= s["features"]["zb_rate_60d"] < hi]
            if sub:
                pos = sum(1 for s in sub if s["promoted"])
                print(f"     {lab:<8} n={len(sub):3} 晋级率={pos/len(sub)*100:.1f}%", flush=True)


if __name__ == "__main__":
    main()

"""用 v0.6 (8 类 regime + LR v0.5) 在 4-29 候选数据上重算推送

这是 REVERSAL "跑一下" 的离线版本 — 用已有的 4-29 抓的数据
"""
import json, math, sys
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_picks_v4 import detect_regime_v5, extract_v5, predict_lr, style_boost

# 加载 4-29 实盘数据
with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v4-2026-04-29-with-4-30-actual.json") as f:
    data = json.load(f)
cands = data["candidates"]
print(f"4-29 候选 {len(cands)} 只 (含 4-30 实际涨幅)\n")

# 加载 v0.5 (含 v0.6 regime 训) 模型
with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/lr_v5_model.json") as f:
    model = json.load(f)
print(f"模型: {model['version']} (regime v0.6, AUC {model['ts_auc']:.4f})")
print(f"P_high={model['P_high']}, P_mid={model['P_mid']}\n")

# 4-29 那天大盘 regime - 用 4-29 当天三大指数
# 先模拟 style 数据 (从 index_daily 拿到 4-29 那天)
with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/index_daily.json") as f:
    idx_data = json.load(f)
idx_4_29 = {}
for code, info in idx_data.items():
    for r in info["rows"]:
        if r["date"] == "2026-04-29":
            idx_4_29[code] = r["chg_pct"]
print(f"4-29 三大指数 1d: 上证 {idx_4_29.get('sh000001', 0):+.2f}%, 创业 {idx_4_29.get('sz399006', 0):+.2f}%, 科创 {idx_4_29.get('sh000688', 0):+.2f}%")

style = {
    "sh_1d": idx_4_29.get("sh000001", 0),
    "cy_1d": idx_4_29.get("sz399006", 0),
    "kc_1d": idx_4_29.get("sh000688", 0),
    "sh_5d": 0.03, "cy_5d": -1.748, "cy_sh_diff": -1.778,
}
regime = detect_regime_v5(style)
print(f"4-29 regime: {regime}\n")

# 重算每个候选
results = []
for c in cands:
    base = predict_lr(c, model, regime=regime)
    boost = style_boost(c, style)
    final = max(0.01, min(0.99, base + boost))
    
    chg = c.get("chg_4_30", 0)
    is_zt = bool(c.get("zt_4_30", False))
    results.append({
        "code": c["code"], "name": c.get("name", ""),
        "lbc": c.get("d0_lbc", 1) or 1,
        "p_old": c.get("lr_prob", 0),  # 4-29 当天 v0.4 的预测
        "p_new_base": round(base, 4),
        "p_new_boost": round(boost, 4),
        "p_new": round(final, 4),
        "chg_4_30": chg,
        "is_zt_4_30": is_zt,
        "callback": c.get("callback_pct", 0),
        "cb5_main": c.get("cb5_main_avg", 0),
    })

# 按新 P 排序
results.sort(key=lambda r: r["p_new"], reverse=True)

# 推送档位
P_high = model["P_high"]; P_mid = model["P_mid"]
qiang = [r for r in results if r["p_new"] >= P_high]
mid = [r for r in results if P_mid <= r["p_new"] < P_high]
print(f"📊 v0.6 推送档位:")
print(f"  极强 (P>={P_high}): {len(qiang)} 只")
print(f"  强中 (P {P_mid}-{P_high}): {len(mid)} 只")
print(f"  总候选: {len(results)} 只\n")

# 极强档详情
if qiang:
    print(f"🌟 极强档 (Top {min(20, len(qiang))}):")
    for r in qiang[:20]:
        zt = "🚀涨停" if r["is_zt_4_30"] else (f"{r['chg_4_30']:+.2f}%" if r["chg_4_30"] else "—")
        print(f"  {r['code']} {r['name'][:6]:<8} lbc={r['lbc']} P={r['p_new']:.3f} (base {r['p_new_base']:.3f}+boost {r['p_new_boost']:+.2f}) cb={r['callback']:.1f}% cb5={r['cb5_main']:+.2f}亿  4-30实际: {zt}")

# 强中档前 20
if mid:
    print(f"\n💪 强中档 (Top 20):")
    for r in mid[:20]:
        zt = "🚀涨停" if r["is_zt_4_30"] else (f"{r['chg_4_30']:+.2f}%" if r["chg_4_30"] else "—")
        print(f"  {r['code']} {r['name'][:6]:<8} lbc={r['lbc']} P={r['p_new']:.3f} cb={r['callback']:.1f}% cb5={r['cb5_main']:+.2f}亿  4-30实际: {zt}")

# 总命中统计
print(f"\n📊 实战命中 (4-30 实际数据):")
for n in [10, 20, 30, 50]:
    sub = results[:n]
    zt = sum(1 for r in sub if r["is_zt_4_30"])
    up = sum(1 for r in sub if r["chg_4_30"] > 0)
    avg = sum(r["chg_4_30"] for r in sub) / n
    print(f"  Top {n:>3}:  涨停 {zt}/{n} ({zt/n*100:.1f}%), 上涨 {up}/{n} ({up/n*100:.1f}%), 平均 {avg:+.2f}%")

# 旧版本 (v0.4) 对比
results_old = sorted(results, key=lambda r: r["p_old"], reverse=True)
print(f"\n📊 对比 v0.4 (4-29 当天实推) Top 命中:")
for n in [10, 20, 30, 50]:
    sub = results_old[:n]
    zt = sum(1 for r in sub if r["is_zt_4_30"])
    up = sum(1 for r in sub if r["chg_4_30"] > 0)
    avg = sum(r["chg_4_30"] for r in sub) / n
    print(f"  Top {n:>3}:  涨停 {zt}/{n} ({zt/n*100:.1f}%), 上涨 {up}/{n} ({up/n*100:.1f}%), 平均 {avg:+.2f}%")

# 落档
out = "/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v6-rerun-2026-04-29.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump({
        "date": "2026-04-29",
        "model": "v0.6 (8 类 regime + LR v0.5)",
        "regime": regime,
        "P_high": P_high, "P_mid": P_mid,
        "n_candidates": len(results),
        "n_qiang": len(qiang),
        "n_mid": len(mid),
        "candidates": results,
    }, f, ensure_ascii=False, indent=2)
print(f"\n📁 落档: {out}")

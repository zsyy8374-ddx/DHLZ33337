"""离线模拟: v0.5 模型 + 联合调权 在 4-30 那天会推什么? 比 v0.4 (含 6 类 regime) 好吗?"""
import json, math, sys
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")

# 加载 v0.5 模型
with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/lr_v5_model.json") as f:
    v5 = json.load(f)
with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-lr-2026-04-30-v4.json") as f:
    v4 = json.load(f)

# 加载 4-30 候选 (含次日实际)
with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v4-2026-04-29-with-4-30-actual.json") as f:
    data = json.load(f)
cands = data["candidates"]

# 4-30 大盘
sh_1d = 0.11; sz_1d = -0.27; kc_1d = 5.19  # 实际 4-30 三大指数
spread = max(sh_1d, sz_1d, kc_1d) - min(sh_1d, sz_1d, kc_1d)
avg = (sh_1d + sz_1d + kc_1d) / 3

if kc_1d > 2 and sh_1d < 0.5: regime = "kc_only_red"
elif sh_1d > 0.5 and sz_1d < -0.3 and kc_1d < -0.3: regime = "sh_only_red"
elif sz_1d > 2 and sh_1d < 0.5: regime = "sz_only_red"
elif spread > 4 and avg > 0: regime = "spread_high_up"
elif spread < 1 and avg <= -0.5: regime = "weak_resonant"
elif spread < 1 and avg >= 0.5: regime = "strong_resonant"
else: regime = "normal"
print(f"4-30 大盘 regime: {regime}\n")

def extract_v4_local(c):
    callback = c.get("callback_pct", 0) or 0
    min_close = c.get("min_close_pct", 0) or 0
    vol_ratio = c.get("vol_callback_ratio", 0) or 0
    d0_chg = c.get("d0_chg", 10) or 10
    lbc = c.get("d0_lbc", 1) or 1
    cb5_main = c.get("cb5_main_avg", 0) or 0
    cb5_in = c.get("cb5_in_ratio", 0) or 0
    cb3_main = c.get("cb3_main_avg", 0) or 0
    cb1_main = c.get("cb1_main_avg", 0) or 0
    d0_main = c.get("d0_main_flow", 0) or 0
    pre_avg = c.get("pre_d0_5d_main_avg", 0) or 0
    return {
        "callback_pct": callback, "min_close_pct": min_close,
        "broke_ma5": 1.0 if c.get("broke_ma5") else 0.0,
        "broke_ma10": 1.0 if c.get("broke_ma10") else 0.0,
        "shallow": 1.0 if callback < 3 else 0.0,
        "no_close_break": 1.0 if min_close < 3 else 0.0,
        "vol_dead": 1.0 if 0.5 <= vol_ratio < 0.7 else 0.0,
        "vol_explode": 1.0 if vol_ratio >= 1.5 else 0.0,
        "is_20cm": 1.0 if d0_chg >= 19.5 and d0_chg < 25 else 0.0,
        "lbc_num": lbc,
        "is_lianban": 1.0 if lbc >= 2 else 0.0,
        "cb5_main_strong_pos": 1.0 if cb5_main >= 2 else 0.0,
        "cb5_main_pos": 1.0 if 0.5 <= cb5_main < 2 else 0.0,
        "cb5_main_neg": 1.0 if cb5_main < -0.5 else 0.0,
        "cb5_in_high": 1.0 if cb5_in >= 0.6 else 0.0,
        "cb5_in_low": 1.0 if cb5_in < 0.4 else 0.0,
        "cb5_main_avg": cb5_main, "cb3_main_avg": cb3_main, "cb1_main_avg": cb1_main,
        "d0_main_flow": d0_main, "pre_d0_5d_main_avg": pre_avg,
    }

def extract_v5_local(c, regime):
    f = extract_v4_local(c)
    f["reg_kc_red"] = 1.0 if regime == "kc_only_red" else 0.0
    f["reg_sh_red"] = 1.0 if regime == "sh_only_red" else 0.0
    f["reg_sz_red"] = 1.0 if regime == "sz_only_red" else 0.0
    f["reg_spread_up"] = 1.0 if regime == "spread_high_up" else 0.0
    f["reg_weak_res"] = 1.0 if regime == "weak_resonant" else 0.0
    f["reg_strong_res"] = 1.0 if regime == "strong_resonant" else 0.0
    lbc = c.get("d0_lbc", 1) or 1
    f["reg_kc_lianban"] = 1.0 if regime == "kc_only_red" and lbc >= 2 else 0.0
    f["reg_spread_lianban"] = 1.0 if regime == "spread_high_up" and lbc >= 2 else 0.0
    f["reg_sz_lianban"] = 1.0 if regime == "sz_only_red" and lbc >= 2 else 0.0
    return f

def post_hoc_boost(c, regime):
    lbc = c.get("d0_lbc", 1) or 1
    boost = 0
    if regime in ("kc_only_red", "spread_high_up"):
        if lbc >= 3: boost = -0.40
        elif lbc >= 2: boost = -0.30
        else: boost = -0.15
    elif regime == "sh_only_red":
        if lbc >= 3: boost = -0.30
        elif lbc >= 2: boost = -0.20
        else: boost = -0.08
    elif regime == "weak_resonant": boost = -0.05
    elif regime == "sz_only_red": boost = 0.05
    elif regime == "strong_resonant": boost = 0.02
    return boost

def predict_lr(c, model, regime):
    if model.get("regime_used"):
        f = extract_v5_local(c, regime)
    else:
        f = extract_v4_local(c)
    means = model["feature_means"]; stds = model["feature_stds"]
    cont_keys = model["cont_keys"]
    fn = {k: ((v - means.get(k, 0))/stds.get(k, 1) if k in cont_keys else v) for k, v in f.items()}
    z = model["bias"] + sum(model["weights"][k] * fn.get(k, 0) for k in model["weights"])
    if z < -500: return 0.0
    if z > 500: return 1.0
    return 1.0 / (1.0 + math.exp(-z))

# 算每个候选的 v4_base, v5_base, v5_combined
results = []
for c in cands:
    p_v4 = predict_lr(c, v4, regime)
    p_v5 = predict_lr(c, v5, regime)
    p_v5_combined = max(0.01, min(0.99, p_v5 + post_hoc_boost(c, regime)))
    
    chg_4_30 = c.get("chg_4_30", 0)
    is_zt = bool(c.get("zt_4_30", False))
    results.append({
        "code": c["code"], "name": c.get("name", ""),
        "lbc": c.get("d0_lbc", 1),
        "p_v4": p_v4, "p_v5": p_v5, "p_v5_combined": p_v5_combined,
        "chg": chg_4_30, "is_zt": is_zt,
    })

print(f"=== Top 30 对比 (按各模型 P 排序) ===\n")

def topn_metrics(results, key, n):
    sub = sorted(results, key=lambda r: r[key], reverse=True)[:n]
    zt_n = sum(1 for r in sub if r["is_zt"])
    up_n = sum(1 for r in sub if r["chg"] > 0)
    avg = sum(r["chg"] for r in sub) / len(sub)
    return zt_n, up_n, avg

for n in [10, 20, 30, 50]:
    print(f"Top {n}:")
    for key in ["p_v4", "p_v5", "p_v5_combined"]:
        zt, up, avg = topn_metrics(results, key, n)
        label = {"p_v4": "v4 base", "p_v5": "v5 (embed only)", "p_v5_combined": "v5 + post-hoc 联合"}[key]
        print(f"   {label:<25} 涨停 {zt:>2}/{n} ({zt/n*100:>5.1f}%), 上涨 {up}/{n}, 平均 {avg:+.2f}%")
    print()

# 看 4-30 实际涨停的 11 只 (zt_4_30=True) 在三种模型下的排名
print("\n=== 4-30 实际涨停股在各模型下的排名 ===")
zt_stocks = [r for r in results if r["is_zt"]]
for r in zt_stocks:
    rank_v4 = sorted(results, key=lambda x: x["p_v4"], reverse=True).index(r) + 1
    rank_v5 = sorted(results, key=lambda x: x["p_v5"], reverse=True).index(r) + 1
    rank_v5c = sorted(results, key=lambda x: x["p_v5_combined"], reverse=True).index(r) + 1
    print(f"  {r['code']} {r['name'][:6]:<8} lbc={r['lbc']}  v4 rank #{rank_v4}, v5 rank #{rank_v5}, v5+联合 rank #{rank_v5c}")

"""推断时调权 v3: 基于"今日涨停 lbc 分布"的智能过滤

观察 4-30:
- 18 只涨停全是 lbc=1 (没一只 ≥2 板)
- 极端分化日 = 不接力连板 = 该日 ≥2 板的全部降权 0.5

策略 v3: 当日大盘极分化, 把所有 lbc≥2 的票概率乘 0.5
"""
import json

with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v4-2026-04-29-with-4-30-actual.json") as f:
    cands = json.load(f)["candidates"]

def regime_v3(sh, sz, kc):
    diffs = [sh, sz, kc]
    spread = max(diffs) - min(diffs)
    if spread > 4:
        return "extreme_split", {"lbc_ge2_factor": 0.5, "lbc_ge3_factor": 0.4}
    if spread > 2:
        return "split", {"lbc_ge2_factor": 0.7, "lbc_ge3_factor": 0.6}
    return "normal", {"lbc_ge2_factor": 1.0, "lbc_ge3_factor": 1.0}

SH, SZ, KC = 0.11, -0.27, 5.19
regime, params = regime_v3(SH, SZ, KC)
print(f"4-30 大盘: {regime} | params: {params}")

def adjust_v3(p, lbc, params):
    lbc = lbc or 1
    if lbc >= 3:
        return p * params["lbc_ge3_factor"]
    if lbc >= 2:
        return p * params["lbc_ge2_factor"]
    return p

def bucket(p):
    if p >= 0.78: return "极强"
    if p >= 0.70: return "强"
    if p >= 0.60: return "强中"
    if p >= 0.50: return "中"
    if p >= 0.40: return "中低"
    return "低"

# 看 4-30 推送 (P>=0.4) 的 lbc 分布
in_push = [c for c in cands if c["lr_prob"] >= 0.4]
print(f"\n4-30 推送候选 {len(in_push)} 只 lbc 分布:")
import collections
lbc_dist = collections.Counter(c.get("d0_lbc") or 1 for c in in_push)
for lbc, n in sorted(lbc_dist.items()):
    sub = [c for c in in_push if (c.get("d0_lbc") or 1) == lbc]
    zt = sum(1 for c in sub if c.get("zt_4_30"))
    avg = sum((c.get("chg_4_30") or 0) for c in sub) / len(sub)
    print(f"  lbc={lbc}  n={n}  涨停 {zt}  涨停率 {zt/n*100:.1f}%  平均 {avg:+.2f}%")

# 调权后 Top 30 命中
adj_cands = []
for c in cands:
    p = c["lr_prob"]
    pa = adjust_v3(p, c.get("d0_lbc"), params)
    c2 = dict(c); c2["lr_prob_adj"] = pa
    adj_cands.append(c2)

# 原 Top 30 命中
orig_top30 = sorted([c for c in cands if c["lr_prob"]>=0.4], key=lambda x: -x["lr_prob"])[:30]
adj_top30 = sorted([c for c in adj_cands if c["lr_prob"]>=0.4], key=lambda x: -x["lr_prob_adj"])[:30]

orig_zt = sum(1 for c in orig_top30 if c.get("zt_4_30"))
adj_zt = sum(1 for c in adj_top30 if c.get("zt_4_30"))
orig_avg = sum((c.get("chg_4_30") or 0) for c in orig_top30) / len(orig_top30)
adj_avg = sum((c.get("chg_4_30") or 0) for c in adj_top30) / len(adj_top30)

print(f"\n📊 Top 30 命中对比:")
print(f"  原 Top 30: 涨停 {orig_zt}, 命中率 {orig_zt/30*100:.1f}%, 平均 {orig_avg:+.2f}%")
print(f"  调 Top 30: 涨停 {adj_zt}, 命中率 {adj_zt/30*100:.1f}%, 平均 {adj_avg:+.2f}%")

# Top 50 看
orig_top50 = sorted([c for c in cands if c["lr_prob"]>=0.4], key=lambda x: -x["lr_prob"])[:50]
adj_top50 = sorted([c for c in adj_cands if c["lr_prob"]>=0.4], key=lambda x: -x["lr_prob_adj"])[:50]
o50_zt = sum(1 for c in orig_top50 if c.get("zt_4_30"))
a50_zt = sum(1 for c in adj_top50 if c.get("zt_4_30"))
o50_avg = sum((c.get("chg_4_30") or 0) for c in orig_top50) / 50
a50_avg = sum((c.get("chg_4_30") or 0) for c in adj_top50) / 50
print(f"\n📊 Top 50 命中对比:")
print(f"  原 Top 50: 涨停 {o50_zt}, 命中率 {o50_zt/50*100:.1f}%, 平均 {o50_avg:+.2f}%")
print(f"  调 Top 50: 涨停 {a50_zt}, 命中率 {a50_zt/50*100:.1f}%, 平均 {a50_avg:+.2f}%")

# 调权后 Top 10 详细
print(f"\n📊 调权后 Top 10:")
adj_top10 = adj_top30[:10]
for c in adj_top10:
    chg = c.get("chg_4_30") or 0
    zt = "✅" if c.get("zt_4_30") else "  "
    print(f"  {c['code']} {c['name'][:6]:<8} lbc={c.get('d0_lbc')} P {c['lr_prob']:.3f}→{c['lr_prob_adj']:.3f} 实际 {chg:+5.1f}% {zt}")

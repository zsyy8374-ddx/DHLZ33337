"""验证 R7 规则在 4-30 数据上的效果"""
import json
import sys
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_picks_v4 import style_boost

with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v4-2026-04-29-with-4-30-actual.json") as f:
    cands = json.load(f)["candidates"]

# 模拟 4-30 早上 (D0 截至 4-29) 的 style
# 4-29 的 5 天涨跌 (粗略)
style_normal = {
    "sh_5d": 0.5, "cy_5d": -2.0, "cy_sh_diff": -2.5,
    "sh_1d": 0.71, "cy_1d": 2.52, "kc_1d": 0.33,
    "index_spread_1d": 2.19, "extreme_split": False
}

# 但 4-30 是分化日, 这个状态在推断时是 4-30 当天能看到的
# style_boost 应该用 D0+cb 期间的市场, 但实际生产是用 D0 前的
# 所以 R7 触发条件实际上要看推断当日 (4-30) 的 1 日表现
# 4-30: sh +0.11, cy -0.27, kc +5.19 → spread = 5.46, sh_1d 0.11 < 0.5 → extreme_split=True
style_extreme_split = {
    "sh_5d": 0.5, "cy_5d": -2.0, "cy_sh_diff": -2.5,
    "sh_1d": 0.11, "cy_1d": -0.27, "kc_1d": 5.19,
    "index_spread_1d": 5.46, "extreme_split": True
}

def evaluate(style, label):
    adj_cands = []
    for c in cands:
        boost = style_boost(c, style)
        p_orig = c["lr_prob"]
        p_adj = max(0.0, min(1.0, p_orig + boost))
        c2 = dict(c)
        c2["p_adj"] = p_adj
        c2["boost"] = boost
        adj_cands.append(c2)
    
    print(f"\n=== {label} ===")
    
    # Top N 命中
    for n in [10, 20, 30, 50]:
        s = sorted([c for c in adj_cands if c["lr_prob"]>=0.4], key=lambda x: -x["p_adj"])[:n]
        zt = sum(1 for c in s if c.get("zt_4_30"))
        avg = sum((c.get("chg_4_30") or 0) for c in s) / len(s)
        pos = sum(1 for c in s if (c.get("chg_4_30") or 0) > 0)
        print(f"  Top {n:>2}: 涨停 {zt} ({zt/n*100:.1f}%), 上涨 {pos} ({pos/n*100:.1f}%), 平均 {avg:+.2f}%")
    
    # 极强档 (P_adj >= 0.78)
    extreme = [c for c in adj_cands if c["p_adj"] >= 0.78 and c["lr_prob"] >= 0.4]
    if extreme:
        zt = sum(1 for c in extreme if c.get("zt_4_30"))
        avg = sum((c.get("chg_4_30") or 0) for c in extreme) / len(extreme)
        print(f"  极强档 P_adj≥0.78: n={len(extreme)}, 涨停 {zt} ({zt/len(extreme)*100:.1f}%), 平均 {avg:+.2f}%")

evaluate(style_normal, "无极端分化 (R7 不触发)")
evaluate(style_extreme_split, "极端分化 (R7 触发)")

# 看具体哪些被降权
print("\n📊 R7 触发后, 被降权的 lbc≥2 候选 (Top 20):")
hit = []
for c in cands:
    boost = style_boost(c, style_extreme_split)
    if boost < -0.15:  # R7 影响明显
        hit.append((c, boost))
hit.sort(key=lambda x: -x[0]["lr_prob"])
for c, b in hit[:20]:
    chg = c.get("chg_4_30") or 0
    zt = "✅" if c.get("zt_4_30") else "  "
    print(f"  {c['code']} {c['name'][:6]:<8} lbc={c.get('d0_lbc')} P {c['lr_prob']:.3f}+{b:+.2f}={c['lr_prob']+b:.3f}  实际 {chg:+5.1f}% {zt}")

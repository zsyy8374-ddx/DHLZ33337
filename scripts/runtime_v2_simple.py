"""推断时调权 v2: 简化版

核心: 当大盘"分化"日 (科创独苗 / 主板独苗), 极强档全部降权 0.7
不区分高位/低吸, 因为单只判断容易错 — 整组降权
"""
import json

with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v4-2026-04-29-with-4-30-actual.json") as f:
    cands = json.load(f)["candidates"]

def regime_v2(sh, sz, kc):
    """三大指数分化判断 (粗分类)"""
    diffs = [sh, sz, kc]
    max_d = max(diffs); min_d = min(diffs)
    spread = max_d - min_d
    if spread > 4:
        return "extreme_split", 0.85  # 极端分化 (4-30 类型, 科创+5 主板平): 极强档大降
    if spread > 2:
        return "split", 0.65  # 中等分化
    if max_d < 0.3 and min_d < -0.3:
        return "weak", 0.80  # 普跌
    if min_d > 0.3:
        return "strong", 0.0  # 普涨, 不调
    return "normal", 0.30

SH, SZ, KC = 0.11, -0.27, 5.19
regime, attn = regime_v2(SH, SZ, KC)
print(f"4-30 大盘: {regime}, 极强档降权强度 {attn:.2f}")

def adjust_v2(p, attn):
    """整组降权
    P >= 0.78: 乘 (1 - attn*0.4)  → attn=0.85 时 *0.66
    0.70 <= P < 0.78: 乘 (1 - attn*0.2) → *0.83
    0.60 <= P < 0.70: 不调
    P < 0.60: 不调
    """
    if p >= 0.78:
        return p * (1 - attn * 0.4)
    if p >= 0.70:
        return p * (1 - attn * 0.20)
    return p

def bucket(p):
    if p >= 0.78: return "极强"
    if p >= 0.70: return "强"
    if p >= 0.60: return "强中"
    if p >= 0.50: return "中"
    if p >= 0.40: return "中低"
    return "低"

# 调权对比
orig = {}; adj = {}
for c in cands:
    p = c["lr_prob"]
    if p < 0.4: continue
    pa = adjust_v2(p, attn)
    b1 = bucket(p); b2 = bucket(pa)
    zt = c.get("zt_4_30", False)
    chg = c.get("chg_4_30") or 0
    
    orig.setdefault(b1, []).append((c, zt, chg))
    adj.setdefault(b2, []).append((c, zt, chg))

print("\n📊 调权前 vs 调权后命中:")
print(f"{'档位':<6}{'调前 n':>10}{'调前涨停':>10}{'调前命中%':>10}  | {'调后 n':>10}{'调后涨停':>10}{'调后命中%':>10}")
print("-"*80)
for b in ["极强","强","强中","中","中低"]:
    o = orig.get(b, []); a = adj.get(b, [])
    o_n = len(o); o_zt = sum(1 for _, zt, _ in o if zt); o_r = o_zt/o_n*100 if o_n else 0
    a_n = len(a); a_zt = sum(1 for _, zt, _ in a if zt); a_r = a_zt/a_n*100 if a_n else 0
    print(f"{b:<6}{o_n:>10}{o_zt:>10}{o_r:>9.1f}%  | {a_n:>10}{a_zt:>10}{a_r:>9.1f}%")

# 平均涨幅
print("\n📊 平均涨幅:")
print(f"{'档位':<6}{'调前 平均%':>14} | {'调后 平均%':>14}")
print("-"*40)
for b in ["极强","强","强中","中","中低"]:
    o = orig.get(b, []); a = adj.get(b, [])
    o_avg = sum(c for _, _, c in o) / len(o) if o else 0
    a_avg = sum(c for _, _, c in a) / len(a) if a else 0
    print(f"{b:<6}{o_avg:>+13.2f}% | {a_avg:>+13.2f}%")

# Top 5 看
print(f"\n📊 调权后 Top 5 (本是极强档的):")
top5 = sorted(cands, key=lambda c: -adjust_v2(c["lr_prob"], attn))[:10]
for c in top5:
    p = c["lr_prob"]; pa = adjust_v2(p, attn)
    chg = c.get("chg_4_30") or 0; zt = "✅" if c.get("zt_4_30") else "❌"
    print(f"  {c['code']} {c['name'][:6]:<8} P {p:.3f} → {pa:.3f}  实际 {chg:+5.1f}% {zt}")

"""推断时市场调权器 (v1.0 思路)

输入:
  - 今天三大指数涨幅 (sh000001, sz399006, sh000688)
  - 候选股 (含 lr_prob, lbc_num, cb5_main_avg 等)

逻辑:
  1. 判断今日"市场风险档" (高位透支型是否安全)
     - 三大指数全负 / 主板独绿 → 极强档 危险, 降权 0.6
     - 大盘平 + 科创独红 → 极强档 危险 (跟 4-30 一样), 降权 0.7
     - 普涨 → 不调 (维持原概率)
  2. 计算"低吸日"标志: 1板+浅cb5+5-12%回调 在弱市时反而稳, +0.05 加分

回测 4-30 数据看: 在 4-30 的市场状态下, 这个调权能让极强档不再误推
"""
import json, sys
from datetime import datetime

def market_regime(sh, sz, kc):
    """判断今日大盘状态
    Returns:
      regime: 'broad_up' / 'kc_only' / 'sz_only' / 'all_down' / 'mixed' / 'normal'
      high_pos_risk: 0..1 (越高 = 高位透支型越危险, 越要降权)
    """
    avg_main = (sh + sz) / 2  # 主板均值
    if sh > 0.5 and sz > 0.5 and kc > 0.5:
        return ("broad_up", 0.0)  # 普涨, 不调
    if sh < -1 and sz < -1 and kc < -1:
        return ("all_down", 1.0)  # 全跌, 极强档危险
    if kc > 2 and avg_main < 0.3:
        return ("kc_only", 0.7)  # 科创独苗 (4-30 类型), 高位档危险
    if avg_main > 0.5 and kc < -0.5:
        return ("sz_only", 0.4)  # 主板/创业板涨科创跌, 中等风险
    if (sh < 0 or sz < 0) and kc < 0:
        return ("mixed_weak", 0.5)
    return ("normal", 0.2)

def adjust_prob(p, lbc, cb5, regime, high_pos_risk):
    """根据市场状态调整 LR 概率
    高位透支型 (lbc≥2 + cb5≥2): 在 high_pos_risk 高时降权
    低吸型 (lbc=1 + cb5≤1.5): 在弱市时不动甚至加分 (它们抗跌)
    """
    is_high_pos = (lbc or 1) >= 2 and (cb5 or 0) >= 2.0
    is_low_absorb = (lbc or 1) == 1 and -1 <= (cb5 or 0) <= 1.5
    
    if is_high_pos:
        # 极强 0.78 + 风险 0.7 → 0.78 * (1 - 0.7*0.5) = 0.78 * 0.65 = 0.51 (从极强降到中)
        adj_factor = 1 - high_pos_risk * 0.5
        return p * adj_factor, "高位透支被降权"
    if is_low_absorb and regime in ("kc_only", "broad_up"):
        # 低吸型在科创风口或普涨时加 0.03
        return min(0.99, p + 0.03), "低吸+科创风口加分"
    if is_low_absorb and regime == "mixed_weak":
        # 弱市低吸, 维持原值 (它们抗跌)
        return p, "低吸+弱市保持"
    return p, "无调整"

# 测试: 用 4-30 实际数据回放
with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v4-2026-04-29-with-4-30-actual.json") as f:
    data = json.load(f)
cands = data["candidates"]

# 4-30 实际指数涨幅
SH_430 = 0.11; SZ_430 = -0.27; KC_430 = 5.19
regime, hpr = market_regime(SH_430, SZ_430, KC_430)
print(f"4-30 大盘状态: {regime}, 高位风险 = {hpr:.1f}")
print(f"  上证 {SH_430:+.2f}%, 创业板 {SZ_430:+.2f}%, 科创50 {KC_430:+.2f}%")

# 调权前后命中对比
def bucket(p):
    if p >= 0.78: return "极强"
    if p >= 0.70: return "强"
    if p >= 0.60: return "强中"
    if p >= 0.50: return "中"
    if p >= 0.40: return "中低"
    return "低"

orig_buckets = {}
adj_buckets = {}
for c in cands:
    p_orig = c["lr_prob"]
    if p_orig < 0.4: continue  # 跟实战阈值对齐
    p_adj, _ = adjust_prob(p_orig, c.get("d0_lbc"), c.get("cb5_main_avg"), regime, hpr)
    
    b1 = bucket(p_orig); b2 = bucket(p_adj)
    zt = c.get("zt_4_30", False)
    
    orig_buckets.setdefault(b1, {"n": 0, "zt": 0})
    orig_buckets[b1]["n"] += 1
    if zt: orig_buckets[b1]["zt"] += 1
    
    adj_buckets.setdefault(b2, {"n": 0, "zt": 0})
    adj_buckets[b2]["n"] += 1
    if zt: adj_buckets[b2]["zt"] += 1

print("\n📊 调权前 (原 v0.4 模型):")
for b in ["极强","强","强中","中","中低"]:
    if b in orig_buckets:
        d = orig_buckets[b]
        rate = d["zt"]/d["n"]*100 if d["n"] else 0
        print(f"   {b:<5} n={d['n']:>3}  涨停 {d['zt']:>3} ({rate:.1f}%)")

print("\n📊 调权后 (v1.0 实时调档):")
for b in ["极强","强","强中","中","中低"]:
    if b in adj_buckets:
        d = adj_buckets[b]
        rate = d["zt"]/d["n"]*100 if d["n"] else 0
        print(f"   {b:<5} n={d['n']:>3}  涨停 {d['zt']:>3} ({rate:.1f}%)")

# 看最关键的 12 只极强档变化
print("\n📊 4-30 极强档 12 只调权前后对比 (按调权后 P 排序):")
extreme = sorted([c for c in cands if c["lr_prob"]>=0.78], key=lambda x: -x["lr_prob"])
for c in extreme:
    p_adj, why = adjust_prob(c["lr_prob"], c.get("d0_lbc"), c.get("cb5_main_avg"), regime, hpr)
    chg = c.get("chg_4_30") or 0
    zt = "✅" if c.get("zt_4_30") else "❌"
    print(f"   {c['code']} {c['name'][:6]:<8} P {c['lr_prob']:.3f} → {p_adj:.3f}  ({why})  实际 {chg:+.1f}% {zt}")

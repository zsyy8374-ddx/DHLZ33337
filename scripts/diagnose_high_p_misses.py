"""分析 v0.6 极强档失误模式 - 哪些 P 高但跌的票 共性是什么"""
import json

with open('/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v6-rerun-2026-04-29.json') as f:
    d = json.load(f)
cands = d['candidates']

def chg_label(r):
    if r['is_zt_4_30']: return '🚀涨停'
    return f"{r['chg_4_30']:+.1f}%"

qiang = cands[:12]
mid = cands[12:62]

print(f"=== Top 命中分布 ===\n")

def stats(arr, label):
    n = len(arr)
    zt = sum(1 for r in arr if r['is_zt_4_30'])
    up = sum(1 for r in arr if r['chg_4_30'] > 0)
    avg = sum(r['chg_4_30'] for r in arr) / n
    big_drop = sum(1 for r in arr if r['chg_4_30'] < -3)
    big_up = sum(1 for r in arr if r['chg_4_30'] > 3)
    return f"{label:<15} n={n:>3}  涨停 {zt}  上涨 {up}  >+3% {big_up}  <-3% {big_drop}  平均 {avg:+.2f}%"

print(stats(qiang, "极强 (P≥.85)"))
print(stats(mid[:20], "强中前20"))
print(stats(mid[20:50], "强中21-50"))
print(stats(cands[62:100], "中档 (62-100)"))
print(stats(cands[100:200], "100-200"))
print(stats(cands[200:], "200+ (尾部)"))

print(f"\n=== 极强档 12 只详情 ===")
for r in qiang:
    label = chg_label(r)
    print(f"  {r['code']} {r['name'][:6]:<8} P={r['p_new']:.3f} lbc={r['lbc']} cb={r['callback']:.1f}% cb5={r['cb5_main']:+.2f}亿  4-30: {label}")

# v0.4 vs v0.6 极强档差异
v4_sorted = sorted(cands, key=lambda r: r['p_old'], reverse=True)
v4_qiang_codes = set(r['code'] for r in v4_sorted[:12])
v6_qiang_codes = set(r['code'] for r in qiang)

print(f"\n=== v0.4 vs v0.6 极强档差异 ===")
print(f"  共同 ({len(v4_qiang_codes & v6_qiang_codes)}): {sorted(v4_qiang_codes & v6_qiang_codes)}")
print(f"  v0.6 新加 ({len(v6_qiang_codes - v4_qiang_codes)}): {sorted(v6_qiang_codes - v4_qiang_codes)}")
print(f"  v0.4 才有 ({len(v4_qiang_codes - v6_qiang_codes)}): {sorted(v4_qiang_codes - v6_qiang_codes)}")

print(f"\nv0.6 加进来的票 (因 +0.05 boost 升档):")
for r in qiang:
    if r['code'] in (v6_qiang_codes - v4_qiang_codes):
        label = chg_label(r)
        print(f"  {r['code']} {r['name'][:6]:<8} P_old={r['p_old']:.3f} → P_new={r['p_new']:.3f}, boost={r['p_new_boost']:+.3f}, lbc={r['lbc']}, 4-30: {label}")

# 4-30 涨停股在两个版本的排名
print(f"\n=== 4-30 涨停股 v0.4 vs v0.6 排名 ===")
zt_stocks = [r for r in cands if r['is_zt_4_30']]
v4_ranks = {r['code']: i+1 for i, r in enumerate(v4_sorted)}
v6_ranks = {r['code']: i+1 for i, r in enumerate(cands)}
zt_stocks.sort(key=lambda r: v6_ranks[r['code']])
for r in zt_stocks:
    print(f"  {r['code']} {r['name'][:6]:<8} lbc={r['lbc']}  v0.4 #{v4_ranks[r['code']]:<3} → v0.6 #{v6_ranks[r['code']]:<3}")

# 只用 P_new_base (LR 含 regime 但无 post-hoc) 看排名
print(f"\n=== 假设 4-29 关掉 boost, 只用 LR+regime embed (P_new_base) ===")
no_boost = sorted(cands, key=lambda r: r['p_new_base'], reverse=True)
for n in [10, 12, 20, 30, 50]:
    sub = no_boost[:n]
    zt = sum(1 for r in sub if r['is_zt_4_30'])
    avg = sum(r['chg_4_30'] for r in sub) / n
    print(f"  Top {n}: 涨停 {zt}, 平均 {avg:+.2f}%")

print(f"\n=== v0.4 (老 P_old) 排序 ===")
for n in [10, 12, 20, 30, 50]:
    sub = v4_sorted[:n]
    zt = sum(1 for r in sub if r['is_zt_4_30'])
    avg = sum(r['chg_4_30'] for r in sub) / n
    print(f"  Top {n}: 涨停 {zt}, 平均 {avg:+.2f}%")

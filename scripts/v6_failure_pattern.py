"""精确分析 4-29 极强档 12 只为啥 4-30 全错"""
import json

with open('/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v6-rerun-2026-04-29.json') as f:
    d = json.load(f)
cands = d['candidates']

qiang = cands[:12]

# 4-30 涨停股 (18 只 全样本)
zt_18 = [r for r in cands if r['is_zt_4_30']]

# 看一个共同维度 - days_since_d0
print("=== 4-29 极强档 vs 4-30 涨停股 days_since_d0 比较 ===")
print("(我们的候选数据没 days_since, 但有 callback_pct/cb5_main 这些)")
print()

print("=== 极强档 12 失败:")
for r in qiang:
    print(f"  {r['code']} {r['name'][:6]:<8} P={r['p_new']:.3f} cb_pct={r['callback']:.1f}% cb5={r['cb5_main']:+.2f}亿 lbc={r['lbc']}  4-30: {r['chg_4_30']:+.1f}%")

# 平均特征
def avg_feat(arr, key):
    return sum(r.get(key, 0) for r in arr) / len(arr)

print(f"\n极强档平均: cb_pct={avg_feat(qiang, 'callback'):.2f}%, cb5={avg_feat(qiang, 'cb5_main'):+.2f}亿, lbc={avg_feat(qiang, 'lbc'):.2f}")

print(f"\n=== 4-30 真涨停股 18 只 (排名按 v0.6 P):")
zt_18.sort(key=lambda r: r['p_new'], reverse=True)
for r in zt_18:
    print(f"  {r['code']} {r['name'][:6]:<8} P={r['p_new']:.3f} cb_pct={r['callback']:.1f}% cb5={r['cb5_main']:+.2f}亿 lbc={r['lbc']}")

print(f"\n4-30 涨停平均: cb_pct={avg_feat(zt_18, 'callback'):.2f}%, cb5={avg_feat(zt_18, 'cb5_main'):+.2f}亿, lbc={avg_feat(zt_18, 'lbc'):.2f}")

# 看回原始数据有没有更细的信息
import json
with open('/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v4-2026-04-29-with-4-30-actual.json') as f:
    full = json.load(f)
codes_q = set(r['code'] for r in qiang)
codes_zt = set(r['code'] for r in zt_18)

print("\n\n=== 极强档 12 的原始数据 (含 days_since_d0) ===")
for c in full['candidates']:
    if c['code'] in codes_q:
        print(f"  {c['code']} {c.get('name','')[:6]:<8} d0={c.get('d0_date')} days={c.get('days_since_d0')} cb={c.get('callback_pct',0):.1f}% mc={c.get('min_close_pct',0):.1f}% lbc={c.get('d0_lbc',1)} cb5={c.get('cb5_main_avg',0):+.2f} cb1={c.get('cb1_main_avg',0):+.2f} d0_main={c.get('d0_main_flow',0):+.2f}")

print("\n=== 4-30 涨停 18 的原始数据 ===")
for c in full['candidates']:
    if c.get('zt_4_30'):
        print(f"  {c['code']} {c.get('name','')[:6]:<8} d0={c.get('d0_date')} days={c.get('days_since_d0')} cb={c.get('callback_pct',0):.1f}% mc={c.get('min_close_pct',0):.1f}% lbc={c.get('d0_lbc',1)} cb5={c.get('cb5_main_avg',0):+.2f} cb1={c.get('cb1_main_avg',0):+.2f} d0_main={c.get('d0_main_flow',0):+.2f}")

# 极强档 12 的 days_since_d0 分布
ds_q = [c.get('days_since_d0') for c in full['candidates'] if c['code'] in codes_q]
ds_zt = [c.get('days_since_d0') for c in full['candidates'] if c.get('zt_4_30')]
print(f"\n=== 距 D0 天数 ===")
print(f"  极强档 12 days: {ds_q}")
print(f"  4-30 涨停 18 days: {ds_zt}")
print(f"  极强档平均 days: {sum(ds_q)/len(ds_q):.1f}")
print(f"  涨停平均 days: {sum(ds_zt)/len(ds_zt):.1f}")

# d0_chg
d0c_q = [c.get('d0_chg') for c in full['candidates'] if c['code'] in codes_q]
d0c_zt = [c.get('d0_chg') for c in full['candidates'] if c.get('zt_4_30')]
print(f"\n=== D0 涨幅 ===")
print(f"  极强档: max={max(d0c_q):.1f}, min={min(d0c_q):.1f}, 20cm数={sum(1 for x in d0c_q if x>=15)}")
print(f"  涨停: max={max(d0c_zt):.1f}, min={min(d0c_zt):.1f}, 20cm数={sum(1 for x in d0c_zt if x>=15)}")

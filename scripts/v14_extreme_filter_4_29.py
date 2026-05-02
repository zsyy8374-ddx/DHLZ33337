"""分析 v1.1 vs v1.4 在 4-29 推送的 极强档 差异
- v1.1 极强档 (P>=0.7): 12 只, 4-30 涨停 0 只, 平均 -2.31% — 全错
- v1.4 极强档 (P>=0.6 集成): 看哪些是 v1.1 推过 v1.4 拒了
- 验证: v1.4 拒掉的 v1.1 极强档, 4-30 实际是不是确实表现差
"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from predict_v14 import load_v14_model, predict_v14
from lr_v11_with_recent_rev_rate import extract_v11
from pathlib import Path

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')

# 拉 4-29 推送 + 4-30 实战
hits_path = WORKSPACE / 'picks' / 'reversal_hits_full.jsonl'
data = None
with open(hits_path) as f:
    for line in f:
        row = json.loads(line)
        if row.get('pick_date') == '2026-04-29':
            data = row; break
results = data['results']

with open(WORKSPACE / 'picks' / 'reversal-v4-2026-04-29.json') as f:
    full = json.load(f)
cand_by_code = {c['code']: c for c in full['candidates']}

# 重打分 v1.4
model_v14 = load_v14_model()
recent_5d, recent_10d, recent_20d = 0.28, 0.39, 0.45

scored = []
for r in results:
    cand = cand_by_code.get(r['code'])
    if not cand: continue
    e_like = {
        'd0_chg': cand.get('d0_chg', 10), 'd0_lbc': cand.get('d0_lbc', 1),
        'callback_pct': cand.get('callback_pct', 0), 'min_close_pct': cand.get('min_close_pct', 0),
        'broke_ma5': cand.get('broke_ma5', False), 'broke_ma10': cand.get('broke_ma10', False),
        'vol_callback_ratio': cand.get('vol_callback_ratio', 0),
        'cb5_main_avg': cand.get('cb5_main_avg', 0), 'cb3_main_avg': cand.get('cb3_main_avg', 0),
        'cb1_main_avg': cand.get('cb1_main_avg', 0), 'cb5_in_ratio': cand.get('cb5_in_ratio', 0),
        'd0_main_flow': cand.get('d0_main_flow', 0), 'pre_d0_5d_main_avg': cand.get('pre_d0_5d_main_avg', 0),
        'outcome': 'na', 'd0_date': cand.get('d0_date', '2026-04-29')
    }
    f = extract_v11(e_like)
    f['recent_5d_rev_rate'] = recent_5d
    f['recent_10d_rev_rate'] = recent_10d
    f['recent_20d_rev_rate'] = recent_20d
    p_ens, p_lr_v14, p_gb = predict_v14(f, model_v14)
    
    scored.append({
        'code': r['code'],
        'name': r.get('name', ''),
        'p_v11': r['lr_prob'],  # 这个是 v1.1 输出的 (含 boost)
        'p_v14': p_ens,
        'p_v14_lr': p_lr_v14,
        'p_v14_gb': p_gb,
        'is_zt': r.get('is_zt', False),
        'today_chg': r.get('today_chg', 0),
        'today_high': r.get('today_high', 0),
        'lbc': cand.get('d0_lbc', 1),
        'cb5': cand.get('cb5_main_avg', 0),
        'cb1': cand.get('cb1_main_avg', 0),
        'callback_pct': cand.get('callback_pct', 0),
        'd0_date': cand.get('d0_date', ''),
    })

# === 关键分析 ===
# 1. v1.1 极强档 (P>=0.78): 12 只
v11_extreme = [s for s in scored if s['p_v11'] >= 0.78]
print(f"=== v1.1 极强档 (P>=0.78): {len(v11_extreme)} 只, 4-30 涨停 {sum(1 for s in v11_extreme if s['is_zt'])} ===")
for s in sorted(v11_extreme, key=lambda x: -x['p_v11']):
    flag = "✅" if s['is_zt'] else "❌"
    saved_by_v14 = "💾v1.4 拒了!" if s['p_v14'] < 0.5 else ""
    print(f"  {s['code']} {s['name']:8s}  v1.1={s['p_v11']:.3f}  v1.4={s['p_v14']:.3f}  {flag} {s['today_chg']:+.2f}%  lbc={s['lbc']} cb5={s['cb5']:+.2f}亿  {saved_by_v14}")

# 2. v1.4 拒掉的 v1.1 高分票 (v1.1 P>=0.6, v1.4 < 0.45)
v14_rejected = [s for s in scored if s['p_v11'] >= 0.6 and s['p_v14'] < 0.45]
print(f"\n=== v1.4 关键拒掉的 v1.1 高分票 (v1.1≥0.6, v1.4<0.45): {len(v14_rejected)} 只 ===")
zt_rejected = sum(1 for s in v14_rejected if s['is_zt'])
zt_rate_rejected = zt_rejected / max(1, len(v14_rejected))
all_chg_rejected = sum(s['today_chg'] for s in v14_rejected) / max(1, len(v14_rejected))
print(f"   涨停 {zt_rejected} ({zt_rate_rejected*100:.1f}%), 平均涨幅 {all_chg_rejected:+.2f}%")
for s in sorted(v14_rejected, key=lambda x: -x['p_v11'])[:15]:
    flag = "✅涨停" if s['is_zt'] else f"{s['today_chg']:+.1f}%"
    print(f"  {s['code']} {s['name']:8s}  v1.1={s['p_v11']:.3f}→v1.4={s['p_v14']:.3f}  {flag}  lbc={s['lbc']} cb5={s['cb5']:+.2f}亿 cb1={s['cb1']:+.2f}亿 cb%={s['callback_pct']:.1f}%")

# 3. v1.4 加进来的 v1.1 中分票 (v1.1 < 0.5, v1.4 >= 0.55)
v14_added = [s for s in scored if s['p_v11'] < 0.5 and s['p_v14'] >= 0.55]
print(f"\n=== v1.4 加进来的 v1.1 中分票 (v1.1<0.5, v1.4≥0.55): {len(v14_added)} 只 ===")
zt_added = sum(1 for s in v14_added if s['is_zt'])
zt_rate_added = zt_added / max(1, len(v14_added))
all_chg_added = sum(s['today_chg'] for s in v14_added) / max(1, len(v14_added))
print(f"   涨停 {zt_added} ({zt_rate_added*100:.1f}%), 平均涨幅 {all_chg_added:+.2f}%")
for s in sorted(v14_added, key=lambda x: -x['p_v14'])[:15]:
    flag = "✅涨停" if s['is_zt'] else f"{s['today_chg']:+.1f}%"
    print(f"  {s['code']} {s['name']:8s}  v1.1={s['p_v11']:.3f}→v1.4={s['p_v14']:.3f}  {flag}  lbc={s['lbc']} cb5={s['cb5']:+.2f}亿")

# 4. 综合: v1.4 vs v1.1 在不同档的命中
print(f"\n=== 综合档命中率 ===")
print(f"{'档':<25}{'v1.1 n':<8}{'v1.1 涨停':<12}{'v1.4 n':<8}{'v1.4 涨停':<12}")
for tier_name, tier_fn_v11, tier_fn_v14 in [
    ("≥0.78 (v1.1 极强)", lambda p: p>=0.78, None),
    ("≥0.6 (v1.4 极强)", None, lambda p: p>=0.6),
    ("0.5-0.6", lambda p: 0.5<=p<0.6, lambda p: 0.5<=p<0.6),
    ("0.45-0.5", lambda p: 0.45<=p<0.5, lambda p: 0.45<=p<0.5),
    ("0.4-0.45", lambda p: 0.4<=p<0.45, lambda p: 0.4<=p<0.45),
]:
    v11_n = sum(1 for s in scored if tier_fn_v11 and tier_fn_v11(s['p_v11']))
    v11_zt = sum(1 for s in scored if tier_fn_v11 and tier_fn_v11(s['p_v11']) and s['is_zt'])
    v14_n = sum(1 for s in scored if tier_fn_v14 and tier_fn_v14(s['p_v14']))
    v14_zt = sum(1 for s in scored if tier_fn_v14 and tier_fn_v14(s['p_v14']) and s['is_zt'])
    v11_str = f"{v11_zt}/{v11_n}" if v11_n else "—"
    v14_str = f"{v14_zt}/{v14_n}" if v14_n else "—"
    v11_pct = f"({v11_zt/v11_n*100:.0f}%)" if v11_n else ""
    v14_pct = f"({v14_zt/v14_n*100:.0f}%)" if v14_n else ""
    print(f"  {tier_name:<25}{v11_n:<8}{v11_str+v11_pct:<12}{v14_n:<8}{v14_str+v14_pct:<12}")

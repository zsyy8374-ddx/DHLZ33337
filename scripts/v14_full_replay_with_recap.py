"""v1.4 完整 replay: 用 4-30 实战数据反推, 看 v1.4 能不能在 4-29 当时就避开雷
模拟 Dengxian 4-29 真实场景:
- 用 v1.4 重新打分 4-29 的 216 候选
- 按 v1.4 分档 (P_high=0.6, P_mid=0.45) 推送
- 看每档命中
- 统计: 比 v1.1 推送 (12 极强 0 涨停, 11 强 1 涨停) 有什么区别

输出: 一份"如果 4-29 用 v1.4 推送会发什么"的模拟报告
"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from predict_v14 import load_v14_model, predict_v14
from lr_v11_with_recent_rev_rate import extract_v11
from pathlib import Path

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')

with open(WORKSPACE / 'picks' / 'reversal_hits_full.jsonl') as f:
    for line in f:
        row = json.loads(line)
        if row.get('pick_date') == '2026-04-29':
            data = row; break

with open(WORKSPACE / 'picks' / 'reversal-v4-2026-04-29.json') as g:
    full = json.load(g)
cand_by_code = {c['code']: c for c in full['candidates']}

model_v14 = load_v14_model()
P_high = model_v14['P_high']  # 0.6
P_mid = model_v14['P_mid']    # 0.45
recent_5d, recent_10d, recent_20d = 0.28, 0.39, 0.45

scored = []
for r in data['results']:
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
        'code': r['code'], 'name': r.get('name', ''),
        'p_v11': r['lr_prob'], 'p_v14': p_ens,
        'p_v14_lr': p_lr_v14, 'p_v14_gb': p_gb,
        'is_zt': r.get('is_zt', False),
        'today_chg': r.get('today_chg', 0),
        'today_high': r.get('today_high', 0),
        'lbc': cand.get('d0_lbc', 1),
        'cb5': cand.get('cb5_main_avg', 0),
        'callback_pct': cand.get('callback_pct', 0),
        'd0_date': cand.get('d0_date', ''),
    })

print(f"📊 4-29 推送候选 (P>=0.4): {len(scored)} 只, 4-30 涨停 {sum(1 for s in scored if s['is_zt'])}")
print(f"📦 v1.4 阈值: P_high={P_high}, P_mid={P_mid}")

# 分档 + 详细
tier_a = [s for s in scored if s['p_v14'] >= P_high]
tier_b = [s for s in scored if P_mid <= s['p_v14'] < P_high]
tier_c = [s for s in scored if 0.35 <= s['p_v14'] < P_mid]

print(f"\n=== 用 v1.4 重新分档后会推送的 ===")
print(f"   极强档 (P≥{P_high}): {len(tier_a)} 只 — 4-30 涨停 {sum(1 for s in tier_a if s['is_zt'])} ({sum(1 for s in tier_a if s['is_zt'])/max(1,len(tier_a))*100:.1f}%)")
print(f"   强档   ({P_mid}≤P<{P_high}): {len(tier_b)} 只 — 4-30 涨停 {sum(1 for s in tier_b if s['is_zt'])} ({sum(1 for s in tier_b if s['is_zt'])/max(1,len(tier_b))*100:.1f}%)")
print(f"   关注档 (0.35≤P<{P_mid}): {len(tier_c)} 只 — 4-30 涨停 {sum(1 for s in tier_c if s['is_zt'])}")

print(f"\n=== v1.4 极强档 详情 ===")
for s in sorted(tier_a, key=lambda x: -x['p_v14']):
    flag = "✅" if s['is_zt'] else "❌"
    print(f"  {s['code']} {s['name']:8s} v1.4={s['p_v14']:.3f} (LR={s['p_v14_lr']:.2f},GB={s['p_v14_gb']:.2f})  {flag} {s['today_chg']:+5.2f}%  最高{s['today_high']:+.2f}%  lbc={s['lbc']} cb5={s['cb5']:+.2f}亿 cb%={s['callback_pct']:.1f}%")

print(f"\n=== v1.4 强档 详情 (Top 15) ===")
for s in sorted(tier_b, key=lambda x: -x['p_v14'])[:15]:
    flag = "✅" if s['is_zt'] else "❌"
    print(f"  {s['code']} {s['name']:8s} v1.4={s['p_v14']:.3f} (LR={s['p_v14_lr']:.2f},GB={s['p_v14_gb']:.2f})  {flag} {s['today_chg']:+5.2f}%  最高{s['today_high']:+.2f}%  lbc={s['lbc']} cb5={s['cb5']:+.2f}亿")

# 假设推送 = 极强 + 强 = 触摸涨停的 (today_high == 涨幅上限)
all_pushed = tier_a + tier_b
zt_pushed = sum(1 for s in all_pushed if s['is_zt'])
touched_zt = sum(1 for s in all_pushed if s['today_high'] >= 9.8)  # 接近涨停
avg_chg = sum(s['today_chg'] for s in all_pushed) / max(1, len(all_pushed))
avg_high = sum(s['today_high'] for s in all_pushed) / max(1, len(all_pushed))

print(f"\n=== 4-29 v1.4 推送会送出的极强+强档 ({len(all_pushed)} 只) 4-30 表现 ===")
print(f"   涨停: {zt_pushed}/{len(all_pushed)} = {zt_pushed/max(1,len(all_pushed))*100:.1f}%")
print(f"   摸涨停 (high>=9.8): {touched_zt}/{len(all_pushed)} = {touched_zt/max(1,len(all_pushed))*100:.1f}%")
print(f"   平均当日涨幅: {avg_chg:+.2f}%")
print(f"   平均当日最高: {avg_high:+.2f}%")

# 对比 v1.1 当时实际推送
v11_pushed = [s for s in scored if s['p_v11'] >= 0.6]  # v1.1 的强档+极强档 (P>=0.6)
v11_zt = sum(1 for s in v11_pushed if s['is_zt'])
v11_avg = sum(s['today_chg'] for s in v11_pushed) / max(1, len(v11_pushed))
v11_high = sum(s['today_high'] for s in v11_pushed) / max(1, len(v11_pushed))
print(f"\n   对比 v1.1 实际推送 (P≥0.6, {len(v11_pushed)} 只):")
print(f"     涨停: {v11_zt}/{len(v11_pushed)} = {v11_zt/max(1,len(v11_pushed))*100:.1f}%")
print(f"     平均涨幅: {v11_avg:+.2f}%")
print(f"     平均最高: {v11_high:+.2f}%")

# 结论
print(f"\n=== 净 alpha (v1.4 - v1.1) ===")
v14_net = avg_chg - v11_avg
print(f"   推送平均涨幅 净改善: {v14_net:+.2f}pp")
print(f"   推送涨停率 净改善: {zt_pushed/max(1,len(all_pushed))*100 - v11_zt/max(1,len(v11_pushed))*100:+.1f}pp")

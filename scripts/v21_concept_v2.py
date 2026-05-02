#!/usr/bin/env python3
"""V2.1 v2 — 修复 lookahead bias
用 D-1 (4-29) 当天各概念的"涨停股数 / 平均涨幅" 作为强度因子
不用 D_t (4-30) 的 outcome
"""
import json, urllib.request, time
from pathlib import Path
import collections

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')

with open(WS / 'backtest' / 'concepts_data.json') as f:
    concepts = json.load(f)

# 拉 4-29 全市场涨停股 + 涨幅排前 10% 的票
import warnings; warnings.filterwarnings('ignore')

# pywencai 拉 4-29 涨幅
import pywencai
print('🌐 拉 4-29 全市场涨幅...', flush=True)
df = pywencai.get(query='2026-04-29 涨跌幅', loop=True, timeout=120)
if df is None or isinstance(df, dict):
    print(f'❌ {df}'); exit(1)
print(f'拉到 {len(df)} 行', flush=True)

# 找涨幅列
chg_col = None
for c in df.columns:
    if '涨跌幅' in c and '20260429' in c:
        chg_col = c; break
if not chg_col:
    print(f'❌ 没找到 4-29 涨跌幅列, 列: {list(df.columns)}'); exit(1)

# 给每只票打 4-29 涨幅
chg_4_29 = {}
for _, row in df.iterrows():
    code = str(row.get('code', '')).strip()
    try: chg = float(row[chg_col])
    except: chg = None
    chg_4_29[code] = chg

print(f'  4-29 涨幅 valid: {sum(1 for v in chg_4_29.values() if v is not None)}', flush=True)

# 算每个概念的 4-29 强度: (涨停股数, 平均涨幅, 红盘率)
def is_zt(name, chg, code):
    if chg is None: return False
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5

# 拿股票名映射
name_map = {}
for _, row in df.iterrows():
    code = str(row.get('code', '')).strip()
    name = str(row.get('股票简称', '')).strip()
    name_map[code] = name

concept_4_29 = collections.defaultdict(lambda: {'n': 0, 'zt': 0, 'chg_sum': 0.0, 'chg_n': 0, 'green': 0})
for code, info in concepts.items():
    chg = chg_4_29.get(code)
    name = name_map.get(code, '')
    for c in info['concepts']:
        s = concept_4_29[c]
        s['n'] += 1
        if chg is not None:
            s['chg_sum'] += chg
            s['chg_n'] += 1
            if chg > 0: s['green'] += 1
            if is_zt(name, chg, code):
                s['zt'] += 1

# 强度排序: zt数 + 平均涨幅
print('\n=== 4-29 当日强度 Top 30 概念 ===')
print(f'{"概念":20} | n   | 涨停 | 红盘率 | avg涨幅')
print('-'*70)
ranked = []
for c, s in concept_4_29.items():
    if s['n'] < 10: continue  # 至少 10 只票才算
    avg_chg = s['chg_sum'] / max(1, s['chg_n'])
    green_rate = s['green'] / max(1, s['chg_n'])
    score = s['zt'] * 5 + avg_chg + green_rate * 10
    ranked.append((c, s['n'], s['zt'], green_rate, avg_chg, score))

ranked.sort(key=lambda x: -x[5])
for c, n, zt, green, avg, score in ranked[:30]:
    print(f'{c:20} | {n:>3} | {zt:>3} | {green*100:>4.0f}% | {avg:+.2f}% | score {score:.2f}')

# 选"4-29 强势" 概念集 (涨停数 ≥ 5 或 score 高的)
HOT_4_29 = {c for c, n, zt, _, _, score in ranked[:30] if zt >= 3 or score >= 8}
print(f'\n🔥 4-29 强势概念 (D-1, 真实可用 — 无 lookahead): {len(HOT_4_29)} 个')
print(f'  {sorted(HOT_4_29)[:20]}...')

# 重新给 4-29 v1.4 候选打 hot_4_29_n
with open(WS / 'backtest' / 'v18_test_4_30_real.json') as f:
    results_4_30 = json.load(f)['results']

for r in results_4_30:
    info = concepts.get(r['code'], {})
    r['concepts'] = info.get('concepts', [])
    r['hot_4_29_n'] = sum(1 for c in r['concepts'] if c in HOT_4_29)

# 测试: hot_4_29_n vs 4-30 涨停 (无 lookahead 真实信号)
print('\n=== hot_4_29_n 分布 (无 lookahead) ===')
zt_dist = collections.Counter(r['hot_4_29_n'] for r in results_4_30 if r['is_zt'])
no_dist = collections.Counter(r['hot_4_29_n'] for r in results_4_30 if not r['is_zt'])
for n in sorted(set(list(zt_dist.keys())+list(no_dist.keys()))):
    z = zt_dist.get(n, 0); no = no_dist.get(n, 0)
    print(f'  hot_4_29_n={n}: 涨停 {z}, 没涨停 {no}, 涨停率 {z/max(1,z+no)*100:.1f}%')

print('\n=== hot_4_29_n ≥ N (无 lookahead) ===')
for thr in [1, 2, 3, 4, 5]:
    sub = [r for r in results_4_30 if r['hot_4_29_n'] >= thr]
    z = sum(1 for r in sub if r['is_zt'])
    if sub:
        print(f'  hot_4_29 ≥ {thr}: n={len(sub)}, 涨停 {z} ({z/len(sub)*100:.1f}%)')

print('\n=== v1.8 + hot_4_29 联动 (无 lookahead) ===')
combos = [(0.7, 1), (0.7, 2), (0.65, 2), (0.6, 2), (0.5, 3), (0.4, 4)]
for p_thr, h_thr in combos:
    sub = [r for r in results_4_30 if r.get('p_v18', 0) >= p_thr and r['hot_4_29_n'] >= h_thr]
    z = sum(1 for r in sub if r['is_zt'])
    if sub:
        print(f'  P≥{p_thr} + hot_4_29≥{h_thr}: n={len(sub)}, 涨停 {z} ({z/len(sub)*100:.0f}%)')

# 重排 Top 20
print('\n=== v1.8 + 0.03 * hot_4_29 重排 Top 20 (无 lookahead) ===')
results_4_30.sort(key=lambda x: -(x.get('p_v18', 0) + 0.03 * x['hot_4_29_n']))
for i, r in enumerate(results_4_30[:20], 1):
    zt = '✅' if r['is_zt'] else '❌'
    print(f'  {i:>2}. {r["code"]} {r["name"][:8]:8} P={r["p_v18"]:.3f} hot_4_29={r["hot_4_29_n"]:>2} {zt}')

# 落档
out = WS / 'backtest' / 'v21_concept_v2.json'
with open(out, 'w') as f:
    json.dump({
        'hot_concepts_4_29': sorted(HOT_4_29),
        'concept_strength_4_29': {c: {'n': s['n'], 'zt': s['zt'], 'avg_chg': s['chg_sum']/max(1,s['chg_n']), 'green_rate': s['green']/max(1,s['chg_n'])} for c, s in concept_4_29.items() if s['n']>=10},
    }, f, ensure_ascii=False, indent=2)
print(f'\n💾 落档: {out}')

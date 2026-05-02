#!/usr/bin/env python3
"""V2.1 概念拉取 v2 — 单股 query 比 batch in() 更稳"""
import json, time, sys
import pywencai
from pathlib import Path
import warnings; warnings.filterwarnings('ignore')

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
OUT = WS / 'backtest' / 'concepts_data.json'

with open(WS / 'backtest' / 'v18_events_enriched.json') as f:
    events = json.load(f)['events']

all_codes = sorted({e['code'] for e in events})
print(f'总 unique 股票: {len(all_codes)}', flush=True)

existing = {}
if OUT.exists():
    with open(OUT) as f: existing = json.load(f)
    print(f'已有缓存: {len(existing)}', flush=True)

# 改方案 — 一次拉一批 50 个但用纯 code 不用 in()
# 实际上, 概念是相对稳定的 (不随日期变化), 一次性拉全市场更合理
print(f'\n🌐 拉全市场所属概念 (一次性, loop)', flush=True)

q = '所属概念 所属同花顺行业'
for retry in range(3):
    try:
        df = pywencai.get(query=q, loop=True, timeout=300)
        if df is not None and not isinstance(df, dict) and len(df) > 100:
            break
    except Exception as e:
        print(f'  ⚠️ retry {retry+1}: {e}', flush=True)
        time.sleep(5)
else:
    print('❌ 拉取失败'); sys.exit(1)

print(f'✅ 拉到 {len(df)} 行', flush=True)

all_data = dict(existing)
for _, row in df.iterrows():
    code = str(row.get('code', '')).strip()
    if not code: continue
    concepts_raw = row.get('所属概念', '')
    industry = row.get('所属同花顺行业', '')
    if isinstance(concepts_raw, str):
        concepts = [c.strip() for c in concepts_raw.split(';') if c.strip()]
    else:
        concepts = []
    all_data[code] = {
        'concepts': concepts,
        'industry': str(industry) if industry else '',
    }

with open(OUT, 'w') as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)
print(f'\n💾 总条数: {len(all_data)}', flush=True)

# 跟 events code 对比
events_codes = set(all_codes)
hit = sum(1 for c in events_codes if c in all_data)
print(f'events 覆盖率: {hit}/{len(events_codes)} = {hit/len(events_codes)*100:.0f}%', flush=True)

import collections
concept_count = collections.Counter()
for code, d in all_data.items():
    if code in events_codes:
        for c in d['concepts']:
            concept_count[c] += 1
print(f'\n📊 events 涉及股票的 Top 30 概念:')
for c, n in concept_count.most_common(30):
    print(f'  {c}: {n}')

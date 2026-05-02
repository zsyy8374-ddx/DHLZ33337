#!/usr/bin/env python3
"""跨模型信号融合 — daily picks (v2.5) ∩ reversal (v1.4) ∩ v1.8
找两个/三个模型同时看好的股, 这是高置信度信号

D-1 17:30 v2.5 daily picks 推 ~30 只 (next-day 候选)
D-1 17:35 v1.4 reversal 推 ~330 只 (回马枪候选)
D 9:25 v1.8 重排 reversal candidates 取 P≥0.8

交集分析:
- v2.5 ∩ v1.4: 两个独立系统都推 → 高置信度
- v1.8 高分 ∩ v2.5 推荐: 9:25 撮合也强 + 长期信号 → 极高置信度
"""
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))


def load_v25(date):
    """daily picks v2.5"""
    f = WS / 'picks' / f'{date}.json'
    if not f.exists(): return None
    with open(f) as fh:
        d = json.load(fh)
    return d.get('candidates', [])


def load_v14(date):
    """reversal v1.4 推送日期 = D-1, 但实际下一天是 D"""
    f = WS / 'picks' / f'reversal-v4-{date}.json'
    if not f.exists(): return None
    with open(f) as fh:
        d = json.load(fh)
    return d.get('candidates', [])


def load_v18(date):
    """v1.8 重排 (D 当天 9:25)"""
    f = WS / 'picks' / f'reversal-v18-{date}.json'
    if not f.exists(): return None
    with open(f) as fh:
        d = json.load(fh)
    return d.get('all_results', [])


def main():
    # 用 4-29 (D-1) v2.5 + v1.4, 4-30 (D) v1.8
    d_minus1 = sys.argv[1] if len(sys.argv) > 1 else '2026-04-29'
    d = sys.argv[2] if len(sys.argv) > 2 else '2026-04-30'
    
    print(f'🔍 跨模型信号融合: D-1={d_minus1}, D={d}', flush=True)
    
    v25 = load_v25(d_minus1)
    v14 = load_v14(d_minus1)
    v18 = load_v18(d)
    
    if not all([v25, v14, v18]):
        print(f'  v25={len(v25 or [])}, v14={len(v14 or [])}, v18={len(v18 or [])}')
        if not v25: print(f'  ❌ daily picks {d_minus1} 不存在')
        if not v14: print(f'  ❌ v1.4 {d_minus1} 不存在')
        if not v18: print(f'  ❌ v1.8 {d} 不存在')
        return
    
    print(f'  v2.5 daily picks ({d_minus1}): {len(v25)} 只', flush=True)
    print(f'  v1.4 reversal ({d_minus1}): {len(v14)} 只', flush=True)
    print(f'  v1.8 重排 ({d}): {len(v18)} 只', flush=True)
    
    v25_codes = {c['code']: c for c in v25}
    v14_codes = {c['code']: c for c in v14}
    v18_codes = {c['code']: c for c in v18}
    
    # 1. v2.5 ∩ v1.4 (两个独立系统都推)
    inter_25_14 = set(v25_codes) & set(v14_codes)
    print(f'\n=== v2.5 ∩ v1.4 ({len(inter_25_14)} 只) ===', flush=True)
    for code in inter_25_14:
        v25_d = v25_codes[code]
        v14_d = v14_codes[code]
        name = v25_d.get('name', v14_d.get('name', '?'))
        v25_p = v25_d.get('lr_prob', v25_d.get('prob', 0))
        v14_p = v14_d.get('lr_prob_with_boost', v14_d.get('lr_prob', 0))
        print(f'  {code} {name[:8]}: v2.5 P={v25_p:.3f}, v1.4 P={v14_p:.3f}')
    
    # 2. v1.8 高分 (P≥0.7) 中, 在 v2.5 里的
    v18_high = [r for r in v18 if r.get('p_v18', 0) >= 0.7]
    cross_18_25 = [r for r in v18_high if r['code'] in v25_codes]
    print(f'\n=== v1.8 P≥0.7 ∩ v2.5 ({len(cross_18_25)} 只) ⭐ 极高置信度 ===', flush=True)
    for r in cross_18_25:
        v25_d = v25_codes[r['code']]
        v25_p = v25_d.get('lr_prob', v25_d.get('prob', 0))
        zt = r.get('is_zt')
        chg = r.get('actual_chg', 'NA')
        print(f'  {r["code"]} {r.get("name","")[:8]}: v1.8 P={r.get("p_v18",0):.3f}, v2.5 P={v25_p:.3f}', end='')
        if zt is not None:
            zt_s = '✅' if zt else '❌'
            print(f', 4-30 {chg if isinstance(chg,str) else f"{chg:+.2f}%"} {zt_s}', end='')
        print()
    
    # 3. v1.8 P≥0.85 (top 极强) 都在哪
    v18_top = sorted([r for r in v18 if r.get('p_v18', 0) >= 0.85], key=lambda x: -x.get('p_v18',0))
    print(f'\n=== v1.8 P≥0.85 极强档 ({len(v18_top)} 只) ===', flush=True)
    for r in v18_top:
        in_v25 = '✓ in v2.5' if r['code'] in v25_codes else ''
        in_v14 = '✓ in v1.4' if r['code'] in v14_codes else ''
        print(f'  {r["code"]} {r.get("name","")[:8]}: v1.8 P={r.get("p_v18",0):.3f}  {in_v25}  {in_v14}')


if __name__ == '__main__':
    main()

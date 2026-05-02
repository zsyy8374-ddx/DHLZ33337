#!/usr/bin/env python3
"""v1.8 数据采集: 给 v12 events 拉 D_t 当天 9:25 集合竞价数据
- 输入: v18_events_with_dt.json (1479 events, 108 唯一 D_t 日期)
- 输出: v18_auc_data.json {date: {code: {auc fields}}}
"""
import json, time, sys, os
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# 静默 SSL warning
import urllib3
urllib3.disable_warnings()

import pywencai

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
SRC = WS / 'backtest' / 'v18_events_with_dt.json'
OUT = WS / 'backtest' / 'v18_auc_data.json'
CKPT = WS / 'backtest' / 'v18_auc_ckpt.json'

QUERY_TPL = '{date_yyyymmdd} 9:25 委买 委卖 委差 多空比 五档买盘 撮合价 成交额 流通股本 涨跌幅'

def main():
    with open(SRC) as f:
        data = json.load(f)
    dates = data['recent_dates']
    print(f'📊 待拉日期: {len(dates)}')
    print(f'  最早: {dates[0]}, 最晚: {dates[-1]}')
    
    # 加载 ckpt
    auc_data = {}
    done_dates = set()
    if CKPT.exists():
        with open(CKPT) as f:
            ck = json.load(f)
        auc_data = ck['data']
        done_dates = set(ck['done'])
        print(f'♻️ 续传: {len(done_dates)} 日期已完成')
    
    t0 = time.time()
    fail_dates = []
    for i, d in enumerate(dates):
        if d in done_dates: continue
        d_yyyymmdd = d.replace('-', '')
        q = QUERY_TPL.format(date_yyyymmdd=d_yyyymmdd)
        try:
            df = pywencai.get(query=q, loop=True, timeout=120)
            if df is None or isinstance(df, dict) or not len(df):
                print(f'  [{i+1}/{len(dates)}] {d}: 空 / dict')
                fail_dates.append(d)
                done_dates.add(d)
                continue
            
            # 提取我们需要的字段
            day_data = {}
            for _, row in df.iterrows():
                code = str(row.get('code', '')).strip()
                if not code: continue
                
                rec = {}
                for col in df.columns:
                    if d_yyyymmdd in col:
                        # 去掉日期标签
                        clean = col.replace(f'[{d_yyyymmdd} 09:25]', '').replace(f'[{d_yyyymmdd}]', '')
                        try:
                            v = float(row[col])
                            rec[clean] = v
                        except (TypeError, ValueError):
                            rec[clean] = row[col]
                
                day_data[code] = rec
            
            auc_data[d] = day_data
            done_dates.add(d)
            
            elapsed = time.time() - t0
            avg = elapsed / (i+1)
            eta = avg * (len(dates) - i - 1) / 60
            print(f'  [{i+1}/{len(dates)}] {d}: {len(day_data)} stocks, '
                  f'avg {avg:.1f}s/d, ETA {eta:.0f}min', flush=True)
            
            # 每 10 个落 ckpt
            if (i+1) % 10 == 0:
                with open(CKPT, 'w') as f:
                    json.dump({'data': auc_data, 'done': sorted(done_dates)}, f, ensure_ascii=False)
                print(f'  💾 ckpt @ {i+1}', flush=True)
        except Exception as e:
            print(f'  [{i+1}/{len(dates)}] {d}: ERROR {e}', flush=True)
            fail_dates.append(d)
            time.sleep(2)
            continue
        time.sleep(0.3)
    
    # final
    with open(OUT, 'w') as f:
        json.dump(auc_data, f, ensure_ascii=False)
    with open(CKPT, 'w') as f:
        json.dump({'data': auc_data, 'done': sorted(done_dates)}, f, ensure_ascii=False)
    print(f'\n✅ 完成 {len(auc_data)} 日期')
    if fail_dates:
        print(f'⚠️ 失败 {len(fail_dates)}: {fail_dates[:10]}...')

if __name__ == '__main__':
    main()

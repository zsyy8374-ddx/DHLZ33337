#!/usr/bin/env python3
"""v1.8 enrich: 给 v12 events 补 D_t 当天 9:25 集合竞价特征
- failed 事件 D_t = D0 + 5 交易日 (严格对齐 reversal 平均, 防泄漏)
- 输出: v18_events_enriched.json
"""
import json
from pathlib import Path
import collections

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
SRC_EVENTS = WS / 'backtest' / 'v18_events_with_dt.json'
SRC_AUC = WS / 'backtest' / 'v18_auc_data.json'
OUT = WS / 'backtest' / 'v18_events_enriched.json'


def main():
    print('📥 加载 events...', flush=True)
    with open(SRC_EVENTS) as f:
        d1 = json.load(f)
    events = d1['events']
    print(f'  events: {len(events)}')
    
    print('📥 加载 auc data (这个比较大)...', flush=True)
    with open(SRC_AUC) as f:
        auc = json.load(f)
    print(f'  auc days: {len(auc)}')
    
    # 给每个 event 加 9:25 字段
    enriched = 0
    skipped_reasons = collections.Counter()
    
    for e in events:
        dt = e.get('d_t_strict')
        if not dt:
            skipped_reasons['no_dt'] += 1
            continue
        if dt not in auc:
            skipped_reasons['dt_not_in_auc'] += 1
            continue
        day_data = auc[dt]
        code = str(e['code']).strip()
        if code not in day_data:
            skipped_reasons['code_not_in_day'] += 1
            continue
        rec = day_data[code]
        
        # 提取 9:25 字段 (列名清理后, 标准化)
        # 期望字段: 分时委买/委卖/委差/多空比/收盘价/成交量/成交额/换手率/涨跌幅:前复权/振幅
        #         流通a股/总股本/最新价
        def g(k, default=None):
            for kk in [k, k.replace(':前复权','').replace(':不复权','')]:
                if kk in rec:
                    v = rec[kk]
                    try: return float(v)
                    except (TypeError, ValueError): return None
            return default
        
        auc_buy = g('分时委买')
        auc_sell = g('分时委卖')
        auc_diff = g('分时委差')
        auc_ratio = g('分时多空比')
        auc_close = g('分时收盘价:不复权') or g('分时收盘价')
        auc_amt = g('分时成交额')
        auc_vol = g('分时成交量')
        auc_turn = g('分时换手率')
        auc_chg = g('分时涨跌幅:前复权') or g('分时涨跌幅')
        auc_open = g('分时开盘价:不复权') or g('分时开盘价')
        auc_high = g('分时最高价:不复权') or g('分时最高价')
        auc_low = g('分时最低价:不复权') or g('分时最低价')
        auc_amp = g('分时振幅')
        
        float_a = g('流通a股')
        total_a = g('总股本')
        latest_price = g('最新价')
        
        # 衍生特征
        # 1. 委买 / 流通盘 (≈ 隔夜单占比)
        buy_to_float = None
        if auc_buy is not None and float_a and float_a > 0:
            # 委买单位是手, 1手=100股
            buy_to_float = (auc_buy * 100) / float_a * 100  # %
        
        # 2. 委卖 / 流通盘
        sell_to_float = None
        if auc_sell is not None and float_a and float_a > 0:
            sell_to_float = (auc_sell * 100) / float_a * 100
        
        # 3. 9:25 成交额 / 流通市值 (≈ 开盘占比近似, 但用市值法)
        amt_to_mcap = None
        if auc_amt is not None and float_a and auc_close:
            # 流通市值 = 流通a股 * 收盘价 (用 D_t 9:25 撮合价做近似)
            mcap = float_a * auc_close
            if mcap > 0:
                amt_to_mcap = auc_amt / mcap * 100  # %
        
        # 4. 强开标志: 撮合涨>0.5% 且 多空比>1.5
        strong_open = 0
        if auc_chg is not None and auc_ratio is not None:
            if auc_chg > 0.5 and auc_ratio > 1.5:
                strong_open = 1
        
        # 5. 集合竞价价位 ≈ 涨停 (相对前收幅度)
        zt_open = 0
        if auc_chg is not None and auc_chg > 9.5:
            zt_open = 1
        
        # 写回
        e['auc_buy'] = auc_buy
        e['auc_sell'] = auc_sell
        e['auc_diff'] = auc_diff
        e['auc_ratio'] = auc_ratio
        e['auc_match_close'] = auc_close
        e['auc_amt'] = auc_amt
        e['auc_vol'] = auc_vol
        e['auc_turn'] = auc_turn
        e['auc_chg'] = auc_chg
        e['auc_amp'] = auc_amp
        e['auc_float_a'] = float_a
        e['auc_total_a'] = total_a
        e['auc_buy_to_float'] = buy_to_float
        e['auc_sell_to_float'] = sell_to_float
        e['auc_amt_to_mcap'] = amt_to_mcap
        e['auc_strong_open'] = strong_open
        e['auc_zt_open'] = zt_open
        
        enriched += 1
    
    print(f'\n📊 enriched: {enriched}/{len(events)}')
    print(f'  skipped: {dict(skipped_reasons)}')
    
    # 各 outcome 的 enrich 率
    by_oc = collections.Counter()
    enriched_by_oc = collections.Counter()
    for e in events:
        by_oc[e['outcome']] += 1
        if 'auc_buy' in e and e['auc_buy'] is not None:
            enriched_by_oc[e['outcome']] += 1
    print(f'\n  by outcome: total={dict(by_oc)}, enriched={dict(enriched_by_oc)}')
    
    # 落档
    with open(OUT, 'w') as f:
        json.dump({'events': events, 'recent_dates': d1.get('recent_dates', [])}, f, ensure_ascii=False)
    print(f'\n💾 落档: {OUT}')

if __name__ == '__main__':
    main()

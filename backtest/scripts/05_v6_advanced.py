"""
05: v6 系列 - 终极迭代
基于 v5 的诊断,进一步:
1. 加"市场宽度"过滤(当日上涨家数比例)
2. 加"持仓多日的多重退出"逻辑(止盈/止损/移动止损)
3. 探索"反向"思路: 阴线后首日反弹? 还是动量延续?
"""
import json, os, glob, statistics, sys
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
KLINE_DIR = os.path.join(DATA_DIR, 'kline')
RESULT_DIR = os.path.join(os.path.dirname(__file__), '..', 'results')

def ma(arr,n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr,n): return max(arr[-n:]) if len(arr)>=n else None
def llv(arr,n): return min(arr[-n:]) if len(arr)>=n else None

def rsi(closes, n=14):
    if len(closes) < n+1: return 50
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i]-closes[i-1]
        gains.append(max(ch,0)); losses.append(max(-ch,0))
    g = sum(gains[-n:])/n; l = sum(losses[-n:])/n
    if l==0: return 100
    return 100 - 100/(1+g/l)

def load_klines():
    out = {}
    for f in glob.glob(os.path.join(KLINE_DIR, '*.json')):
        code = os.path.basename(f).replace('.json','')
        try: out[code] = json.load(open(f))
        except: pass
    return out

# 市场宽度: 每日上涨家数比例
def build_market_breadth(klines):
    by_date = defaultdict(lambda: {'up':0,'total':0,'med_chg':[]})
    for code, bars in klines.items():
        for i,b in enumerate(bars):
            if i==0: continue
            prev = bars[i-1]['c']
            chg = (b['c']-prev)/prev*100
            by_date[b['date']]['total'] += 1
            if chg > 0: by_date[b['date']]['up'] += 1
            by_date[b['date']]['med_chg'].append(chg)
    
    out = {}
    for d, info in by_date.items():
        if info['total']<50: continue
        out[d] = {
            'breadth': info['up']/info['total']*100,
            'med_chg': statistics.median(info['med_chg']),
        }
    return out


# === v6.0 ===
def f_v6_0(bars, today, mkt):
    """v6.0: 严选 + 市场宽度过滤 + 阶段动量"""
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']; h=today['h']; v=today['v']; o=today['o']; l=today['l']
    
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 4): return False, 0, {}
    
    # 市场宽度: 当天上涨家数比例必须 > 50% (否则是逆势单兵作战)
    if mkt and mkt.get('breadth', 0) < 50: return False, 0, {'why':'breadth_low'}
    # 大盘中位涨幅 > -0.5%
    if mkt and mkt.get('med_chg', 0) < -0.5: return False, 0, {'why':'mkt_weak'}
    
    ma5=ma(closes,5); ma10=ma(closes,10); ma20=ma(closes,20)
    ma60=ma(closes,60); ma120=ma(closes,min(120,len(closes)))
    vol5=ma(vols,5); vol20=ma(vols,20)
    if not all([ma5,ma10,ma20,ma60,vol20]): return False, 0, {}
    
    # 核心条件
    if c <= ma10 or c <= ma20: return False, 0, {}
    
    ma20_5d_ago = ma(closes[-25:-5] if len(closes)>=25 else closes[:-5], 20)
    if not (ma20_5d_ago and ma20 > ma20_5d_ago * 1.005): return False, 0, {}
    
    ratio = v/vol20
    if not (1.3 < ratio < 2.2): return False, 0, {}
    
    # RSI 启动期 (50-65, 不要超买)
    closes_w = closes + [c]
    r = rsi(closes_w, 14)
    if not (50 < r < 68): return False, 0, {}
    
    # 阶段动量: 过去5日累涨 > 0 (确认上行)
    pct5 = (c/closes[-5]-1)*100
    if pct5 <= 0: return False, 0, {}
    # 但20日累涨不能太多
    pct20 = (c/closes[-20]-1)*100
    if pct20 > 15: return False, 0, {}
    
    # 收阳 + 收上半部
    if c <= o: return False, 0, {}
    if h>l and (h-c)/(h-l) > 0.4: return False, 0, {}
    
    # 距MA60 不远(<35%)
    if c/ma60 > 1.35: return False, 0, {}
    
    return True, 8, {'rsi':r,'ratio':ratio,'pct5':pct5,'pct20':pct20}


def f_v6_1(bars, today, mkt):
    """v6.1: v6.0 + 突破近20日新高(明确启动信号)"""
    p, s, dbg = f_v6_0(bars, today, mkt)
    if not p: return p, s, dbg
    
    highs = [b['h'] for b in bars]
    if today['c'] < hhv(highs[-20:], 20) * 0.99: return False, s, dict(dbg, why='no_break')
    return True, s+1, dbg


def f_v6_2(bars, today, mkt):
    """v6.2: 改方向 - 寻找'回踩MA10后反弹'(回调买点)"""
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']; v=today['v']
    
    today_pct = (c/closes[-1]-1)*100
    if not (0.5 < today_pct < 3.5): return False, 0, {}
    
    if mkt and mkt.get('breadth', 0) < 45: return False, 0, {}
    
    ma10 = ma(closes,10); ma20 = ma(closes,20); ma60 = ma(closes,60)
    if not all([ma10,ma20,ma60]): return False, 0, {}
    
    # 必须站MA20 + MA20 > MA60 (中期多头)
    if c <= ma20 or ma20 <= ma60*1.01: return False, 0, {}
    
    # 关键: 昨日或前日触及/接近MA10(回踩) + 今日反弹
    touched_ma10 = False
    for i in [-1, -2]:
        if i >= -len(lows) and lows[i] <= ma10 * 1.015:  # 触及MA10附近
            touched_ma10 = True; break
    if not touched_ma10: return False, 0, {}
    
    # 今日收阳上行
    if c <= closes[-1]: return False, 0, {}
    
    # 量能温和(不需要爆量,因为是回踩)
    vol20 = ma(vols,20)
    if not vol20: return False, 0, {}
    ratio = v/vol20
    if not (0.8 < ratio < 1.8): return False, 0, {}
    
    # RSI 没超买
    r = rsi(closes+[c], 14)
    if not (45 < r < 65): return False, 0, {}
    
    return True, 7, {'rsi':r,'ratio':ratio}


def f_v6_3(bars, today, mkt):
    """v6.3: 阶段强度 - 寻找'近10日跑赢大盘'的强势股启动"""
    if len(bars)<30: return False, 0, {}
    closes=[b['c'] for b in bars]; vols=[b['v'] for b in bars]
    c = today['c']; v = today['v']
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 4): return False, 0, {}
    
    if mkt and mkt.get('breadth', 0) < 50: return False, 0, {}
    
    ma10 = ma(closes,10); ma20 = ma(closes,20)
    if not (ma10 and ma20): return False, 0, {}
    if c <= ma10 or c <= ma20: return False, 0, {}
    ma20_prev = ma(closes[-25:-5] if len(closes)>=25 else closes[:-5], 20)
    if not (ma20_prev and ma20 > ma20_prev*1.01): return False, 0, {}
    
    vol20 = ma(vols,20)
    if not vol20: return False, 0, {}
    ratio = v/vol20
    if not (1.4 < ratio < 2.5): return False, 0, {}
    
    # 近10日跑赢市场: 个股10日涨幅 > 大盘10日涨幅 + 3%
    pct10 = (c/closes[-10]-1)*100 if len(closes)>=10 else 0
    if not (3 < pct10 < 18): return False, 0, {}
    
    r = rsi(closes+[c], 14)
    if not (52 < r < 68): return False, 0, {}
    
    return True, 6, {'rsi':r,'ratio':ratio,'pct10':pct10}


# === 回测带 T+1过滤 + 移动止损 ===
def backtest(formula_fn, klines, eval_dates, market_breadth, hold_days=[3,5,10]):
    hits_filtered = []
    hits_with_stop = []
    
    for code, bars in klines.items():
        date_idx = {b['date']:i for i,b in enumerate(bars)}
        for d in eval_dates:
            if d not in date_idx: continue
            i = date_idx[d]
            if i < 65: continue
            
            mkt = market_breadth.get(d, {})
            past = bars[:i]; today = bars[i]
            try:
                passed, score, dbg = formula_fn(past, today, mkt)
            except: continue
            if not passed: continue
            
            if i+1 >= len(bars): continue
            next_bar = bars[i+1]
            entry_signal = today['c']
            actual_entry = next_bar['o']
            op_pct = (actual_entry/entry_signal-1)*100
            if op_pct > 3 or op_pct < -3: continue  # T+1开盘过滤
            
            # 收益(无止损)
            f_returns = {}
            for hd in hold_days:
                if i+1+hd < len(bars):
                    f_returns[hd] = (bars[i+1+hd]['c']/actual_entry-1)*100
            hits_filtered.append({'date':d,'code':code,'entry':actual_entry,'returns':f_returns,'score':score})
            
            # 移动止损模拟: T+1买入,跌破-5%或破10日线先卖
            stop_returns = {}
            stop_price = actual_entry * 0.95  # 初始-5%
            for hd in hold_days:
                if i+1+hd >= len(bars): continue
                stopped = False
                hp = actual_entry  # 持仓最高价
                for j in range(i+1, i+1+hd+1):
                    bj = bars[j]
                    if bj['l'] <= stop_price:
                        stop_returns[hd] = (stop_price/actual_entry-1)*100
                        stopped = True; break
                    # 移动止损: 涨>5%后,止损上移到 -2% 保本
                    if bj['c'] > actual_entry*1.05:
                        new_stop = actual_entry * 0.98
                        if new_stop > stop_price: stop_price = new_stop
                    if bj['c'] > actual_entry*1.10:
                        new_stop = actual_entry * 1.03
                        if new_stop > stop_price: stop_price = new_stop
                    hp = max(hp, bj['c'])
                if not stopped:
                    stop_returns[hd] = (bars[i+1+hd]['c']/actual_entry-1)*100
            hits_with_stop.append({'date':d,'code':code,'entry':actual_entry,
                                   'returns':stop_returns,'score':score})
    
    return hits_filtered, hits_with_stop


def stats(hits, hold_days=[3,5,10]):
    if not hits: return {}
    out = {'n': len(hits)}
    for hd in hold_days:
        rs = [h['returns'][hd] for h in hits if hd in h['returns']]
        if not rs: continue
        wins = sum(1 for r in rs if r>0)
        out[f'T+{hd}'] = {
            'n': len(rs),
            'avg': round(statistics.mean(rs),2),
            'med': round(statistics.median(rs),2),
            'win': round(wins/len(rs)*100,1),
            'big_win': round(sum(1 for r in rs if r>5)/len(rs)*100,1),
            'big_loss': round(sum(1 for r in rs if r<-5)/len(rs)*100,1),
        }
    return out


def main():
    print("加载K线...")
    klines = load_klines()
    print(f"  {len(klines)} 只")
    
    print("构建市场宽度指标...")
    breadth = build_market_breadth(klines)
    print(f"  {len(breadth)} 个交易日")
    
    eval_dates = sorted(breadth.keys())
    eval_dates = eval_dates[max(0,len(eval_dates)-120):-12]
    print(f"评估期: {eval_dates[0]} ~ {eval_dates[-1]}")
    
    formulas = {'v6.0': f_v6_0, 'v6.1': f_v6_1, 'v6.2': f_v6_2, 'v6.3': f_v6_3}
    
    summary = {}
    for name, fn in formulas.items():
        print(f"\n=== {name} ===")
        no_stop, with_stop = backtest(fn, klines, eval_dates, breadth)
        s_no = stats(no_stop); s_st = stats(with_stop)
        summary[name] = {'no_stop': s_no, 'with_stop': s_st}
        
        print(f"  T+1过滤后命中 {len(no_stop)}")
        for tag, s in [('无止损', s_no), ('移动止损', s_st)]:
            t5 = s.get('T+5',{})
            t10 = s.get('T+10',{})
            print(f"  {tag} T+5: 胜{t5.get('win','-')}% 均{t5.get('avg','-')}% 大跌{t5.get('big_loss','-')}%")
            print(f"  {tag} T+10: 胜{t10.get('win','-')}% 均{t10.get('avg','-')}% 大涨{t10.get('big_win','-')}%")
    
    with open(os.path.join(RESULT_DIR, 'summary_v6.json'),'w') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*100}")
    print(f"📊 v6 系列总对比 (T+1开盘过滤 + 移动止损)")
    print(f"{'='*100}")
    print(f"{'版本':<8}{'命中':<8}{'T+5胜率':<10}{'T+5均':<10}{'T+10胜率':<10}{'T+10均':<10}{'大涨率':<8}{'大跌率':<8}")
    for name, s in summary.items():
        f5 = s['with_stop'].get('T+5',{})
        f10 = s['with_stop'].get('T+10',{})
        print(f"{name:<8}{s['with_stop'].get('n',0):<8}"
              f"{str(f5.get('win','-')):<10}{str(f5.get('avg','-')):<10}"
              f"{str(f10.get('win','-')):<10}{str(f10.get('avg','-')):<10}"
              f"{str(f10.get('big_win','-')):<8}{str(f10.get('big_loss','-')):<8}")

if __name__=='__main__':
    main()

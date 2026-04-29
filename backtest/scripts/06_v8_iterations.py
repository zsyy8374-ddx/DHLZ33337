"""
06: v8 系列 - 多因子打分 + ATR 过滤 + 连续性确认
基于 v7.1 痛点改进:
1. 加 ATR 波动率过滤
2. 多因子打分(不是硬过滤)
3. 连续性确认(昨日也接近满足)
4. 板块共振(用市场宽度代理)
"""
import json, os, glob, statistics
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

def atr(bars, n=14):
    """Average True Range"""
    if len(bars) < n+1: return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[i]['h']; l = bars[i]['l']; pc = bars[i-1]['c']
        tr = max(h-l, abs(h-pc), abs(l-pc))
        trs.append(tr)
    return sum(trs[-n:])/n

def load_klines():
    out = {}
    for f in glob.glob(os.path.join(KLINE_DIR, '*.json')):
        code = os.path.basename(f).replace('.json','')
        try: out[code] = json.load(open(f))
        except: pass
    return out

def build_market_breadth(klines):
    by_date = defaultdict(lambda: {'up':0,'total':0,'med_chg':[],'big_up':0})
    for code, bars in klines.items():
        for i,b in enumerate(bars):
            if i==0: continue
            prev = bars[i-1]['c']
            chg = (b['c']-prev)/prev*100
            by_date[b['date']]['total'] += 1
            if chg > 0: by_date[b['date']]['up'] += 1
            if chg > 3: by_date[b['date']]['big_up'] += 1
            by_date[b['date']]['med_chg'].append(chg)
    out = {}
    for d, info in by_date.items():
        if info['total']<100: continue
        out[d] = {
            'breadth': info['up']/info['total']*100,
            'med_chg': statistics.median(info['med_chg']),
            'big_up_pct': info['big_up']/info['total']*100,
        }
    return out


# === v8.0: 多因子打分模型 ===
def f_v8_0_score(bars, today, mkt):
    """
    v8.0 - 多因子加权打分,返回总分(0-100)
    通过阈值: total >= 70
    """
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']; h=today['h']; v=today['v']; o=today['o']; l=today['l']
    today_pct = (c/closes[-1]-1)*100
    
    # === 硬条件预筛 (不通过直接淘汰) ===
    # 当日涨幅 1-5% (放宽一点窗口)
    if not (1.0 < today_pct < 5): return False, 0, {}
    # 大盘环境
    if mkt and mkt.get('breadth', 0) < 45: return False, 0, {}
    if mkt and mkt.get('med_chg', 0) < -1: return False, 0, {}
    
    ma10=ma(closes,10); ma20=ma(closes,20); ma60=ma(closes,60); ma120=ma(closes,min(120,len(closes)))
    vol5=ma(vols,5); vol20=ma(vols,20)
    if not all([ma10,ma20,ma60,vol20]): return False, 0, {}
    
    # 站上 MA20 是必须 (基础趋势)
    if c <= ma20: return False, 0, {}
    
    # === 打分项 ===
    score = 0
    factors = {}
    
    # F1: 当日涨幅(2-3.5% 最佳, 加 15 分; 1.5-2 或 3.5-4 加 10 分; 边缘加5)
    if 2 < today_pct < 3.5: score += 15; factors['day_pct'] = 15
    elif 1.5 < today_pct < 4: score += 10; factors['day_pct'] = 10
    else: score += 5; factors['day_pct'] = 5
    
    # F2: 量比(1.5-2 最佳 加 15; 1.3-1.5 或 2-2.5 加 10)
    ratio = v/vol20
    if 1.5 < ratio < 2.0: score += 15; factors['vol_ratio'] = 15
    elif (1.3 < ratio < 1.5) or (2.0 < ratio < 2.5): score += 10; factors['vol_ratio'] = 10
    elif (1.1 < ratio < 1.3) or (2.5 < ratio < 3.0): score += 5; factors['vol_ratio'] = 5
    else: factors['vol_ratio'] = 0
    
    # F3: RSI(58-63 最佳 15; 55-58/63-65 10; 50-55/65-68 5)
    closes_w = closes + [c]
    r = rsi(closes_w, 14)
    if 58 < r < 63: score += 15; factors['rsi'] = 15
    elif 55 < r < 58 or 63 < r < 65: score += 10; factors['rsi'] = 10
    elif 50 < r < 55 or 65 < r < 68: score += 5; factors['rsi'] = 5
    else: factors['rsi'] = 0
    
    # F4: 5日动量(5-9% 最佳 15; 3-5/9-12 10; 0-3/12-15 5)
    pct5 = (c/closes[-5]-1)*100
    if 5 < pct5 < 9: score += 15; factors['mom5'] = 15
    elif 3 < pct5 < 5 or 9 < pct5 < 12: score += 10; factors['mom5'] = 10
    elif 0 < pct5 < 3 or 12 < pct5 < 15: score += 5; factors['mom5'] = 5
    else: factors['mom5'] = 0
    
    # F5: 20日累涨(温和 -3~15% 加 10; 15-25 加 5)
    pct20 = (c/closes[-20]-1)*100
    if -3 < pct20 < 15: score += 10; factors['mom20'] = 10
    elif 15 < pct20 < 25: score += 5; factors['mom20'] = 5
    else: factors['mom20'] = 0
    
    # F6: MA20 上行斜率(强上行加10, 平缓上行加5)
    ma20_5d = ma(closes[-25:-5] if len(closes)>=25 else closes[:-5], 20)
    if ma20_5d:
        slope_5d = (ma20/ma20_5d - 1)*100
        if slope_5d > 1.5: score += 10; factors['ma20_slope'] = 10
        elif slope_5d > 0.5: score += 5; factors['ma20_slope'] = 5
        else: factors['ma20_slope'] = 0
    else: factors['ma20_slope'] = 0
    
    # F7: 收盘强度(收K上半部 加10)
    if h>l:
        position = 1 - (h-c)/(h-l)
        if position > 0.7: score += 10; factors['close_strong'] = 10
        elif position > 0.5: score += 5; factors['close_strong'] = 5
        else: factors['close_strong'] = 0
    else: factors['close_strong'] = 5
    
    # F8: 突破新高(20日新高 加10, 10日新高 加5)
    if c > hhv(highs[-20:], 20)*0.99: score += 10; factors['breakout'] = 10
    elif c > hhv(highs[-10:], 10)*0.99: score += 5; factors['breakout'] = 5
    else: factors['breakout'] = 0
    
    # F9: ATR 波动率(适中=好,太大=危险)
    a = atr(bars, 14)
    if a and a/c < 0.04: score += 5; factors['atr'] = 5  # 低波动好
    elif a and a/c > 0.07: score -= 10; factors['atr'] = -10  # 高波动惩罚
    else: factors['atr'] = 0
    
    # F10: 大盘强度(大盘宽度>60 加5, >70 加10)
    if mkt:
        b = mkt.get('breadth', 50)
        if b > 70: score += 10; factors['mkt_strong'] = 10
        elif b > 60: score += 5; factors['mkt_strong'] = 5
        else: factors['mkt_strong'] = 0
    
    # F11: 不远离年线(c/MA60 < 1.3 加5)
    if c/ma60 < 1.3: score += 5; factors['not_high'] = 5
    elif c/ma60 > 1.5: score -= 10; factors['not_high'] = -10
    else: factors['not_high'] = 0
    
    # F12: 连续性 - 昨日也站MA20 (确认非偶发)
    if closes[-1] > ma(closes[:-1], 20): score += 5; factors['continuity'] = 5
    
    # 通过阈值
    passed = score >= 70
    return passed, score, {'factors':factors,'rsi':r,'ratio':ratio,'pct5':pct5,'pct20':pct20,'today_pct':today_pct}


# === v8.1: 在 v8.0 基础上 + 突破新高强制 ===
def f_v8_1(bars, today, mkt):
    p, s, dbg = f_v8_0_score(bars, today, mkt)
    if not p: return p, s, dbg
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    if today['c'] < hhv(highs[-20:], 20)*0.99: return False, s, dbg
    return True, s, dbg


# === v8.2: 在 v8.1 基础上 + 阈值提高到 80 ===
def f_v8_2(bars, today, mkt):
    p, s, dbg = f_v8_0_score(bars, today, mkt)
    if not p: return False, s, dbg
    if s < 80: return False, s, dbg
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    if today['c'] < hhv(highs[-20:], 20)*0.99: return False, s, dbg
    return True, s, dbg


# === v8.3: 多因子打分 + ATR 自适应止损 ===
def f_v8_3(bars, today, mkt):
    """v8.3 == v8.1 但样本更精,只挑 score>=75"""
    p, s, dbg = f_v8_0_score(bars, today, mkt)
    if not p: return False, s, dbg
    if s < 75: return False, s, dbg
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    if today['c'] < hhv(highs[-20:], 20)*0.99: return False, s, dbg
    return True, s, dbg


# === 回测 ===
def backtest(formula_fn, klines, eval_dates, market_breadth, hold_days=[1,3,5,10,20]):
    hits = []
    for code, bars in klines.items():
        date_idx = {b['date']:i for i,b in enumerate(bars)}
        for d in eval_dates:
            if d not in date_idx: continue
            i = date_idx[d]
            if i < 65: continue
            mkt = market_breadth.get(d, {})
            try:
                passed, score, dbg = formula_fn(bars[:i], bars[i], mkt)
            except: continue
            if not passed: continue
            if i+1 >= len(bars): continue
            next_bar = bars[i+1]
            actual_entry = next_bar['o']
            op_pct = (actual_entry/bars[i]['c']-1)*100
            if op_pct > 3 or op_pct < -3: continue
            ret = {}
            for hd in hold_days:
                if i+1+hd < len(bars):
                    ret[hd] = (bars[i+1+hd]['c']/actual_entry-1)*100
            hits.append({'date':d,'code':code,'op_pct':op_pct,'score':score,'returns':ret,'dbg':dbg})
    return hits


def stats(hits, hold_days=[1,3,5,10,20]):
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
    
    print("构建市场宽度...")
    breadth = build_market_breadth(klines)
    print(f"  {len(breadth)} 个交易日")
    
    eval_dates = sorted(breadth.keys())
    eval_dates = eval_dates[max(0,len(eval_dates)-120):-22]  # 留 22 天观察期
    print(f"评估期: {eval_dates[0]} ~ {eval_dates[-1]} ({len(eval_dates)}天)")
    
    formulas = {
        'v8.0': f_v8_0_score,  # 阈值 70
        'v8.1': f_v8_1,        # +突破
        'v8.2': f_v8_2,        # +突破 +阈值 80
        'v8.3': f_v8_3,        # +突破 +阈值 75
    }
    
    summary = {}
    for name, fn in formulas.items():
        print(f"\n=== {name} ===")
        hits = backtest(fn, klines, eval_dates, breadth)
        s = stats(hits)
        summary[name] = {'stats': s, 'count': len(hits)}
        with open(os.path.join(RESULT_DIR, f'hits_{name}.json'),'w') as f:
            json.dump(hits[:200], f, ensure_ascii=False, indent=1, default=str)
        
        print(f"  命中 {len(hits)}")
        for hd in [3,5,10,20]:
            t = s.get(f'T+{hd}',{})
            if t:
                print(f"  T+{hd}: 胜{t['win']}% 均{t['avg']}% 中{t['med']}% 大涨{t['big_win']}% 大跌{t['big_loss']}%")
    
    with open(os.path.join(RESULT_DIR, 'summary_v8.json'),'w') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*100}")
    print(f"📊 v8 系列总对比")
    print(f"{'='*100}")
    print(f"{'版本':<8}{'命中':<8}{'T+5胜':<10}{'T+5均':<10}{'T+10胜':<10}{'T+10均':<10}{'T+20均':<10}{'大涨率':<8}{'大跌率':<8}")
    for name, s in summary.items():
        ss = s['stats']
        f5 = ss.get('T+5',{}); f10 = ss.get('T+10',{}); f20 = ss.get('T+20',{})
        print(f"{name:<8}{s['count']:<8}"
              f"{str(f5.get('win','-')):<10}{str(f5.get('avg','-')):<10}"
              f"{str(f10.get('win','-')):<10}{str(f10.get('avg','-')):<10}"
              f"{str(f20.get('avg','-')):<10}"
              f"{str(f20.get('big_win','-')):<8}{str(f20.get('big_loss','-')):<8}")

if __name__=='__main__':
    main()

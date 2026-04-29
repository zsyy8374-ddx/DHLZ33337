"""
v9: 在 v7.1 硬条件基础上加分层
1. v9.0: v7.1 硬条件 + 全样本验证(1494只)
2. v9.1: v7.1 + ATR<5% (排除高波动)
3. v9.2: v7.1 + 换手代理(量/流通股估算)
4. v9.3: v7.1 + 连续2日满足(强信号)
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
    if len(bars) < n+1: return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[i]['h']; l = bars[i]['l']; pc = bars[i-1]['c']
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs[-n:])/n

def load_klines():
    out = {}
    for f in glob.glob(os.path.join(KLINE_DIR, '*.json')):
        code = os.path.basename(f).replace('.json','')
        try: out[code] = json.load(open(f))
        except: pass
    return out

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
        if info['total']<100: continue
        out[d] = {'breadth': info['up']/info['total']*100,
                  'med_chg': statistics.median(info['med_chg'])}
    return out


def f_v7_1_core(bars, today, mkt):
    """v7.1 核心硬条件 - 不变"""
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']; h=today['h']; v=today['v']; o=today['o']; l=today['l']
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 4): return False, 0, {}
    
    if mkt and mkt.get('breadth', 0) < 50: return False, 0, {}
    if mkt and mkt.get('med_chg', 0) < -0.3: return False, 0, {}
    
    ma10=ma(closes,10); ma20=ma(closes,20); ma60=ma(closes,60)
    vol20=ma(vols,20)
    if not all([ma10,ma20,ma60,vol20]): return False, 0, {}
    if c <= ma10 or c <= ma20: return False, 0, {}
    
    ma20_5d_ago = ma(closes[-25:-5] if len(closes)>=25 else closes[:-5], 20)
    if not (ma20_5d_ago and ma20 > ma20_5d_ago * 1.005): return False, 0, {}
    
    ratio = v/vol20
    if not (1.3 < ratio < 2.2): return False, 0, {}
    
    closes_w = closes + [c]
    r = rsi(closes_w, 14)
    if not (55 < r < 65): return False, 0, {}
    
    pct5 = (c/closes[-5]-1)*100
    if not (4 < pct5 < 11): return False, 0, {}
    
    pct20 = (c/closes[-20]-1)*100
    if not (-3 < pct20 < 18): return False, 0, {}
    
    if c <= o: return False, 0, {}
    if h>l and (h-c)/(h-l) > 0.4: return False, 0, {}
    if c/ma60 > 1.35: return False, 0, {}
    
    if c < hhv(highs[-20:], 20) * 0.99: return False, 0, {}
    
    return True, 10, {'rsi':r,'ratio':ratio,'pct5':pct5,'pct20':pct20}


# v9.0: 纯 v7.1 在全样本上验证
f_v9_0 = f_v7_1_core


def f_v9_1(bars, today, mkt):
    """v9.1: v7.1 + ATR/价格 < 4% (排除高波动)"""
    p, s, dbg = f_v7_1_core(bars, today, mkt)
    if not p: return False, s, dbg
    a = atr(bars, 14)
    if a is None: return False, s, dbg
    c = today['c']
    if a/c > 0.04: return False, s, dict(dbg, atr_ratio=a/c)
    return True, s, dict(dbg, atr_ratio=a/c)


def f_v9_2(bars, today, mkt):
    """v9.2: v7.1 + 量稳定性(VOL5/VOL20 在 1.0-2.0,即近期量稳)"""
    p, s, dbg = f_v7_1_core(bars, today, mkt)
    if not p: return False, s, dbg
    vols = [b['v'] for b in bars]
    vol5 = ma(vols,5); vol20 = ma(vols,20)
    if not (vol5 and vol20): return False, s, dbg
    ratio_vol = vol5/vol20
    if not (1.0 < ratio_vol < 2.0): return False, s, dbg
    return True, s, dict(dbg, vol5_20=ratio_vol)


def f_v9_3(bars, today, mkt):
    """v9.3: v7.1 + 昨日也站MA20且接近满足(连续启动)"""
    p, s, dbg = f_v7_1_core(bars, today, mkt)
    if not p: return False, s, dbg
    closes = [b['c'] for b in bars]
    ma20_y = ma(closes[:-1], 20)
    if not (ma20_y and closes[-1] > ma20_y): return False, s, dbg
    return True, s, dbg


def f_v9_4(bars, today, mkt):
    """v9.4: 全部 v9.1+v9.2+v9.3 加总"""
    p, s, dbg = f_v9_1(bars, today, mkt)
    if not p: return False, s, dbg
    p, s, dbg = f_v9_2(bars, today, mkt)
    if not p: return False, s, dbg
    return f_v9_3(bars, today, mkt)


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
            hits.append({'date':d,'code':code,'op_pct':op_pct,'returns':ret,'dbg':dbg})
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
    
    eval_dates = sorted(breadth.keys())
    eval_dates = eval_dates[max(0,len(eval_dates)-120):-22]
    print(f"评估期: {eval_dates[0]} ~ {eval_dates[-1]}")
    
    formulas = {
        'v9.0': f_v9_0,  # = v7.1 全样本
        'v9.1': f_v9_1,  # +ATR过滤
        'v9.2': f_v9_2,  # +量稳定
        'v9.3': f_v9_3,  # +连续性
        'v9.4': f_v9_4,  # 全部加上
    }
    
    summary = {}
    for name, fn in formulas.items():
        print(f"\n=== {name} ===")
        hits = backtest(fn, klines, eval_dates, breadth)
        s = stats(hits)
        summary[name] = {'stats': s, 'count': len(hits)}
        with open(os.path.join(RESULT_DIR, f'hits_{name}.json'),'w') as f:
            json.dump(hits[:100], f, ensure_ascii=False, indent=1, default=str)
        print(f"  命中 {len(hits)}")
        for hd in [3,5,10,20]:
            t = s.get(f'T+{hd}',{})
            if t:
                print(f"  T+{hd}: 胜{t['win']}% 均{t['avg']}% 大涨{t['big_win']}% 大跌{t['big_loss']}%")
    
    with open(os.path.join(RESULT_DIR, 'summary_v9.json'),'w') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*100}")
    print(f"📊 v9 系列对比 (1494只全样本)")
    print(f"{'='*100}")
    print(f"{'版本':<8}{'命中':<8}{'T+5胜':<8}{'T+5均':<8}{'T+10胜':<8}{'T+10均':<8}{'T+20均':<8}{'大涨率':<8}{'大跌率':<8}")
    for name, s in summary.items():
        ss = s['stats']
        f5 = ss.get('T+5',{}); f10 = ss.get('T+10',{}); f20 = ss.get('T+20',{})
        print(f"{name:<8}{s['count']:<8}"
              f"{str(f5.get('win','-')):<8}{str(f5.get('avg','-')):<8}"
              f"{str(f10.get('win','-')):<8}{str(f10.get('avg','-')):<8}"
              f"{str(f20.get('avg','-')):<8}"
              f"{str(f20.get('big_win','-')):<8}{str(f20.get('big_loss','-')):<8}")

if __name__=='__main__':
    main()

"""
04: v5 系列迭代 - 基于诊断结果的真正改进
核心改变:
1. 加大盘环境过滤(大盘趋势向下,不选股)
2. 加 T+1 开盘价过滤(高开>3%放弃,1%-3%才介入)
3. 强调"启动初期"特征:RSI不超买、距离MA60不远
4. 不再追求最多命中,追求高胜率少而精
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

# 大盘指数(用上证综指代理) - 用所有股票收盘价加权代理
def build_market_index(klines):
    """简易市场指数: 每天所有票收盘价中位数变化率"""
    by_date = defaultdict(list)
    for code, bars in klines.items():
        for b in bars:
            by_date[b['date']].append(b['c'])
    dates = sorted(by_date.keys())
    # 用每日收盘价的相对变化构建
    prev_med = None
    idx = {}
    cum = 1000
    for d in dates:
        med = statistics.median(by_date[d])
        if prev_med:
            cum *= med/prev_med
        idx[d] = cum
        prev_med = med
    return idx, dates

# 公式 v5.0
def f_v5_0(bars, today, market_state):
    """v5.0: 严选 + 大盘过滤 + 开盘价过滤(在评估时用)"""
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c = today['c']; h = today['h']; v = today['v']; o=today['o']; l=today['l']
    
    today_pct = (c/closes[-1]-1)*100
    
    # 当日涨幅 1.5%-5% (温和启动,不要爆量)
    if not (1.5 < today_pct < 5): return False, 0, {'why':'pct_out'}
    
    # 大盘环境: 5日大盘上涨, 否则放弃
    if market_state.get('ma5_up', True) is False:
        return False, 0, {'why':'market_weak'}
    
    ma5=ma(closes,5); ma10=ma(closes,10); ma20=ma(closes,20)
    ma60=ma(closes,60); ma120=ma(closes,min(120,len(closes)))
    vol5=ma(vols,5); vol20=ma(vols,20)
    if not all([ma5,ma10,ma20,ma60,vol20]): return False, 0, {}
    
    closes_w = closes + [c]; highs_w = highs + [h]; lows_w = lows + [l]; vols_w = vols + [v]
    
    flags = []
    
    # 1. 站上MA20 (基础趋势)
    flags.append(c > ma20)
    # 2. MA20 上行
    ma20_5d = ma(closes[-25:-5] if len(closes)>=25 else closes[:-5], 20)
    flags.append(ma20_5d and ma20 > ma20_5d * 1.005)
    # 3. 当日量比 1.3-2.5 (温和放量,排除暴量出货)
    ratio = v/vol20
    flags.append(1.3 < ratio < 2.5)
    # 4. 平台整理: 过去20日振幅<20%
    flags.append((hhv(highs[-20:],20)/llv(lows[-20:],20)-1)*100 < 20)
    # 5. 收阳: c > o
    flags.append(c > o)
    # 6. 收盘强势: 收在K线上半部 (h-c)/(h-l) < 0.35
    if h>l: flags.append((h-c)/(h-l) < 0.35)
    else: flags.append(True)
    # 7. RSI 不超买: <70
    r = rsi(closes_w, 14)
    flags.append(r < 70)
    # 8. 距MA60距离: c/ma60 < 1.4 (排除过度乖离)
    flags.append(c/ma60 < 1.4)
    # 9. 20日累涨 -3% ~ +18% (启动初期,涨幅有限)
    pct20 = (c/closes[-20]-1)*100
    flags.append(-3 < pct20 < 18)
    # 10. 突破近10日高 (强弱锚点)
    flags.append(c > hhv(highs[-10:], 10) * 0.99)
    
    score = sum(flags)
    return score >= 9, score, {'flags':flags,'today_pct':today_pct,'rsi':r,'ratio':ratio}


def f_v5_1(bars, today, market_state):
    """v5.1: 在 v5.0 基础上加 'MACD零轴上方' 和 '量价齐升' 共振"""
    base_passed, base_score, dbg = f_v5_0(bars, today, market_state)
    if not base_passed: return False, base_score, dbg
    
    closes=[b['c'] for b in bars]
    
    # MACD
    def ema(arr,n):
        k=2/(n+1); e=arr[0]; out=[e]
        for x in arr[1:]:
            e=x*k+e*(1-k); out.append(e)
        return out
    closes_w = closes + [today['c']]
    e12 = ema(closes_w,12); e26 = ema(closes_w,26)
    if len(e12)<27: return False, base_score, dbg
    dif = e12[-1]-e26[-1]
    dif_arr = [a-b for a,b in zip(e12,e26)]
    dea_arr = ema(dif_arr,9)
    
    # MACD 零轴上方 + DIF 上行
    if dif <= 0: return False, base_score, dict(dbg, why='macd_neg')
    if dif_arr[-1] <= dif_arr[-2]: return False, base_score, dict(dbg, why='dif_down')
    
    return True, base_score+1, dbg


def f_v5_2(bars, today, market_state):
    """v5.2: v5.1 + 涨幅范围更窄 1.5-3.5% + 量比更窄 1.3-2.0"""
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]
    c = today['c']; v = today['v']
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 3.5): return False, 0, {'why':'pct_strict'}
    
    vol20 = ma([b['v'] for b in bars],20)
    ratio = v/vol20 if vol20 else 0
    if not (1.3 < ratio < 2.0): return False, 0, {'why':'vol_strict'}
    
    return f_v5_1(bars, today, market_state)


def f_v5_3(bars, today, market_state):
    """v5.3: 极简版 - 只要4个核心条件
    1. 当日 1.5-4% 温和涨
    2. 站MA10/MA20 + MA20 上行
    3. 量比1.3-2.2
    4. RSI 50-65 (启动期)
    """
    if len(bars)<30: return False, 0, {}
    closes=[b['c'] for b in bars]
    c = today['c']; v = today['v']
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 4): return False, 0, {}
    
    ma10 = ma(closes,10); ma20 = ma(closes,20)
    if not (ma10 and ma20): return False, 0, {}
    if c <= ma10 or c <= ma20: return False, 0, {}
    ma20_prev = ma(closes[-25:-5] if len(closes)>=25 else closes[:-5], 20)
    if not (ma20_prev and ma20 > ma20_prev*1.005): return False, 0, {}
    
    vol20 = ma([b['v'] for b in bars],20)
    if not vol20: return False, 0, {}
    ratio = v/vol20
    if not (1.3 < ratio < 2.2): return False, 0, {}
    
    closes_w = closes + [c]
    r = rsi(closes_w, 14)
    if not (50 < r < 70): return False, 0, {}
    
    return True, 4, {'rsi':r, 'ratio':ratio}


# T+1 开盘价过滤 (在回测时使用)
def t1_filter(entry, next_bar):
    """T+1 开盘 0.5% ~ 3.0% 才进场, 高开>3%放弃"""
    if not next_bar: return False
    op_pct = (next_bar['o']/entry-1)*100
    return -1.5 < op_pct < 3.0  # 不能高开太多, 略低开也行


def backtest_with_t1_filter(formula_fn, klines, eval_dates, market_idx, hold_days=[3,5,10]):
    """带T+1过滤的回测"""
    hits_raw = []  # 公式选出
    hits_filtered = []  # T+1过滤后实际买入
    
    market_dates = sorted(market_idx.keys())
    market_idx_pos = {d:i for i,d in enumerate(market_dates)}
    
    for code, bars in klines.items():
        date_idx = {b['date']:i for i,b in enumerate(bars)}
        for d in eval_dates:
            if d not in date_idx: continue
            i = date_idx[d]
            if i < 65: continue
            
            # 大盘状态
            mi = market_idx_pos.get(d, None)
            if mi is None or mi < 5: continue
            mkt5 = [market_idx[market_dates[mi-j]] for j in range(5,0,-1)]
            mkt5.append(market_idx[d])
            ma5_up = mkt5[-1] > ma(mkt5, 5)
            market_state = {'ma5_up': ma5_up}
            
            past = bars[:i]; today = bars[i]
            try:
                passed, score, dbg = formula_fn(past, today, market_state)
            except: continue
            if not passed: continue
            
            entry = today['c']
            # 不带T+1过滤的收益
            raw_returns = {}
            for hd in hold_days:
                if i+hd < len(bars):
                    raw_returns[hd] = (bars[i+hd]['c']/entry-1)*100
            hits_raw.append({'date':d,'code':code,'entry':entry,'returns':raw_returns,'score':score})
            
            # T+1 过滤
            if i+1 >= len(bars): continue
            next_bar = bars[i+1]
            if not t1_filter(entry, next_bar): continue
            actual_entry = next_bar['o']  # 用 T+1 开盘价买入
            f_returns = {}
            for hd in hold_days:
                if i+1+hd < len(bars):
                    f_returns[hd] = (bars[i+1+hd]['c']/actual_entry-1)*100
                # 加 -7% 止损模拟
            hits_filtered.append({'date':d,'code':code,'signal_close':entry,'actual_entry':actual_entry,
                                  'returns':f_returns,'score':score})
    
    return hits_raw, hits_filtered


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
    
    print("构建市场指数...")
    market_idx, market_dates = build_market_index(klines)
    print(f"  {len(market_dates)} 个交易日")
    
    eval_dates = market_dates[max(0,len(market_dates)-120):-12]
    print(f"评估期: {eval_dates[0]} ~ {eval_dates[-1]}")
    
    formulas = {
        'v5.0': f_v5_0,
        'v5.1': f_v5_1,
        'v5.2': f_v5_2,
        'v5.3': f_v5_3,
    }
    
    summary = {}
    for name, fn in formulas.items():
        print(f"\n=== {name} ===")
        raw, filt = backtest_with_t1_filter(fn, klines, eval_dates, market_idx)
        s_raw = stats(raw); s_filt = stats(filt)
        summary[name] = {'raw': s_raw, 'filtered': s_filt}
        
        print(f"  原始命中 {len(raw)}, T+1过滤后 {len(filt)} (留 {len(filt)*100/max(len(raw),1):.0f}%)")
        if s_raw.get('T+5'):
            print(f"  原始 T+5: 胜{s_raw['T+5']['win']}% 均{s_raw['T+5']['avg']}% 中{s_raw['T+5']['med']}%")
        if s_filt.get('T+5'):
            print(f"  过滤 T+5: 胜{s_filt['T+5']['win']}% 均{s_filt['T+5']['avg']}% 中{s_filt['T+5']['med']}%")
        if s_filt.get('T+10'):
            print(f"  过滤T+10: 胜{s_filt['T+10']['win']}% 均{s_filt['T+10']['avg']}% 中{s_filt['T+10']['med']}%")
    
    with open(os.path.join(RESULT_DIR, 'summary_v5.json'),'w') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    # 对比表
    print(f"\n{'='*90}")
    print(f"📊 v5 系列对比 (T+1开盘过滤后实战收益)")
    print(f"{'='*90}")
    print(f"{'版本':<8}{'命中':<8}{'T+3胜率':<10}{'T+3均':<10}{'T+5胜率':<10}{'T+5均':<10}{'T+10胜率':<10}{'T+10均':<10}")
    for name, s in summary.items():
        f5 = s['filtered'].get('T+5',{})
        f3 = s['filtered'].get('T+3',{})
        f10 = s['filtered'].get('T+10',{})
        print(f"{name:<8}{s['filtered'].get('n',0):<8}"
              f"{str(f3.get('win','-')):<10}{str(f3.get('avg','-')):<10}"
              f"{str(f5.get('win','-')):<10}{str(f5.get('avg','-')):<10}"
              f"{str(f10.get('win','-')):<10}{str(f10.get('avg','-')):<10}")

if __name__=='__main__':
    main()

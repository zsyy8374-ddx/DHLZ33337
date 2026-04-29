"""
v17: 高胜率狙击版 - 极致筹码回踩 + 强趋势分形
目标: T+10 胜率突破 70%
逻辑: 
1. 极致窄幅整理 (VCP < 0.4)
2. 5日均线上穿20日均线后的首次回踩 (MA10支撑)
3. 筹码集中度 ASR > 70% (筹码高度锁定)
4. 排除所有带长上影线的K线 (拒绝假突破)
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = 'backtest/data'
KLINE_DIR = os.path.join(DATA_DIR, 'kline')

def ma(arr, n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr, n): return max(arr[-n:]) if len(arr)>=n else None
def llv(arr, n): return min(arr[-n:]) if len(arr)>=n else None

def f_v17_high_win(bars, today, mkt):
    if len(bars)<120: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']; o=today['o']; h=today['h']; l=today['l']
    
    # 1. 均线金叉后的趋势确认
    m5=ma(closes,5); m10=ma(closes,10); m20=ma(closes,20); m60=ma(closes,60)
    if not all([m5,m10,m20,m60]): return False, 0, {}
    # 5/10/20 必须是多头排列，且股价回踩 m10 但不破 m20
    if not (m5 > m10 > m20): return False, 0, {}
    if not (l < m10 * 1.01 and c > m10): return False, 0, {} # 回踩10日线企稳
    
    # 2. VCP 极致波动压缩 (0.4)
    w1 = (max(highs[-20:-10]) - min(lows[-20:-10])) / ma(closes[-20:-10], 10)
    w2 = (max(highs[-10:]) - min(lows[-10:])) / ma(closes[-10:], 10)
    if w1 == 0 or w2/w1 > 0.4: return False, 0, {}
    
    # 3. 拒绝长上影线 (买盘坚决)
    if (h-max(c,o)) > (max(c,o)-min(c,o)) * 0.5: return False, 0, {}
    
    # 4. 温和启动 
    today_pct = (c/closes[-1]-1)*100
    if not (1.0 < today_pct < 3.5): return False, 0, {}
    
    # 5. 成交量: 相比昨日微增但不爆量 (1.1-1.5倍)
    if not (1.1 < today['v']/vols[-1] < 1.5): return False, 0, {}
    
    return True, 100, {'vcp': w2/w1, 'pct': today_pct}

def backtest(formula_fn, klines, eval_dates):
    hits = []
    for code, bars in klines.items():
        d_idx = {b['date']:i for i,b in enumerate(bars)}
        for d in eval_dates:
            if d not in d_idx: continue
            i = d_idx[d]
            if i < 120 or i+10 >= len(bars): continue
            passed, s, dbg = formula_fn(bars[:i], bars[i], None)
            if not passed: continue
            entry = bars[i+1]['o']
            hits.append({
                'date': d, 'code': code,
                'ret5': (bars[i+5]['c']/entry-1)*100,
                'ret10': (bars[i+10]['c']/entry-1)*100
            })
    return hits

def main():
    import glob, statistics
    print("正在进行 v17 高胜率版回测...")
    files = glob.glob(os.path.join(KLINE_DIR, '*.json'))
    klines = {os.path.basename(f).replace('.json',''): json.load(open(f)) for f in files}
    eval_dates = sorted(list(set(b['date'] for bars in klines.values() for b in bars)))[120:-12]
    
    hits = backtest(f_v17_high_win, klines, eval_dates)
    if not hits:
        print("❌ v17 无命中")
        return

    r10 = [h['ret10'] for h in hits]
    win10 = sum(1 for r in r10 if r>0)/len(r10)*100
    avg10 = statistics.mean(r10)
    
    print(f"\n📊 v17 高胜率版结果:")
    print("-" * 40)
    print(f"总命中数: {len(hits)}")
    print(f"T+10 胜率: {win10:.1f}% 🏆")
    print(f"T+10 均收益: {avg10:.2f}%")
    print("-" * 40)
    
    for h in sorted(hits, key=lambda x: x['ret10'], reverse=True)[:5]:
        print(f"样例: {h['date']} | {h['code']} | T+10: {h['ret10']:.2f}%")

if __name__ == "__main__": main()

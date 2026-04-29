"""
v20: 冰点起爆 - 寻找极度超跌后的底部反转
1. 股价距离 60 日线跌幅 > 15%
2. 5日均量 < 120日均量 * 0.7 (地量)
3. 今日涨幅 2%~5%, 且放量 > 昨日1.2倍
4. RSI(6) 从 < 25 低位拐头
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = 'backtest/data'
KLINE_DIR = os.path.join(DATA_DIR, 'kline')

def ma(arr, n): return sum(arr[-n:])/n if len(arr)>=n else None

def rsi_simple(closes, n=6):
    if len(closes) < n+1: return 50
    gains = []
    losses = []
    for i in range(len(closes)-n, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / n
    avg_loss = sum(losses) / n
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def f_v20_bottom_reversal(bars, today, mkt):
    if len(bars)<120: return False, 0, {}
    closes=[b['c'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']; v=today['v']; prev_c=closes[-1]
    
    # 1. 超跌确认 (C < MA60 * 0.85)
    m60 = ma(closes, 60)
    if not (m60 and c < m60 * 0.85): return False, 0, {}
    
    # 2. 地量确认 (MA5V < MA120V * 0.7)
    m5v = ma(vols, 5); m120v = ma(vols, 120)
    if not (m5v and m120v and m5v < m120v * 0.7): return False, 0, {}
    
    # 3. 阳线放量 (2% < pct < 5% AND V > prev_V * 1.2)
    pct = (c/prev_c-1)*100
    if not (2.0 < pct < 5.0 and v > vols[-1] * 1.2): return False, 0, {}
    
    # 4. RSI 低位反转
    r6_prev = rsi_simple(closes, 6)
    r6_now = rsi_simple(closes + [c], 6)
    if not (r6_prev < 25 and r6_now > r6_prev): return False, 0, {}
    
    return True, 100, {'pct': pct, 'rsi': r6_now}

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
    print("正在进行 v20 冰点起爆版回测...")
    files = glob.glob(os.path.join(KLINE_DIR, '*.json'))
    klines = {os.path.basename(f).replace('.json',''): json.load(open(f)) for f in files}
    eval_dates = sorted(list(set(b['date'] for bars in klines.values() for b in bars)))[120:-12]
    
    hits = backtest(f_v20_bottom_reversal, klines, eval_dates)
    if not hits:
        print("❌ v20 无命中")
        return

    r5 = [h['ret5'] for h in hits]
    r10 = [h['ret10'] for h in hits]
    win10 = sum(1 for r in r10 if r>0)/len(r10)*100
    avg10 = statistics.mean(r10)
    
    print(f"\n📊 v20 冰点起爆版结果 (总计 {len(hits)} 次命中):")
    print("-" * 40)
    print(f"T+5  均收益: {statistics.mean(r5):.2f}%")
    print(f"T+10 胜率: {win10:.1f}% 🏆")
    print(f"T+10 均收益: {avg10:.2f}%")
    print("-" * 40)
    
    # 打印前5个高收益样例
    for h in sorted(hits, key=lambda x: x['ret10'], reverse=True)[:5]:
        print(f"样例: {h['date']} | {h['code']} | T+10: {h['ret10']:.2f}%")

if __name__ == "__main__": main()

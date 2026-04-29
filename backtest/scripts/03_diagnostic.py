"""
03: 诊断分析 — 公式为什么亏?
- 看命中后T+1开盘 vs 收盘表现(冲高回落?)
- 看不同板块/价格段的表现差异
- 看大盘环境的过滤效果
- 看"如果加止损"会怎样
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
KLINE_DIR = os.path.join(DATA_DIR, 'kline')
RESULT_DIR = os.path.join(os.path.dirname(__file__), '..', 'results')

def load_klines():
    out = {}
    for f in glob.glob(os.path.join(KLINE_DIR, '*.json')):
        code = os.path.basename(f).replace('.json','')
        try: out[code] = json.load(open(f))
        except: pass
    return out

# 加载某个版本的命中记录,补充更多分析维度
def deep_analyze(version):
    hits = json.load(open(os.path.join(RESULT_DIR, f'hits_{version}.json')))
    klines = load_klines()
    
    print(f"\n{'='*70}")
    print(f"深度分析: {version} (命中 {len(hits)} 次)")
    print(f"{'='*70}")
    
    # 维度1: T+1 开盘 vs 收盘
    open_pcts = []  # T+1 开盘相对买入价
    intraday_changes = []  # T+1 开盘到收盘
    for h in hits:
        code = h['code']
        if code not in klines: continue
        bars = klines[code]
        date_idx = {b['date']:i for i,b in enumerate(bars)}
        if h['date'] not in date_idx: continue
        i = date_idx[h['date']]
        if i+1 >= len(bars): continue
        next_bar = bars[i+1]
        entry = h['entry']
        op = (next_bar['o']/entry-1)*100
        cl = (next_bar['c']/next_bar['o']-1)*100
        open_pcts.append(op)
        intraday_changes.append(cl)
    
    if open_pcts:
        print(f"\n[T+1 开盘表现]")
        print(f"  平均开盘 {statistics.mean(open_pcts):+.2f}%, 中位 {statistics.median(open_pcts):+.2f}%")
        print(f"  开盘上涨占 {sum(1 for x in open_pcts if x>0)*100/len(open_pcts):.1f}%")
        print(f"  开盘>=2% 占 {sum(1 for x in open_pcts if x>=2)*100/len(open_pcts):.1f}%")
        
        print(f"\n[T+1 日内表现 (开盘到收盘)]")
        print(f"  平均日内 {statistics.mean(intraday_changes):+.2f}%")
        print(f"  日内上涨占 {sum(1 for x in intraday_changes if x>0)*100/len(intraday_changes):.1f}%")
    
    # 维度2: 模拟止损 (T+1 起跌-7%止损,反之就持有)
    for hold_days in [3, 5, 10]:
        rets_no_stop = []
        rets_with_stop = []
        for h in hits:
            code = h['code']
            if code not in klines: continue
            bars = klines[code]
            date_idx = {b['date']:i for i,b in enumerate(bars)}
            if h['date'] not in date_idx: continue
            i = date_idx[h['date']]
            if i+hold_days >= len(bars): continue
            entry = h['entry']
            
            # 无止损
            exit_p = bars[i+hold_days]['c']
            rets_no_stop.append((exit_p/entry-1)*100)
            
            # 有止损 -7% 跟踪
            stopped = False
            stop_price = entry * 0.93
            for j in range(i+1, i+hold_days+1):
                if bars[j]['l'] <= stop_price:
                    rets_with_stop.append(-7)
                    stopped = True
                    break
            if not stopped:
                rets_with_stop.append((bars[i+hold_days]['c']/entry-1)*100)
        
        if rets_no_stop:
            print(f"\n[T+{hold_days} 止损对比]")
            print(f"  无止损: 均值{statistics.mean(rets_no_stop):+.2f}% 中位{statistics.median(rets_no_stop):+.2f}% 胜率{sum(1 for r in rets_no_stop if r>0)*100/len(rets_no_stop):.1f}%")
            print(f"  -7%止损: 均值{statistics.mean(rets_with_stop):+.2f}% 中位{statistics.median(rets_with_stop):+.2f}% 胜率{sum(1 for r in rets_with_stop if r>0)*100/len(rets_with_stop):.1f}%")
    
    # 维度3: 按命中评分细分
    score_buckets = defaultdict(list)
    for h in hits:
        sc = h.get('score', 0)
        if 5 in [b for b in h.get('returns',{}).keys()]:
            score_buckets[sc].append(h['returns'][5])
    print(f"\n[按评分细分 T+5 收益]")
    for sc in sorted(score_buckets.keys(), reverse=True):
        rs = score_buckets[sc]
        if len(rs)<5: continue
        print(f"  评分{sc}: {len(rs)}次, 均值{statistics.mean(rs):+.2f}% 胜率{sum(1 for r in rs if r>0)*100/len(rs):.1f}%")
    
    # 维度4: 收盘强度过滤
    # 检查 T+1 高开>3%的票, 平均收益如何
    high_open_rets = []
    low_open_rets = []
    for h in hits:
        code = h['code']
        if code not in klines: continue
        bars = klines[code]
        date_idx = {b['date']:i for i,b in enumerate(bars)}
        if h['date'] not in date_idx: continue
        i = date_idx[h['date']]
        if i+5 >= len(bars): continue
        op_pct = (bars[i+1]['o']/h['entry']-1)*100
        ret5 = (bars[i+5]['c']/h['entry']-1)*100
        if op_pct > 3:
            high_open_rets.append(ret5)
        elif op_pct < 1:
            low_open_rets.append(ret5)
    
    if high_open_rets and low_open_rets:
        print(f"\n[T+1 开盘价过滤]")
        print(f"  高开>3% (n={len(high_open_rets)}): T+5均值{statistics.mean(high_open_rets):+.2f}%, 胜率{sum(1 for r in high_open_rets if r>0)*100/len(high_open_rets):.1f}%")
        print(f"  低开<1% (n={len(low_open_rets)}): T+5均值{statistics.mean(low_open_rets):+.2f}%, 胜率{sum(1 for r in low_open_rets if r>0)*100/len(low_open_rets):.1f}%")
    
    # 维度5: 板块/价格段
    price_buckets = defaultdict(list)
    for h in hits:
        ret5 = h.get('returns',{}).get(5)
        if ret5 is None: continue
        p = h['entry']
        if p < 10: bucket = '<10'
        elif p < 30: bucket = '10-30'
        elif p < 60: bucket = '30-60'
        else: bucket = '>60'
        price_buckets[bucket].append(ret5)
    print(f"\n[按价格段 T+5 收益]")
    for b in ['<10','10-30','30-60','>60']:
        rs = price_buckets.get(b,[])
        if len(rs)<5: continue
        print(f"  价格{b:6s}: {len(rs)}次, 均值{statistics.mean(rs):+.2f}% 胜率{sum(1 for r in rs if r>0)*100/len(rs):.1f}%")

if __name__=='__main__':
    import sys
    v = sys.argv[1] if len(sys.argv)>1 else 'v3.0'
    deep_analyze(v)

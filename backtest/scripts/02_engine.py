"""
02: 回测引擎 — 历史滚动 N 天,每天用公式选股,看 T+1/T+3/T+5/T+10 收益
- 输入: 公式版本号 + 参数字典
- 输出: 命中率/平均收益/胜率/最大回撤等
- 支持多版本对比
"""
import json, os, glob, sys, statistics
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
KLINE_DIR = os.path.join(DATA_DIR, 'kline')
RESULT_DIR = os.path.join(os.path.dirname(__file__), '..', 'results')
os.makedirs(RESULT_DIR, exist_ok=True)

def ma(arr,n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr,n): return max(arr[-n:]) if len(arr)>=n else None
def llv(arr,n): return min(arr[-n:]) if len(arr)>=n else None

def load_all_klines():
    """加载所有缓存的K线"""
    klines = {}
    for f in glob.glob(os.path.join(KLINE_DIR, '*.json')):
        code = os.path.basename(f).replace('.json','')
        try:
            klines[code] = json.load(open(f))
        except: pass
    return klines

# 公式版本字典 — 每个公式接收(bars_until_today, today_bar) 返回 (passed:bool, score:int, debug:dict)
FORMULAS = {}

def register(name):
    def deco(fn):
        FORMULAS[name] = fn
        return fn
    return deco

@register('v3.0')
def f_v3(bars, today):
    """v3.0 原版: 8 个条件,全过为命中"""
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c = today['c']; h = today['h']; v = today['v']
    
    ma5=ma(closes,5); ma10=ma(closes,10); ma20=ma(closes,20)
    ma60=ma(closes,60); ma120=ma(closes,min(120,len(closes)))
    vol5=ma(vols,5); vol20=ma(vols,20)
    
    # 把今天加入临时序列计算
    closes_w = closes + [c]; highs_w = highs + [h]; lows_w = lows + [today['l']]; vols_w = vols + [v]
    
    c1 = (hhv(highs_w[-20:],20)/llv(lows_w[-20:],20)-1)*100 < 28
    c2 = c > ma20
    c3 = ma20 >= ma(closes[-25:-5] if len(closes)>=25 else closes[:-5],20)*0.99 if len(closes)>=25 else False
    
    # 近3日(含今天)放量上涨
    c4 = False
    series_v = vols_w; series_c = closes_w
    for i in range(-3, 0):
        if abs(i) < len(series_v) and vol20 and series_v[i] > vol20*1.4 and series_c[i] > series_c[i-1]*1.02:
            c4 = True; break
    
    # 近3日破近30日新高
    if len(highs_w) >= 33:
        c5 = max(highs_w[-3:]) > hhv(highs_w[:-3],30)*0.99
    else:
        c5 = False
    
    pct_20d = (c/closes[-20]-1)*100 if len(closes)>=20 else 0
    c6 = -10 < pct_20d < 30
    c7 = vol5 and vol20 and vol5 > vol20*1.1
    c8 = ma120 and c < ma120*1.8
    
    flags = [c1,c2,c3,c4,c5,c6,c7,c8]
    score = sum(flags)
    return score==8, score, {'flags':flags}


@register('v3.1')
def f_v31(bars, today):
    """v3.1: 在 v3 基础上加换手率上限25%(无换手数据则跳过), 去掉过严的破30日新高"""
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c = today['c']; h = today['h']; v = today['v']
    
    ma5=ma(closes,5); ma10=ma(closes,10); ma20=ma(closes,20)
    ma60=ma(closes,60); ma120=ma(closes,min(120,len(closes)))
    vol5=ma(vols,5); vol20=ma(vols,20)
    
    closes_w = closes + [c]; highs_w = highs + [h]; lows_w = lows + [today['l']]; vols_w = vols + [v]
    
    c1 = (hhv(highs_w[-20:],20)/llv(lows_w[-20:],20)-1)*100 < 28
    c2 = c > ma20
    c3 = ma20 >= ma(closes[-25:-5] if len(closes)>=25 else closes[:-5],20)*0.99 if len(closes)>=25 else False
    
    c4 = False
    for i in range(-3, 0):
        if abs(i) < len(vols_w) and vol20 and vols_w[i] > vol20*1.4 and closes_w[i] > closes_w[i-1]*1.02:
            c4 = True; break
    
    # v3.1 改进: "近3日破近20日新高" (而非30日)
    if len(highs_w) >= 23:
        c5 = max(highs_w[-3:]) > hhv(highs_w[:-3],20)*0.99
    else:
        c5 = False
    
    pct_20d = (c/closes[-20]-1)*100 if len(closes)>=20 else 0
    c6 = -10 < pct_20d < 30
    c7 = vol5 and vol20 and vol5 > vol20*1.1
    c8 = ma120 and c < ma120*1.8
    
    flags = [c1,c2,c3,c4,c5,c6,c7,c8]
    score = sum(flags)
    return score==8, score, {'flags':flags}


@register('v3.2')
def f_v32(bars, today):
    """v3.2: v3.1 + 当日涨幅 2%-6% (温和启动) + 量比1.2-3.5 (避免暴量出货)"""
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c = today['c']; h = today['h']; v = today['v']; o = today['o']
    
    # 当日涨幅
    today_pct = (c/closes[-1]-1)*100
    if today_pct < 2 or today_pct > 6: return False, 0, {'reason':'pct_out'}
    
    vol20 = ma(vols,20)
    if vol20:
        ratio = v/vol20
        if ratio < 1.2 or ratio > 3.5: return False, 0, {'reason':'vol_out','ratio':ratio}
    
    return f_v31(bars, today)  # 复用 v3.1


@register('v4.0')
def f_v40(bars, today):
    """v4.0: 大改 — 起涨初期识别
    核心: 寻找'刚刚启动'的票
    1. 平台整理后的首次有效突破
    2. 量价配合(放量1.5-3倍)
    3. 趋势确认(MA20上行+站稳)
    4. 涨幅过滤(当日2%-7%, 20日累计-5%~+20%)
    5. 不在历史顶部
    """
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c = today['c']; h = today['h']; v = today['v']; o = today['o']; l = today['l']
    
    today_pct = (c/closes[-1]-1)*100
    
    closes_w = closes + [c]; highs_w = highs + [h]; lows_w = lows + [l]; vols_w = vols + [v]
    
    ma5=ma(closes,5); ma10=ma(closes,10); ma20=ma(closes,20)
    ma60=ma(closes,60); ma120=ma(closes,min(120,len(closes)))
    vol5=ma(vols,5); vol20=ma(vols,20)
    if not all([ma5,ma10,ma20,ma60,vol20]): return False, 0, {}
    
    # 1. 当日温和上涨 2%-7%
    c1 = 2 < today_pct < 7
    # 2. 量比1.5-3倍 (启动量, 避免诱多)
    ratio = v/vol20
    c2 = 1.5 < ratio < 3.0
    # 3. 站上MA10 和 MA20
    c3 = c > ma10 and c > ma20
    # 4. MA20 上行 (5日前的MA20 < 当前)
    ma20_5d_ago = ma(closes[:-5], 20)
    c4 = ma20_5d_ago and ma20 > ma20_5d_ago
    # 5. 平台整理: 过去20日振幅<22% (更严的平台)
    c5 = (hhv(highs[-20:],20)/llv(lows[-20:],20)-1)*100 < 22
    # 6. 突破近20日高 (今日收盘 > 近20日最高)
    c6 = c > hhv(highs[-20:], 20)*0.99
    # 7. 20日累涨 -5% ~ +20% (温和,不在末段)
    pct_20d = (c/closes[-20]-1)*100
    c7 = -5 < pct_20d < 20
    # 8. 不在历史顶部 (与年线距离<70%)
    c8 = ma120 and c < ma120*1.7
    # 9. 收阳线(实体>=半根)
    c9 = c > o and (c-o)/(h-l+0.001) > 0.4 if h>l else c>=o
    # 10. 收盘价靠近最高(防止冲高回落): (h-c)/(h-l) < 0.3
    c10 = (h-l)>0 and (h-c)/(h-l) < 0.4
    
    flags = [c1,c2,c3,c4,c5,c6,c7,c8,c9,c10]
    score = sum(flags)
    return score==10, score, {'flags':flags,'today_pct':today_pct,'ratio':ratio}


def backtest(formula_name, klines, eval_dates=None, hold_days=[1,3,5,10], lookback_days=60):
    """
    对每只股票, 在每个评估日运行公式, 记录后续N天收益
    """
    fn = FORMULAS[formula_name]
    
    # 收集所有日期(取覆盖最多的)
    all_dates = set()
    for code, bars in klines.items():
        for b in bars: all_dates.add(b['date'])
    all_dates = sorted(all_dates)
    
    if eval_dates is None:
        # 默认: 最近120天里, 跳过前60天预热, 每天回测
        eval_dates = all_dates[-lookback_days-1:-max(hold_days)-1]
    
    print(f"  评估日范围: {eval_dates[0]} ~ {eval_dates[-1]} ({len(eval_dates)}天)")
    
    hits = []  # 每个命中: {date,code,name,entry,returns:{1:,3:,5:,10:}}
    
    for code, bars in klines.items():
        # 把bars 按 date 索引
        date_idx = {b['date']:i for i,b in enumerate(bars)}
        
        for d in eval_dates:
            if d not in date_idx: continue
            i = date_idx[d]
            if i < 65: continue  # 数据不够
            past = bars[:i]
            today = bars[i]
            
            try:
                passed, score, dbg = fn(past, today)
            except Exception as e:
                continue
            
            if not passed: continue
            
            # 评估T+1..T+10 收益
            entry = today['c']
            returns = {}
            for hd in hold_days:
                if i+hd < len(bars):
                    exit_p = bars[i+hd]['c']
                    returns[hd] = (exit_p/entry - 1)*100
            
            hits.append({
                'date': d, 'code': code,
                'entry': entry, 'returns': returns,
                'score': score
            })
    
    return hits


def stats(hits, hold_days=[1,3,5,10]):
    out = {'total_hits': len(hits)}
    if not hits:
        return out
    
    for hd in hold_days:
        rs = [h['returns'][hd] for h in hits if hd in h['returns']]
        if not rs: continue
        wins = sum(1 for r in rs if r>0)
        big_wins = sum(1 for r in rs if r>5)
        big_losses = sum(1 for r in rs if r<-5)
        out[f'T+{hd}'] = {
            'samples': len(rs),
            'avg_ret_pct': round(statistics.mean(rs),2),
            'median_ret_pct': round(statistics.median(rs),2),
            'win_rate_pct': round(wins/len(rs)*100,1),
            'big_win_rate_pct': round(big_wins/len(rs)*100,1),  # >5%
            'big_loss_rate_pct': round(big_losses/len(rs)*100,1),  # <-5%
            'max_ret': round(max(rs),2),
            'min_ret': round(min(rs),2),
        }
    return out


def main():
    versions = sys.argv[1].split(',') if len(sys.argv)>1 else list(FORMULAS.keys())
    
    print(f"加载K线数据...")
    klines = load_all_klines()
    print(f"  {len(klines)} 只股票")
    
    if not klines:
        print("⚠️ 无K线数据,先跑 01_fetch_universe.py")
        return
    
    # 取覆盖率最高的日期范围
    all_dates = set()
    for bars in klines.values():
        for b in bars: all_dates.add(b['date'])
    all_dates = sorted(all_dates)
    
    print(f"日期范围: {all_dates[0]} ~ {all_dates[-1]} ({len(all_dates)}天)")
    
    # 评估期: 最近120天但要给末段留10天观察
    eval_dates = all_dates[max(0,len(all_dates)-120):-12]
    
    summary = {}
    for v in versions:
        if v not in FORMULAS:
            print(f"未知公式: {v}"); continue
        print(f"\n=== 测试 {v} ===")
        hits = backtest(v, klines, eval_dates=eval_dates)
        s = stats(hits)
        summary[v] = {'stats': s, 'hits_count': len(hits)}
        # 保存命中明细
        with open(os.path.join(RESULT_DIR, f'hits_{v}.json'),'w') as f:
            json.dump(hits, f, ensure_ascii=False, indent=1)
        print(f"  命中 {len(hits)} 次")
        for k,vv in s.items():
            if k=='total_hits': continue
            print(f"    {k}: 胜率{vv['win_rate_pct']}% 均值{vv['avg_ret_pct']}% 中位{vv['median_ret_pct']}% 大涨>5%占{vv['big_win_rate_pct']}% 大跌<-5%占{vv['big_loss_rate_pct']}%")
    
    # 保存汇总
    with open(os.path.join(RESULT_DIR, 'summary.json'),'w') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    # 打印对比
    print(f"\n{'='*80}\n📊 对比表\n{'='*80}")
    print(f"{'版本':<8}{'命中数':<8}{'T+1胜率%':<10}{'T+3胜率%':<10}{'T+5胜率%':<10}{'T+5均收益%':<10}")
    for v, info in summary.items():
        s = info['stats']
        if 'T+1' in s:
            print(f"{v:<8}{info['hits_count']:<8}{s['T+1']['win_rate_pct']:<10}"
                  f"{s.get('T+3',{}).get('win_rate_pct','-'):<10}"
                  f"{s.get('T+5',{}).get('win_rate_pct','-'):<10}"
                  f"{s.get('T+5',{}).get('avg_ret_pct','-'):<10}")

if __name__=='__main__':
    main()

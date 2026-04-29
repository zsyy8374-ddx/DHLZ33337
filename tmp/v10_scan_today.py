import os, json, time, statistics, urllib.request, re
from collections import defaultdict

KLINE_DIR = 'backtest/data/kline'

def get_sina_hq(codes):
    """Fetch real-time data from Sina"""
    formatted = []
    for c in codes:
        if c.startswith('6'): formatted.append(f"sh{c}")
        else: formatted.append(f"sz{c}")
    
    url = f"https://hq.sinajs.cn/list={','.join(formatted)}"
    req = urllib.request.Request(url, headers={'Referer': 'https://finance.sina.com.cn'})
    try:
        with urllib.request.urlopen(req, timeout=10) as f:
            content = f.read().decode('gb18030')
    except Exception as e:
        print(f"Error fetching {codes[0]}...: {e}")
        return {}
    
    results = {}
    lines = content.strip().split('\n')
    for line in lines:
        match = re.search(r'hq_str_s[hz](\d+)="([^"]+)"', line)
        if match:
            code = match.group(1)
            data = match.group(2).split(',')
            if len(data) >= 31 and float(data[1]) > 0:
                results[code] = {
                    'date': '2026-04-27',
                    'o': float(data[1]),
                    'c': float(data[3]),
                    'h': float(data[4]),
                    'l': float(data[5]),
                    'v': float(data[8])
                }
    return results

def ma(arr, n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr, n): return max(arr[-n:]) if len(arr)>=n else None
def llv(arr, n): return min(arr[-n:]) if len(arr)>=n else None

def v10_0_scan():
    print("开始 v10.0 今日扫描 (2026-04-27)...")
    
    all_codes = [f.replace('.json','') for f in os.listdir(KLINE_DIR) if f.endswith('.json')]
    print(f"总计股票数: {len(all_codes)}")
    
    # 1. 批量抓取今日数据
    today_data = {}
    chunk_size = 80
    for i in range(0, len(all_codes), chunk_size):
        chunk = all_codes[i:i+chunk_size]
        data = get_sina_hq(chunk)
        today_data.update(data)
        if i % 400 == 0: print(f"  已抓取 {i} 只...")
        time.sleep(0.1)
    
    print(f"抓取完成, 有效今日数据: {len(today_data)}")
    
    # 2. 计算市场宽度
    chgs = []
    for code, d in today_data.items():
        # 需要昨天收盘价,这里先简单估算
        pass
        
    # 3. 逐一运行公式
    hits = []
    for code in all_codes:
        if code not in today_data: continue
        
        try:
            with open(os.path.join(KLINE_DIR, f"{code}.json")) as f:
                bars = json.load(f)
        except: continue
        
        if not bars: continue
        # 补全今日
        today = today_data[code]
        if bars[-1]['date'] == today['date']:
            # 已经有今日数据了(可能之前抓过)
            hist = bars[:-1]
            now = bars[-1]
        else:
            hist = bars
            now = today
            
        if len(hist) < 65: continue
        
        # 逻辑运行
        closes = [b['c'] for b in hist]
        highs = [b['h'] for b in hist]
        lows = [b['l'] for b in hist]
        vols = [b['v'] for b in hist]
        
        c = now['c']; h = now['h']; l = now['l']; o = now['o']; v = now['v']
        prev_c = closes[-1]
        today_pct = (c/prev_c-1)*100
        
        # 基础条件
        if not (1.5 < today_pct < 4.5): continue
        
        ma10 = ma(closes, 10); ma20 = ma(closes, 20); ma60 = ma(closes, 60)
        vol5 = ma(vols, 5); vol20 = ma(vols, 20)
        if not all([ma10, ma20, ma60, vol20]): continue
        if c <= ma10 or c <= ma20: continue
        
        # MA20上行
        ma20_5d = ma(closes[:-5], 20)
        if not (ma20_5d and ma20 > ma20_5d * 1.005): continue
        
        # 量比
        ratio = v/vol20
        if not (1.3 < ratio < 2.5): continue
        
        # ATR (MTR)
        mtrs = []
        for i in range(len(hist)-14, len(hist)):
            bar = hist[i]
            pc = hist[i-1]['c']
            mtrs.append(max(bar['h']-bar['l'], abs(bar['h']-pc), abs(bar['l']-pc)))
        atr14 = sum(mtrs)/14
        if atr14/c > 0.04: continue
        
        # 量比稳
        if vol5/vol20 < 1.0 or vol5/vol20 > 2.0: continue
        
        # 昨日站MA20
        if closes[-1] <= ma(closes[:-1], 20): continue
        
        # 其它硬指标
        if c <= o: continue
        if h>l and (h-c)/(h-l) > 0.4: continue
        if c/ma60 > 1.35: continue
        if c < hhv(highs[-20:], 20) * 0.99: continue

        # VCP 波动率收缩 (v10.0 核心)
        w1 = (max(highs[-20:-10]) - min(lows[-20:-10])) / ma(closes[-20:-10], 10)
        w2 = (max(highs[-10:]) - min(lows[-10:])) / ma(closes[-10:], 10)
        if w2 >= w1 * 0.9: continue
        
        hits.append({
            'code': code,
            'name': f"Stock {code}", # 暂无名称
            'chg': round(today_pct, 2),
            'c': c,
            'score': 100,
            'vcp_ratio': round(w2/w1, 2)
        })
        
    # 打印结果
    print(f"\n✅ 扫描完成! 今日符合 v10.0 (VCP) 的标的共 {len(hits)} 只:")
    print("-" * 50)
    if not hits:
        print("今日无符合条件的标的 (说明 v10.0 非常严苛)。")
    else:
        for h in sorted(hits, key=lambda x: x['vcp_ratio']):
            print(f"代码: {h['code']} | 涨幅: {h['chg']}% | 现价: {h['c']} | 波动收缩比: {h['vcp_ratio']}")
    print("-" * 50)

if __name__ == "__main__":
    v10_0_scan()

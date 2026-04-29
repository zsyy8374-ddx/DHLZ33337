"""
01: 拉取股票全集(全A) + 缓存日K数据
- 用新浪接口(更稳)
- 每只缓存180日,够算60日均线和20日累涨幅
- 缓存到 backtest/data/kline/<code>.json
"""
import json, urllib.request, time, os, sys

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
KLINE_DIR = os.path.join(DATA_DIR, 'kline')
os.makedirs(KLINE_DIR, exist_ok=True)

def fetch_universe():
    """拿全市场股票列表(用新浪)"""
    out = []
    for page in range(1, 50):  # 50页 * 100 = 5000只,够A股全集
        url = f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num=100&sort=symbol&asc=1&node=hs_a"
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://finance.sina.com.cn'})
            raw = urllib.request.urlopen(req, timeout=10).read().decode('gbk', errors='ignore')
            arr = json.loads(raw)
            if not arr: break
            out.extend(arr)
            print(f"page {page}: cumul {len(out)}", end='\r')
            time.sleep(0.15)
            if len(arr) < 100: break
        except Exception as e:
            print(f"\npage {page} err: {e}"); break
    return out

def fetch_kline(code, days=180):
    """单只股票日K"""
    prefix = 'sz' if code.startswith(('00','30')) else 'sh'
    url = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=240&ma=no&datalen={days}'
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=8).read().decode()
        return [{'date':d['day'],'o':float(d['open']),'c':float(d['close']),
                 'h':float(d['high']),'l':float(d['low']),'v':float(d['volume'])} for d in json.loads(raw)]
    except Exception as e:
        return None

def main():
    # Step 1: 取股票列表
    cache_universe = os.path.join(DATA_DIR, 'universe.json')
    if os.path.exists(cache_universe) and (time.time()-os.path.getmtime(cache_universe))<86400:
        print(f"用缓存的universe: {cache_universe}")
        universe = json.load(open(cache_universe))
    else:
        print("拉取股票列表...")
        universe = fetch_universe()
        with open(cache_universe,'w') as f: json.dump(universe, f, ensure_ascii=False)
    print(f"\n全集 {len(universe)} 只")
    
    # 过滤: 排除ST、退市、北交所
    pool = []
    for s in universe:
        name = s.get('name','')
        code = s.get('code','')
        if 'ST' in name or '退' in name or 'N' in name[:1]: continue
        if not code or code.startswith(('8','4','9')): continue  # 北交所/B股
        if not code.startswith(('00','30','60','68')): continue
        pool.append(s)
    print(f"过滤后 {len(pool)} 只")
    
    # Step 2: 拉K线缓存(限制总量,避免拉太久)
    target_n = int(sys.argv[1]) if len(sys.argv)>1 else 1500  # 默认拉1500只
    pool = pool[:target_n]
    
    fetched = 0; cached = 0; failed = 0
    for i, s in enumerate(pool):
        code = s['code']
        cache_file = os.path.join(KLINE_DIR, f"{code}.json")
        # 已有且不超过24h,跳过
        if os.path.exists(cache_file) and (time.time()-os.path.getmtime(cache_file))<86400:
            cached += 1
            continue
        bars = fetch_kline(code, 180)
        if bars and len(bars)>=80:
            with open(cache_file,'w') as f: json.dump(bars, f)
            fetched += 1
        else:
            failed += 1
        if (i+1)%50==0:
            print(f"  进度 {i+1}/{len(pool)}  新拉{fetched} 缓存{cached} 失败{failed}", end='\r')
        time.sleep(0.04)
    print(f"\n完成: 新拉 {fetched} / 缓存 {cached} / 失败 {failed}")
    
    # 保存pool
    with open(os.path.join(DATA_DIR, 'pool.json'),'w') as f:
        json.dump([{'code':s['code'],'name':s['name']} for s in pool], f, ensure_ascii=False)
    print(f"pool 已保存 ({len(pool)} 只)")

if __name__=='__main__':
    main()

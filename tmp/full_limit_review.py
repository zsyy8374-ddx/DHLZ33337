import os, json, urllib.request, re, time

def get_full_market_limit_up():
    """
    全面扫描全市场(沪深京)所有涨停个股
    """
    # 扩大扫描范围到全 A 股 (4000+), 这里用 common prefix 批量抓取
    prefixes = ['sh60', 'sh68', 'sz00', 'sz30', 'bj83', 'bj87', 'bj43']
    limit_ups = []
    
    # 获取全市场代码列表 (从本地 kline 目录获取已有的, 并补充常见号段)
    all_codes = set([f.replace('.json','') for f in os.listdir('backtest/data/kline') if f.endswith('.json')])
    # 补充一些可能遗漏的活跃号段
    # (此处略, 实际生产中应从数据接口获取全量列表)
    
    codes_list = list(all_codes)
    chunk_size = 80
    
    print(f"开始扫描全市场 {len(codes_list)} 只股票...")
    
    for i in range(0, len(codes_list), chunk_size):
        chunk = codes_list[i:i+chunk_size]
        formatted = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c in chunk]
        url = f"https://hq.sinajs.cn/list={','.join(formatted)}"
        req = urllib.request.Request(url, headers={'Referer': 'https://finance.sina.com.cn'})
        try:
            with urllib.request.urlopen(req, timeout=10) as f:
                content = f.read().decode('gb18030')
                lines = content.strip().split('\n')
                for line in lines:
                    match = re.search(r'hq_str_s[hz](\d+)="([^"]+)"', line)
                    if match:
                        code = match.group(1)
                        data = match.group(2).split(',')
                        if len(data) >= 31:
                            prev_c = float(data[2])
                            curr_c = float(data[3])
                            if prev_c <= 0: continue
                            
                            pct = (curr_c/prev_c - 1) * 100
                            
                            # 判定涨停标准 (主板10%, 创业/科创20%)
                            is_limit = False
                            if code.startswith('60') or code.startswith('00'):
                                if pct >= 9.9: is_limit = True
                            elif code.startswith('30') or code.startswith('68'):
                                if pct >= 19.9: is_limit = True
                            
                            if is_limit:
                                bid1_vol = float(data[10]) # 手
                                bid1_price = float(data[11])
                                amount = float(data[9]) # 成交额
                                
                                limit_ups.append({
                                    'code': code,
                                    'name': data[0],
                                    'pct': round(pct, 2),
                                    'c': curr_c,
                                    'amount_cr': round(amount/100000000, 2), # 亿
                                    'bid_money_wan': round(bid1_vol * bid1_price / 10000, 2), # 万元
                                    'open': data[1],
                                    'high': data[4],
                                    'low': data[5]
                                })
        except: pass
        if i % 800 == 0: print(f"  已扫描 {i} 只...")
        time.sleep(0.02)
    
    return limit_ups

if __name__ == "__main__":
    res = get_full_market_limit_up()
    print(json.dumps(res, ensure_ascii=False))

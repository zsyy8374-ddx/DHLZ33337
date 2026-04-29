import os, json, urllib.request, re, time

def get_limit_up_stocks():
    """从新浪获取今日涨停/大涨股票"""
    # 这里用一个简单的逻辑: 扫描 1494 只股票, 找出涨幅 > 9.8% 的
    all_codes = [f.replace('.json','') for f in os.listdir('backtest/data/kline') if f.endswith('.json')]
    hits = []
    chunk_size = 100
    for i in range(0, len(all_codes), chunk_size):
        chunk = all_codes[i:i+chunk_size]
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
                        if len(data) >= 4:
                            prev_c = float(data[2])
                            curr_c = float(data[3])
                            if prev_c > 0:
                                pct = (curr_c/prev_c - 1) * 100
                                # 涨停筛选: 主板 > 9.8%, 创/科 > 19.5%
                                is_limit = False
                                if code.startswith('60') or code.startswith('00'):
                                    if pct > 9.8: is_limit = True
                                elif code.startswith('30') or code.startswith('68'):
                                    if pct > 19.5: is_limit = True
                                
                                if is_limit:
                                    # 抓取封单金额估算 (买一量)
                                    bid1_vol = float(data[10])
                                    bid1_price = float(data[11])
                                    hits.append({
                                        'code': code,
                                        'name': data[0],
                                        'pct': round(pct, 2),
                                        'c': curr_c,
                                        'bid_money': round(bid1_vol * bid1_price / 10000, 2), # 万元
                                        'turnover': round(float(data[8]) * curr_c / 100000000, 2) # 成交额(亿)
                                    })
        except: pass
        time.sleep(0.05)
    return hits

if __name__ == "__main__":
    stocks = get_limit_up_stocks()
    print(json.dumps(stocks, ensure_ascii=False))

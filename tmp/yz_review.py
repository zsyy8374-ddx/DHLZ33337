import os, json, time, urllib.request, re

# 精选今日 84 家涨停中具代表性的非 ST 标的
# 基于 Dengxian 提供的 XLS 数据和游资关注度
stocks = [
    {"code": "000925", "name": "众合科技"},
    {"code": "003036", "name": "泰坦股份"},
    {"code": "603501", "name": "豪威集团"},
    {"code": "603228", "name": "景旺电子"},
    {"code": "603610", "name": "麒盛科技"},
    {"code": "300582", "name": "英飞特"},
    {"code": "600418", "name": "江淮汽车"},
    {"code": "002120", "name": "韵达股份"},
    {"code": "600637", "name": "东方明珠"},
    {"code": "002902", "name": "铭普光磁"},
    {"code": "688381", "name": "帝奥微"},
    {"code": "605118", "name": "力鼎光电"},
    {"code": "603657", "name": "春光科技"},
    {"code": "002484", "name": "江海股份"},
    {"code": "600396", "name": "华电辽能"},
    {"code": "000062", "name": "深圳华强"}
]

def get_realtime_data(stock_list):
    results = []
    codes = [f"sh{s['code']}" if s['code'].startswith('6') else f"sz{s['code']}" for s in stock_list]
    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
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
                        # 0:name, 1:open, 2:last_close, 3:price, 4:high, 5:low, 6:bid, 7:ask, 8:volume, 9:amount
                        # 10:b1_v, 11:b1_p ... 30:date, 31:time
                        open_p = float(data[1])
                        last_p = float(data[2])
                        curr_p = float(data[3])
                        high_p = float(data[4])
                        low_p = float(data[5])
                        amount_yi = float(data[9]) / 100000000
                        b1_v = float(data[10])
                        b1_p = float(data[11])
                        bid_money_wan = (b1_v * b1_p) / 10000
                        
                        # 换手率计算需要流通盘，这里简化为成交额观察
                        # 判定涨停强度
                        is_yizi = (open_p == curr_p == high_p == low_p) and (curr_p > last_p * 1.09)
                        is_t_board = (curr_p == high_p == open_p) and (low_p < curr_p)
                        
                        results.append({
                            'code': code,
                            'name': data[0],
                            'pct': round((curr_p/last_p - 1) * 100, 2),
                            'amount_yi': round(amount_yi, 2),
                            'bid_wan': round(bid_money_wan, 2),
                            'bid_ratio': round(bid_money_wan / (amount_yi * 10000 + 1) * 100, 2),
                            'type': '一字' if is_yizi else ('T字' if is_t_board else '自然'),
                            'open_pct': round((open_p/last_p - 1) * 100, 2)
                        })
    except Exception as e:
        print(f"Error: {e}")
    return results

analysis = get_realtime_data(stocks)
print(json.dumps(analysis, ensure_ascii=False, indent=2))

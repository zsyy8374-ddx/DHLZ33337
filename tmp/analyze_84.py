import os, json, time, urllib.request, re

def analyze_stocks(stock_list):
    results = []
    # Only pick a subset of interesting ones if list is too long, but let's try all 84 since we have them
    chunk_size = 50
    for i in range(0, len(stock_list), chunk_size):
        chunk = stock_list[i:i+chunk_size]
        codes = [s['code'] for s in chunk]
        formatted = [f"sh{c}" if c.startswith('6') else f"sz{c}" for c in codes]
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
                            bid1_wan = round(float(data[10]) * float(data[11]) / 10000, 2)
                            amount_yi = round(float(data[9]) / 100000000, 2)
                            results.append({
                                'code': code,
                                'name': data[0],
                                'price': data[3],
                                'bid_wan': bid1_wan,
                                'amount_yi': amount_yi,
                                'bid_ratio': round(bid1_wan / (amount_yi * 10000 + 1) * 100, 2) # 封单额/成交额 比例
                            })
        except: pass
        time.sleep(0.05)
    return results

# Load the parsed data from the previous step
with open('tmp/parse_xls.py', 'r') as f:
    # Just kidding, I'll just re-run the logic here
    pass

# Read from what I just outputted in the previous turn
stock_data = [
  {"code": "301500", "name": "飞南资源"}, {"code": "000056", "name": "*ST皇庭"}, {"code": "000062", "name": "深圳华强"},
  {"code": "002484", "name": "江海股份"}, {"code": "002560", "name": "通达股份"}, {"code": "002569", "name": "*ST步森"},
  {"code": "000565", "name": "渝三峡Ａ"}, {"code": "000593", "name": "德龙汇能"}, {"code": "000609", "name": "*ST中迪"},
  {"code": "002630", "name": "ST华西"}, {"code": "688221", "name": "前沿生物-U"}, {"code": "300582", "name": "英飞特"},
  {"code": "600152", "name": "维科技术"}, {"code": "002706", "name": "良信股份"}, {"code": "603095", "name": "越剑智能"},
  {"code": "002741", "name": "光华科技"}, {"code": "000820", "name": "*ST节能"}, {"code": "603110", "name": "东方材料"},
  {"code": "000838", "name": "*ST发展"}, {"code": "603125", "name": "常青科技"}, {"code": "002785", "name": "万里石"},
  {"code": "600238", "name": "*ST椰岛"}, {"code": "688381", "name": "帝奥微"}, {"code": "600246", "name": "万通发展"},
  {"code": "000925", "name": "众合科技"}, {"code": "000952", "name": "广济药业"}, {"code": "603211", "name": "晋拓股份"},
  {"code": "603228", "name": "景旺电子"}, {"code": "001211", "name": "双枪科技"}, {"code": "600338", "name": "西藏珠峰"},
  {"code": "002902", "name": "铭普光磁"}, {"code": "688530", "name": "欧莱新材"}, {"code": "603272", "name": "联翔股份"},
  {"code": "002932", "name": "*ST明德"}, {"code": "600396", "name": "华电辽能"}, {"code": "001332", "name": "锡装股份"},
  {"code": "600400", "name": "红豆股份"}, {"code": "603318", "name": "水发燃气"}, {"code": "600418", "name": "江淮汽车"},
  {"code": "600433", "name": "冠豪高新"}, {"code": "002029", "name": "七 匹 狼"}, {"code": "003036", "name": "泰坦股份"},
  {"code": "002058", "name": "*ST威尔"}, {"code": "688677", "name": "海泰新光"}, {"code": "603486", "name": "科沃斯"},
  {"code": "603501", "name": "豪威集团"}, {"code": "603557", "name": "ST起步"}, {"code": "002115", "name": "三维通信"},
  {"code": "002120", "name": "韵达股份"}, {"code": "603579", "name": "荣泰健康"}, {"code": "603580", "name": "*ST艾艾"},
  {"code": "002134", "name": "天津普林"}, {"code": "603610", "name": "麒盛科技"}, {"code": "002154", "name": "报 喜 鸟"},
  {"code": "603626", "name": "科森科技"}, {"code": "603657", "name": "春光科技"}, {"code": "002175", "name": "东方智造"},
  {"code": "002181", "name": "粤 传 媒"}, {"code": "600637", "name": "东方明珠"}, {"code": "002210", "name": "飞马国际"},
  {"code": "002217", "name": "合力泰"}, {"code": "603721", "name": "*ST天择"}, {"code": "002227", "name": "*ST特迅"},
  {"code": "603726", "name": "朗迪集团"}, {"code": "603773", "name": "沃格光电"}, {"code": "600693", "name": "东百集团"},
  {"code": "600696", "name": "*ST岩石"}, {"code": "600707", "name": "彩虹股份"}, {"code": "603813", "name": "*ST原尚"},
  {"code": "002289", "name": "*ST宇顺"}, {"code": "600726", "name": "华电能源"}, {"code": "600735", "name": "ST新华锦"},
  {"code": "301248", "name": "杰创智能"}, {"code": "603931", "name": "格林达"}, {"code": "600815", "name": "厦工股份"},
  {"code": "600830", "name": "香溢融通"}, {"code": "605006", "name": "山东玻纤"}, {"code": "605118", "name": "力鼎光电"},
  {"code": "605138", "name": "盛泰集团"}, {"code": "605287", "name": "德才股份"}, {"code": "605289", "name": "罗曼股份"},
  {"code": "605336", "name": "*ST帅电"}, {"code": "688001", "name": "华兴源创"}
]

analysis = analyze_stocks(stock_data)
# Sort by bid_ratio to find the "strongest" boards
sorted_analysis = sorted(analysis, key=lambda x: x['bid_ratio'], reverse=True)
print(json.dumps(sorted_analysis, ensure_ascii=False, indent=2))

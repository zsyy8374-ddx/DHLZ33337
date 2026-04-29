import os, json, time, urllib.request, re

# 待深度分析的题材股名单 (基于 4/27 涨停及 Shi 的反馈)
stocks = [
    {"code": "000925", "name": "众合科技", "desc": "算力/交通"},
    {"code": "300582", "name": "英飞特", "desc": "20CM领头羊/算力"},
    {"code": "603501", "name": "豪威集团", "desc": "半导体/CIS龙头"},
    {"code": "603228", "name": "景旺电子", "desc": "算力/PCB"},
    {"code": "603610", "name": "麒盛科技", "desc": "智能家居/外贸"},
    {"code": "003036", "name": "泰坦股份", "desc": "纺织/一带一路"},
    {"code": "600418", "name": "江淮汽车", "desc": "华为汽车/智能驾驶"},
    {"code": "002120", "name": "韵达股份", "desc": "低位/物流反转"},
    {"code": "600637", "name": "东方明珠", "desc": "超高清视频/传媒"},
    {"code": "002902", "name": "铭普光磁", "desc": "CPO/光通信"},
    {"code": "688381", "name": "帝奥微", "desc": "模拟芯片/低位"},
    {"code": "002484", "name": "江海股份", "desc": "超级电容/半导体"},
    {"code": "000062", "name": "深圳华强", "desc": "分销/芯片出口"},
    {"code": "603318", "name": "水发燃气", "desc": "天然气/低吸"},
    {"code": "605118", "name": "力鼎光电", "desc": "车载镜头/低位"},
    {"code": "600707", "name": "彩虹股份", "desc": "面板/涨价预期"}
]

def analyze_themes(stock_list):
    # 这里通过模拟或简单的爬虫逻辑获取每个股票背后的核心催化剂
    # 游资逻辑：题材越新、越跨国、政策越硬，级别越高
    themed_results = []
    for s in stock_list:
        # 实际操作中这里会结合 web_search 的结果
        # 此处展示分析后的权重分配
        weight = 0
        theme_str = ""
        if s['code'] == "000925":
            theme_str = "自主算力芯片 + 智慧交通。题材级别：S级（涉及国产替代核心）"
            weight = 95
        elif s['code'] == "603501":
            theme_str = "CIS芯片国产化 + 科创权重反弹。题材级别：A级（机构共振）"
            weight = 88
        elif s['code'] == "300582":
            theme_str = "英伟达产业链补涨 + 20CM身位优势。题材级别：A级（情绪龙头）"
            weight = 90
        elif s['code'] == "603228":
            theme_str = "1.6T光模块PCB板 + 产能释放。题材级别：A级（基本面支撑）"
            weight = 85
        elif s['code'] == "603610":
            theme_str = "智能养老 + 外贸复苏 + 极低换手。题材级别：B级（妖股潜质）"
            weight = 82
        elif s['code'] == "003036":
            theme_str = "纺织出海 + 高标身位卡位。题材级别：B级（身位龙）"
            weight = 80
        elif s['code'] == "600418":
            theme_str = "尊界（华为第四界）发布倒计时。题材级别：A级（大趋势）"
            weight = 87
        else:
            theme_str = s['desc'] + " (常规补涨)"
            weight = 70
        
        themed_results.append({
            "code": s['code'],
            "name": s['name'],
            "theme": theme_str,
            "weight": weight
        })
    return sorted(themed_results, key=lambda x: x['weight'], reverse=True)

print(json.dumps(analyze_themes(stocks), ensure_ascii=False, indent=2))

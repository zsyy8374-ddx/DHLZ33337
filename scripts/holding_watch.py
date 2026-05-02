#!/usr/bin/env python3
"""持仓股监控 — 每隔 1 小时拉 5m K, 检测异动告警
触发: 北京 9:35, 10:30, 11:30, 13:30, 14:30, 14:55 (盘中 6 次)

监控规则:
1. 5 分钟涨幅 > +3%: 异动告警 ⚡
2. 5 分钟涨幅 < -3%: 急跌告警 ⚠️
3. 触及涨停 (+9.5% 主板, +19% 创业): 涨停告警 🚀
4. 跌破前一日收盘 (盘中由红转绿): 转弱告警 🔻
"""
import json, sys, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))

WX_CHANNEL = "openclaw-weixin"
WX_ACCOUNT = "ba28cc3242ca-im-bot"
WX_TARGET = "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat"

# 状态文件: 记录每只股最近一次告警, 避免重复
STATE_FILE = WS / 'memory' / 'holding_watch_state.json'

WATCH_LIST = {
    '600330': '天通股份',
    '002866': '传艺科技',
}


def send_wechat(msg):
    import subprocess
    cmd = ["openclaw", "message", "send",
           "--channel", WX_CHANNEL, "--account", WX_ACCOUNT,
           "--target", WX_TARGET, "--message", msg, "--json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def get_5m_kline(code):
    """拉腾讯 5m K, 返回最近 50 根"""
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/kline/mkline?param={prefix}{code},m5,,50'
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        return d.get('data', {}).get(f'{prefix}{code}', {}).get('m5', [])
    except Exception:
        return []


def get_realtime(code):
    """拉实时报价 (sina)"""
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://hq.sinajs.cn/list={prefix}{code}'
    try:
        req = urllib.request.Request(url, headers={'Referer':'http://finance.sina.com.cn', 'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            text = r.read().decode('gbk')
        parts = text.split('"')[1].split(',')
        return {
            'name': parts[0],
            'open': float(parts[1]),
            'prev_close': float(parts[2]),
            'now': float(parts[3]),
            'high': float(parts[4]),
            'low': float(parts[5]),
        }
    except Exception:
        return None


def is_zt(name, chg, code):
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f: return json.load(f)
    return {}


def save_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f: json.dump(s, f, ensure_ascii=False, indent=2)


def main():
    today = datetime.now(BJT).strftime('%Y-%m-%d')
    now_h = datetime.now(BJT).strftime('%H:%M')
    print(f'⏱ 持仓监控 {today} {now_h}', flush=True)
    
    state = load_state()
    today_state = state.get(today, {})
    
    alerts = []
    for code, name in WATCH_LIST.items():
        rt = get_realtime(code)
        if not rt:
            print(f'  {code} 实时数据失败', flush=True)
            continue
        
        chg = (rt['now'] - rt['prev_close']) / rt['prev_close'] * 100
        intraday_high_chg = (rt['high'] - rt['prev_close']) / rt['prev_close'] * 100
        intraday_low_chg = (rt['low'] - rt['prev_close']) / rt['prev_close'] * 100
        
        cur_alerts = today_state.get(code, [])
        
        # 1. 涨停
        if is_zt(name, chg, code) and 'zt' not in cur_alerts:
            alerts.append(f'🚀 {code} {name} 涨停! (+{chg:.2f}%, 现价 {rt["now"]:.2f})')
            cur_alerts.append('zt')
        
        # 2. 急涨 5m (用 5m K 看)
        kline = get_5m_kline(code)
        if kline and len(kline) >= 2:
            last = kline[-1]
            # m5 格式: [time, open, close, high, low, volume]
            last_close = float(last[2])
            last_open = float(last[1])
            m5_chg = (last_close - last_open) / last_open * 100
            
            if m5_chg > 3.0 and 'rapid_up' not in cur_alerts:
                alerts.append(f'⚡ {code} {name} 5m 急涨 +{m5_chg:.2f}% (今日 {chg:+.2f}%, 现价 {rt["now"]:.2f})')
                cur_alerts.append('rapid_up')
            elif m5_chg < -3.0 and 'rapid_down' not in cur_alerts:
                alerts.append(f'⚠️ {code} {name} 5m 急跌 {m5_chg:.2f}% (今日 {chg:+.2f}%, 现价 {rt["now"]:.2f})')
                cur_alerts.append('rapid_down')
        
        # 3. 红转绿 (盘中 high 是红, 现价绿)
        if intraday_high_chg > 1.0 and chg < -0.5 and 'red_to_green' not in cur_alerts:
            alerts.append(f'🔻 {code} {name} 红转绿! 高点 +{intraday_high_chg:.2f}%, 现价 {chg:+.2f}%')
            cur_alerts.append('red_to_green')
        
        today_state[code] = cur_alerts
        print(f'  {code} {name}: 现价 {rt["now"]:.2f} ({chg:+.2f}%), 高 {intraday_high_chg:+.2f}%, 低 {intraday_low_chg:+.2f}%', flush=True)
    
    state[today] = today_state
    # 只保留最近 30 天 state
    if len(state) > 30:
        state = dict(sorted(state.items())[-30:])
    save_state(state)
    
    if alerts:
        msg = f'📍 持仓监控 {now_h}\n' + '\n'.join(alerts)
        send_wechat(msg)
        print(f'\n✅ 告警发送: {len(alerts)} 条', flush=True)
    else:
        print('\n  无告警', flush=True)


if __name__ == '__main__':
    main()

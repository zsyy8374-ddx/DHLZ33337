"""给 v9-with-pre10 (3262 events) 补 D_t 早盘特征 (集合竞价 + 首 5 分钟)
实战观察 (4-30):
- 真涨停: 5m 高点 +4-5%, 高开 +0.7-1.5% (温和高开 + 急速冲高)
- 失败: 5m 高点 <2%, 低开或假高开

新增字段 (D_t = D0+callback_window+1, 即反转/失败的判定日的早盘):
- pm_open_pct: D_t 开盘价相对前一日收盘 (%)
- pm_5m_amt_yi: D_t 9:30-9:34 总成交金额 (亿)
- pm_5m_high_pct: D_t 9:30-9:34 最高价相对开盘 (%)
- pm_5m_close_pct: D_t 9:30-9:34 末根收盘相对开盘 (%) 
- pm_open_red: 1 if 高开 + 5m 走绿 (高开低走)
- pm_strong_open: 1 if open_pct ≥ 0.5% + 5m_high_pct ≥ 3%
- pm_weak_open: 1 if open_pct < 0 (低开)

⚠️ 重要: 这些是 **D_t 早上 9:35 才能拿到的数据**
用法:
  - 历史回测: 拿 D_t 早盘数据训模型, 看模型能不能在 9:35 二次扫描时刷掉假反转
  - 实时: 5-6 推送当天加 9:35 cron 重新打分前 50 强档

数据源: 腾讯 m1 K (有 500 根, 约 2.5 个交易日历史 — 单股拉一次只能覆盖 D_t 在最近 2 天)
所以历史回测需要按日期回退多次拉, 慢. 但能做.

⏳ 优化: 我们只需要拉 D_t 是 reversal 或 fail 这一天的早盘 (D_t 是确定的)
EOF
"""
import json, time, sys
from pathlib import Path
from urllib.request import urlopen, Request
from datetime import datetime, timedelta

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"


def http_get(url, timeout=12):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def get_minute_bars(code, num=500):
    """拉腾讯 1m K 线 (最近 num 根, 约 num/240 个交易日)"""
    prefix = "sh" if code.startswith('6') else "sz"
    url = f'http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={prefix}{code},m1,,{num}'
    data = http_get(url)
    if not data: return []
    try:
        d = json.loads(data)
        return d.get('data', {}).get(f'{prefix}{code}', {}).get('m1', [])
    except Exception:
        return []


def get_daily_bars(code, count=400):
    """拉日 K 用于反推前收"""
    prefix = "sh" if code.startswith('6') else "sz"
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,{count},qfq'
    data = http_get(url)
    if not data: return []
    try:
        d = json.loads(data)
        return d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
    except Exception:
        return []


def calc_premarket(bars_minute, daily_map, dt_date):
    """从 1m bar + daily 算 D_t 早盘特征"""
    dt_compact = dt_date.replace('-', '')
    d_t_bars = [b for b in bars_minute if b[0].startswith(dt_compact)]
    if len(d_t_bars) < 5:
        return None
    
    first5 = d_t_bars[:5]
    open_p = float(first5[0][1])
    
    # 前收: 从日 K 找
    prev_close = None
    sorted_dates = sorted(daily_map.keys())
    for i, dd in enumerate(sorted_dates):
        if dd >= dt_date and i > 0:
            prev_close = daily_map[sorted_dates[i-1]]
            break
    if not prev_close:
        # 兜底: 用 D_t 前一日的最后 bar (但腾讯 m1 数据有限)
        return None
    
    open_pct = (open_p / prev_close - 1) * 100
    amt_5m = sum(float(b[7]) for b in first5)  # 单位: 万
    max_5m = max(float(b[3]) for b in first5)
    close_5m = float(first5[-1][2])
    high_pct = (max_5m / open_p - 1) * 100
    close_pct = (close_5m / open_p - 1) * 100
    
    return {
        "pm_open_pct": round(open_pct, 3),
        "pm_5m_amt_yi": round(amt_5m / 10000, 4),  # 万 → 亿
        "pm_5m_high_pct": round(high_pct, 3),
        "pm_5m_close_pct": round(close_pct, 3),
        "pm_open_red": 1 if open_pct >= 0.5 and close_pct < 0 else 0,
        "pm_strong_open": 1 if open_pct >= 0.5 and high_pct >= 3 else 0,
        "pm_weak_open": 1 if open_pct < 0 else 0,
    }


def main():
    src = BACKTEST_DIR / "reversal-events-2026-05-01-v9-with-pre10.json"
    with open(src) as f:
        data = json.load(f)
    events = data["events"]
    
    # 计算每个事件的 D_t
    # outcome=reversal: D_t = d0 + callback_window 天后
    # outcome=fail: D_t = d0 + 10 天后 (但用 fail_d_t 字段如果有)
    print(f"📊 events: {len(events)}")
    
    # 先统计 D_t 是否有
    has_dt = sum(1 for e in events if e.get('d_t_date') or e.get('fail_d_t_date'))
    print(f"   有 d_t_date 的: {has_dt}")
    
    # 看一个示例
    for e in events[:3]:
        print(f"   sample: code={e['code']} d0={e['d0_date']} outcome={e['outcome']} cb_window={e.get('callback_window','?')} d_t={e.get('d_t_date')} fail_dt={e.get('fail_d_t_date')}")
    
    # ⚠️ 不一定能 ev → 都补到, 因为腾讯 m1 只回看 ~2 天, 大量历史拿不到
    # 让我测下能拿到的比例
    by_code = {}
    for e in events:
        by_code.setdefault(e["code"], []).append(e)
    print(f"   unique codes: {len(by_code)}")
    
    # 先小批测 (前 20 codes), 看能拿到多少
    test_codes = list(by_code.keys())[:20]
    enriched_test = 0
    total_test = 0
    for code in test_codes:
        bars = get_minute_bars(code, num=500)
        daily = get_daily_bars(code, count=400)
        daily_map = {b[0]: float(b[2]) for b in daily}  # date → close
        for e in by_code[code]:
            dt_date = e.get('d_t_date') or e.get('fail_d_t_date')
            if not dt_date: continue
            total_test += 1
            pm = calc_premarket(bars, daily_map, dt_date)
            if pm:
                enriched_test += 1
        time.sleep(0.4)
    print(f"\n📋 测试 20 codes: {enriched_test}/{total_test} 能补 ({enriched_test/max(1,total_test)*100:.1f}%)")
    print(f"   说明: 腾讯 m1 K 只能给 ~2 天回看, 历史大部分拿不到")
    print(f"   → 需要换数据源 (新浪历史 5m K) 或者只做最近事件")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""v1.8 性能跟踪 — 累计实战表现, 对比预期, 偏离过大告警
触发: 每周一 22:30 (= 北京) 累计前一周 5 天命中, 写到 picks/v18_performance_history.json

预期:
- Top 10 ~40% (base rate 5.4% × 7.4 lift)
- Top 20 ~35%
- P≥0.85 ~50%
- P≥0.80 ~42%

如果实战连续 2 周低于 50% 预期 (Top 10 < 20%) → 告警
"""
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))

WX_CHANNEL = "openclaw-weixin"
WX_ACCOUNT = "ba28cc3242ca-im-bot"
WX_TARGET = "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat"

EXPECTED = {
    'top10_rate': 40,
    'top20_rate': 35,
    'p85_rate': 50,
    'p80_rate': 42,
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


def load_history():
    f = WS / 'picks' / 'v18_performance_history.json'
    if f.exists():
        with open(f) as fh: return json.load(fh)
    return {'days': []}


def save_history(h):
    f = WS / 'picks' / 'v18_performance_history.json'
    with open(f, 'w') as fh: json.dump(h, fh, ensure_ascii=False, indent=2)


def compute_day_perf(date):
    """读 review-{date}.json 算当天表现"""
    review = WS / 'picks' / f'review-{date}.json'
    if not review.exists(): return None
    
    with open(review) as f:
        data = json.load(f)
    
    results = data.get('v18_results', [])
    if not results: return None
    
    # 已经有 is_zt 和 chg
    sorted_v18 = sorted(results, key=lambda x: -x.get('p_v18', 0))
    
    top10 = sorted_v18[:10]
    top20 = sorted_v18[:20]
    
    p85 = [r for r in results if r.get('p_v18', 0) >= 0.85]
    p80 = [r for r in results if r.get('p_v18', 0) >= 0.80]
    p70 = [r for r in results if r.get('p_v18', 0) >= 0.70]
    
    return {
        'date': date,
        'n_total': len(results),
        'top10_zt': sum(1 for r in top10 if r.get('is_zt')),
        'top20_zt': sum(1 for r in top20 if r.get('is_zt')),
        'p85_zt': sum(1 for r in p85 if r.get('is_zt')), 'p85_n': len(p85),
        'p80_zt': sum(1 for r in p80 if r.get('is_zt')), 'p80_n': len(p80),
        'p70_zt': sum(1 for r in p70 if r.get('is_zt')), 'p70_n': len(p70),
    }


def main():
    today = datetime.now(BJT).strftime('%Y-%m-%d')
    print(f'📊 v1.8 性能跟踪 @ {today}', flush=True)
    
    h = load_history()
    existing_dates = {d['date'] for d in h['days']}
    
    # 找最近 7 天的 review 文件
    review_files = sorted((WS / 'picks').glob('review-*.json'), reverse=True)
    new_days = []
    for f in review_files[:14]:  # 最多看 14 天
        date = f.stem.replace('review-', '')
        if date in existing_dates: continue
        perf = compute_day_perf(date)
        if perf:
            new_days.append(perf)
            print(f'  + {date}: Top10={perf["top10_zt"]}/10', flush=True)
    
    h['days'].extend(new_days)
    h['days'].sort(key=lambda x: x['date'])
    save_history(h)
    
    if not h['days']:
        print('⚠️ 还没有任何 review 数据', flush=True)
        return
    
    # 累计统计
    days = h['days'][-30:]  # 最近 30 天
    total_top10_zt = sum(d['top10_zt'] for d in days)
    total_top20_zt = sum(d['top20_zt'] for d in days)
    n = len(days)
    
    p85_total_zt = sum(d['p85_zt'] for d in days)
    p85_total_n = sum(d['p85_n'] for d in days)
    p80_total_zt = sum(d['p80_zt'] for d in days)
    p80_total_n = sum(d['p80_n'] for d in days)
    
    top10_rate = total_top10_zt / (n * 10) * 100
    top20_rate = total_top20_zt / (n * 20) * 100
    p85_rate = p85_total_zt / max(1, p85_total_n) * 100
    p80_rate = p80_total_zt / max(1, p80_total_n) * 100
    
    msg_lines = [f'📊 v1.8 累计性能 ({today})', '━━━━━━━━━━━━━━━━']
    msg_lines.append(f'累计 {n} 天 ({days[0]["date"]} → {days[-1]["date"]}):')
    msg_lines.append('')
    
    def cmp(actual, expected):
        diff = actual - expected
        if diff >= -5: return f'✅ ({diff:+.1f})'
        elif diff >= -15: return f'⚠️ ({diff:+.1f})'
        else: return f'❌ ({diff:+.1f})'
    
    msg_lines.append(f'  Top 10: {top10_rate:.1f}% (预期 {EXPECTED["top10_rate"]}%) {cmp(top10_rate, EXPECTED["top10_rate"])}')
    msg_lines.append(f'  Top 20: {top20_rate:.1f}% (预期 {EXPECTED["top20_rate"]}%) {cmp(top20_rate, EXPECTED["top20_rate"])}')
    if p85_total_n > 0:
        msg_lines.append(f'  P≥0.85: {p85_rate:.1f}% (预期 {EXPECTED["p85_rate"]}%) {cmp(p85_rate, EXPECTED["p85_rate"])} (n={p85_total_n})')
    if p80_total_n > 0:
        msg_lines.append(f'  P≥0.80: {p80_rate:.1f}% (预期 {EXPECTED["p80_rate"]}%) {cmp(p80_rate, EXPECTED["p80_rate"])} (n={p80_total_n})')
    
    msg_lines.append('')
    msg_lines.append('📋 最近 7 天逐日:')
    for d in days[-7:]:
        rate = d['top10_zt'] / 10 * 100
        msg_lines.append(f'  {d["date"]}: Top10={d["top10_zt"]}/10 ({rate:.0f}%)')
    
    # 告警: 连续 2 周低于 20% Top 10
    if len(days) >= 10:
        recent = days[-10:]
        recent_top10 = sum(d['top10_zt'] for d in recent) / (10 * 10) * 100
        if recent_top10 < 20:
            msg_lines.append('')
            msg_lines.append(f'⚠️⚠️ 警告: 最近 10 天 Top 10 = {recent_top10:.1f}%, 远低于 40% 预期')
            msg_lines.append('需要考虑 retrain 或调整模型')
    
    msg = '\n'.join(msg_lines)
    print(msg, flush=True)
    
    # 累计 ≥ 5 天才发微信汇报
    if n >= 5:
        send_wechat(msg)
        print('\n✅ 已发微信', flush=True)
    else:
        print(f'\n⏸ 还只 {n} 天数据, 不发微信 (≥5 才发)', flush=True)


if __name__ == '__main__':
    main()

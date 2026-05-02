#!/usr/bin/env python3
"""HVB 命中追踪 — 北京 18:35 跑 (D 当天)
- 读 picks/hvb-{D-1}.json (昨晚推送)
- 拉今天 (D) 实际涨幅
- 算各档命中率
- 微信汇报
"""
import json, sys, urllib.request, time, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))

WX_CHANNEL = "openclaw-weixin"
WX_ACCOUNT = "ba28cc3242ca-im-bot"
WX_TARGET = "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat"


def is_zt(name, chg, code):
    if chg is None: return False
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5


def get_chg(code, target):
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,5,qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        for i, b in enumerate(bars):
            if b[0] == target and i > 0:
                return (float(b[2]) - float(bars[i-1][2])) / float(bars[i-1][2]) * 100
    except: pass
    return None


def send_wechat(msg):
    cmd = ["openclaw", "message", "send",
           "--channel", WX_CHANNEL, "--account", WX_ACCOUNT,
           "--target", WX_TARGET, "--message", msg, "--json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.now(BJT).strftime('%Y-%m-%d')
    
    # 找 D-1 推送 (前一交易日, 简单回退 1-3 天)
    for delta in [1, 2, 3, 4]:
        d_minus = (datetime.strptime(today, '%Y-%m-%d') - timedelta(days=delta)).strftime('%Y-%m-%d')
        f = WS / 'picks' / f'hvb-{d_minus}.json'
        if f.exists():
            with open(f) as fh: data = json.load(fh)
            print(f'📊 HVB 追踪: D-1={d_minus} → D={today}', flush=True)
            break
    else:
        print(f'❌ 找不到最近的 hvb 推送')
        return
    
    cands = data.get('candidates', [])
    s_tier = [c for c in cands if c['tier'] == 'S']
    a_tier = [c for c in cands if c['tier'] == 'A']
    b_tier = [c for c in cands if c['tier'] == 'B']
    
    print(f'  S/A/B 档: {len(s_tier)}/{len(a_tier)}/{len(b_tier)}', flush=True)
    
    # 拉每只票今日涨幅
    for c in cands:
        chg = get_chg(c['code'], today)
        c['chg_d'] = chg
        c['is_zt_d'] = is_zt(c.get('name'), chg, c['code'])
        time.sleep(0.03)
    
    # 统计
    def stat(sub, label):
        if not sub: return None
        zt = sum(1 for c in sub if c.get('is_zt_d'))
        avg = sum(c['chg_d'] for c in sub if c.get('chg_d') is not None) / max(1, sum(1 for c in sub if c.get('chg_d') is not None))
        rate = zt / len(sub) * 100
        return {'label': label, 'n': len(sub), 'zt': zt, 'rate': rate, 'avg_chg': avg}
    
    stats = [stat(s_tier, 'S'), stat(a_tier, 'A'), stat(b_tier, 'B')]
    stats = [s for s in stats if s]
    
    msg_lines = [f'📈 HVB 命中追踪 ({today})', '━━━━━━━━━━━━━━━━']
    msg_lines.append(f'D-1 = {d_minus}, 推送 {len(cands)} 只')
    msg_lines.append('')
    
    for s in stats:
        msg_lines.append(f'{s["label"]} 档 ({s["n"]} 只): 涨停 {s["zt"]} ({s["rate"]:.1f}%), 平均涨幅 {s["avg_chg"]:+.2f}%')
    
    # Top 5 涨幅
    valid = [c for c in cands if c.get('chg_d') is not None]
    valid.sort(key=lambda x: -x['chg_d'])
    msg_lines.append('')
    msg_lines.append('📌 Top 5 涨幅:')
    for c in valid[:5]:
        zt_s = '🚀' if c.get('is_zt_d') else ''
        msg_lines.append(f'  {c["code"]} {c["name"][:8]}: {c["chg_d"]:+.2f}% [{c["tier"]}] {zt_s}')
    
    # 落档
    out = WS / 'picks' / f'hvb-{d_minus}-with-{today}-actual.json'
    with open(out, 'w') as f:
        json.dump({'date': d_minus, 'd_actual': today, 'candidates': cands}, f, ensure_ascii=False, indent=2)
    
    msg = '\n'.join(msg_lines)
    print(msg, flush=True)
    send_wechat(msg)
    print('\n✅ 微信发送完成', flush=True)


if __name__ == '__main__':
    main()

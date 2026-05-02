#!/usr/bin/env python3
"""v1.8 / v1.9 自动命中追踪 — 当天 18:30 (北京) 跑
读取当天 9:26 推送, 拉当天 实际涨幅, 算命中率
"""
import json, sys, time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))


def get_today():
    return datetime.now(BJT).strftime('%Y-%m-%d')


def get_close_chg(code, target_date):
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,5,qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        bars = data.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        for i, b in enumerate(bars):
            if b[0] == target_date and i > 0:
                today = float(b[2]); prev = float(bars[i-1][2])
                return (today-prev)/prev*100
    except Exception:
        pass
    return None


def is_zt(name, chg, code):
    if chg is None: return False
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5


WX_CHANNEL = "openclaw-weixin"
WX_ACCOUNT = "ba28cc3242ca-im-bot"
WX_TARGET = "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat"


def send_wechat(msg):
    import subprocess, re
    cmd = ["openclaw", "message", "send",
           "--channel", WX_CHANNEL, "--account", WX_ACCOUNT,
           "--target", WX_TARGET, "--message", msg, "--json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else get_today()
    print(f'📊 v1.8 命中追踪 — {target}', flush=True)
    
    # 加载今天的 v1.8 推送
    pick_file = WS / 'picks' / f'reversal-v18-{target}.json'
    if not pick_file.exists():
        print(f'❌ 没找到 v1.8 推送 {pick_file}'); return
    
    with open(pick_file) as f:
        pushed = json.load(f)
    all_results = pushed.get('all_results', [])
    
    # 各档命中
    print(f'\n📊 推送当天命中追踪:', flush=True)
    print(f'{"档":15} | n  | 命中  | 命中率')
    print('-' * 60)
    
    for thr_name, thr in [('P≥0.85 极强', 0.85), ('P≥0.8 强档', 0.8), ('P≥0.7 中等', 0.7)]:
        sub = [r for r in all_results if r.get('p_v18', 0) >= thr]
        zt_count = 0
        for r in sub:
            chg = get_close_chg(r['code'], target)
            r['chg'] = chg
            r['is_zt'] = is_zt(r.get('name', ''), chg, r['code'])
            if r['is_zt']: zt_count += 1
            time.sleep(0.15)
        
        pct = zt_count/max(1,len(sub))*100
        print(f'{thr_name:15} | {len(sub):>2} | {zt_count:>4} | {pct:>5.1f}%', flush=True)
    
    # 落档
    out = WS / 'picks' / f'reversal-v18-track-{target}.json'
    with open(out, 'w') as f:
        json.dump({'date': target, 'results': all_results}, f, ensure_ascii=False, indent=2)
    print(f'\n💾 落档: {out}', flush=True)
    
    # 发微信汇报
    track_msg_lines = [f'📊 v1.8 命中追踪 {target}', '━━━━━━━━━━━━━━━━━━']
    for thr_name, thr in [('P≥0.85 极强', 0.85), ('P≥0.8 强档', 0.8), ('P≥0.7 中等', 0.7)]:
        sub = [r for r in all_results if r.get('p_v18', 0) >= thr]
        zt = sum(1 for r in sub if r.get('is_zt'))
        track_msg_lines.append(f'  {thr_name}: {zt}/{len(sub)} ({zt/max(1,len(sub))*100:.0f}%)')
    
    # Top 5 详情
    track_msg_lines.append('')
    track_msg_lines.append('Top 5 表现:')
    sorted_results = sorted(all_results, key=lambda x: -x.get('p_v18', 0))[:5]
    for i, r in enumerate(sorted_results, 1):
        chg = r.get('chg')
        chg_s = f'{chg:+.2f}%' if chg is not None else 'NA'
        zt_s = '✅' if r.get('is_zt') else '❌'
        track_msg_lines.append(f'  {i}. {r["code"]} {r.get("name","")[:8]} P={r.get("p_v18",0):.3f} {chg_s} {zt_s}')
    
    msg = '\n'.join(track_msg_lines)
    if send_wechat(msg):
        print('✅ 微信发送 OK', flush=True)
    else:
        print('⚠️ 微信发送失败', flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""每日盘后复盘 — 北京 16:00 跑
整合 v1.8/v1.9/v1.4 当天表现, 找漏掉的、错杀的、命中的, 形成可学习的 daily review

输出:
  - 今日各档命中率
  - Top 5 涨幅排行 (涨停/接近涨停)
  - 漏掉的票 (4-30 涨停但 v1.8 没排进 Top 30)
  - 错杀的票 (v1.8 推 Top 10 但实际跌的)
  - 经验: 哪些特征有效/失效
"""
import json, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))

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
                today = float(b[2])
                prev = float(bars[i-1][2])
                return (today - prev) / prev * 100
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


WATCH_LIST = {
    '600330': '天通股份',
    '002866': '传艺科技',
}


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else datetime.now(BJT).strftime('%Y-%m-%d')
    print(f'📊 复盘 {target}', flush=True)
    
    msg_lines = [f'📊 {target} 盘后复盘', '━━━━━━━━━━━━━━━━━━']
    
    # 先拉你的持仓股今日表现
    msg_lines.append('📌 你的持仓 (今日表现)')
    for code, name in WATCH_LIST.items():
        chg = get_close_chg(code, target)
        if chg is not None:
            zt_s = ' 🚀' if is_zt(name, chg, code) else ''
            msg_lines.append(f'  {code} {name}: {chg:+.2f}%{zt_s}')
        else:
            msg_lines.append(f'  {code} {name}: NA (拉取失败)')
    msg_lines.append('')
    
    # 1. v1.8 推送命中
    v18_file = WS / 'picks' / f'reversal-v18-{target}.json'
    if v18_file.exists():
        with open(v18_file) as f:
            v18_data = json.load(f)
        all_v18 = v18_data.get('all_results', [])
        
        # 拉实际涨幅
        for r in all_v18:
            chg = get_close_chg(r['code'], target)
            r['chg'] = chg
            r['is_zt'] = is_zt(r.get('name'), chg, r['code'])
            time.sleep(0.1)
        
        msg_lines.append('🚀 v1.8 加强档 (9:26 推送)')
        sub_085 = [r for r in all_v18 if r.get('p_v18', 0) >= 0.85]
        sub_080 = [r for r in all_v18 if r.get('p_v18', 0) >= 0.80]
        sub_070 = [r for r in all_v18 if r.get('p_v18', 0) >= 0.70]
        
        for label, sub in [('P≥0.85 极强', sub_085), ('P≥0.8 强档', sub_080), ('P≥0.7 中等', sub_070)]:
            zt = sum(1 for r in sub if r['is_zt'])
            avg_chg = sum(r['chg'] for r in sub if r.get('chg') is not None) / max(1, sum(1 for r in sub if r.get('chg') is not None))
            msg_lines.append(f'  {label}: {zt}/{len(sub)} 涨停 ({zt/max(1,len(sub))*100:.0f}%), 平均 {avg_chg:+.2f}%')
        
        # Top 5 详情
        sub_080.sort(key=lambda x: -x.get('p_v18', 0))
        msg_lines.append('')
        msg_lines.append('📌 Top 5 强档详情:')
        for i, r in enumerate(sub_080[:5], 1):
            chg = r.get('chg')
            chg_s = f'{chg:+.2f}%' if chg is not None else 'NA'
            zt_s = '✅' if r.get('is_zt') else '❌'
            msg_lines.append(f'  {i}. {r["code"]} {r.get("name","")[:8]} P={r.get("p_v18",0):.3f} {chg_s} {zt_s}')
    else:
        msg_lines.append('⚠️ v1.8 推送文件不存在 (今天可能没跑)')
    
    msg_lines.append('')
    
    # 2. v1.9 推送命中
    v19_file = WS / 'picks' / f'reversal-v19-{target}.json'
    if v19_file.exists():
        with open(v19_file) as f:
            v19_data = json.load(f)
        all_v19 = v19_data.get('all_results', [])
        sub_085 = [r for r in all_v19 if r.get('p_v19', 0) >= 0.85]
        for r in sub_085:
            if 'chg' not in r:
                chg = get_close_chg(r['code'], target)
                r['chg'] = chg
                r['is_zt'] = is_zt(r.get('name'), chg, r['code'])
                time.sleep(0.1)
        zt = sum(1 for r in sub_085 if r.get('is_zt'))
        msg_lines.append(f'🚀 v1.9 极强档 (9:36 推送): {zt}/{len(sub_085)} ({zt/max(1,len(sub_085))*100:.0f}%)')
        for r in sub_085[:3]:
            chg_s = f'{r.get("chg",0):+.2f}%' if r.get('chg') is not None else 'NA'
            zt_s = '✅' if r.get('is_zt') else '❌'
            msg_lines.append(f'  {r["code"]} {r.get("name","")[:8]} P={r.get("p_v19",0):.3f} {chg_s} {zt_s}')
    
    msg_lines.append('')
    
    # 3. v1.4 原始候选 (前一天 17:35 推送) 命中
    # 找到前一个交易日 (D-1) 的 v1.4 picks
    candidate_files = sorted((WS / 'picks').glob('reversal-v4-*.json'), reverse=True)
    candidate_files = [f for f in candidate_files 
                       if not f.name.endswith('with-4-30-actual.json')
                       and f.name < f'reversal-v4-{target}.json']
    if candidate_files:
        with open(candidate_files[0]) as f:
            v14 = json.load(f).get('candidates', [])
        # 在 all_v18 里查涨跌幅 (我们已拉过)
        v14_codes = {c['code']: c for c in v14}
        v14_zt = sum(1 for r in all_v18 if r['code'] in v14_codes and r.get('is_zt'))
        v14_in_v18 = sum(1 for r in all_v18 if r['code'] in v14_codes)
        msg_lines.append(f'📊 v1.4 原始 (D-1 17:35 {candidate_files[0].name})')
        msg_lines.append(f'   总 {len(v14)} 个候选, 其中有 9:25 数据 {v14_in_v18} 个, 涨停 {v14_zt}/{v14_in_v18} ({v14_zt/max(1,v14_in_v18)*100:.0f}%)')
        msg_lines.append('')
    
    # 4. 漏掉的票 (实际涨停但 v1.8 排名靠后)
    if v18_file.exists():
        sorted_v18 = sorted(all_v18, key=lambda x: -x.get('p_v18', 0))
        # Top 30 内的涨停
        top30_zt = sum(1 for r in sorted_v18[:30] if r['is_zt'])
        # 30 名外的涨停 (漏掉的)
        miss = [r for r in sorted_v18[30:] if r['is_zt']]
        
        if miss:
            msg_lines.append(f'😞 漏掉的涨停股 (排 30 名外): {len(miss)} 只')
            for r in miss[:5]:
                rank = sorted_v18.index(r) + 1
                msg_lines.append(f'  #{rank} {r["code"]} {r.get("name","")[:8]} P={r.get("p_v18",0):.3f} ({r.get("chg",0):+.2f}%)')
    
    msg = '\n'.join(msg_lines)
    print(msg, flush=True)
    
    # 落档
    out = WS / 'picks' / f'review-{target}.json'
    with open(out, 'w') as f:
        json.dump({'date': target, 'v18_results': all_v18 if v18_file.exists() else []}, 
                  f, ensure_ascii=False, indent=2)
    
    if send_wechat(msg):
        print('\n✅ 复盘已发微信', flush=True)
    else:
        print('\n⚠️ 微信发送失败', flush=True)


if __name__ == '__main__':
    main()

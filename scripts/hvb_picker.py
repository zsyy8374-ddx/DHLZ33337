#!/usr/bin/env python3
"""高量柱战法选股 — 每日 17:30 跑 (与 v1.4 同时)
- D-1 17:30 拉问财全市场
- 找出 量比≥3 + 当日涨停 的票 → 推送 D 候选
- 不依赖 v1.4/v1.8, 是独立战法

实证 lift (4-29 → 4-30):
- 量比≥3 + 当日涨停: 4-30 再涨停 15.8% (5.88x lift)
- 量比≥3 + 阳柱 + d0_chg≥7: 10% (3.72x)

输出: picks/hvb-{date}.json
"""
import json, subprocess, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))

WX_CHANNEL = "openclaw-weixin"
WX_ACCOUNT = "ba28cc3242ca-im-bot"
WX_TARGET = "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat"

WATCH_LIST = {
    '600330': '天通股份',
    '002866': '传艺科技',
}


def safe(v):
    import math
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except: return None


def is_zt(name, chg, code):
    if chg is None: return False
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5


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
    target = sys.argv[1] if len(sys.argv) > 1 else datetime.now(BJT).strftime('%Y-%m-%d')
    yyyymmdd = target.replace('-', '')
    
    print(f'🔬 高量柱选股 D-1={target}', flush=True)
    
    import pywencai
    df = pywencai.get(query=f'{yyyymmdd} 量比 涨跌幅 成交量 收盘价 最高价 最低价 开盘价 振幅 换手率 成交额', 
                      loop=True, timeout=180)
    if df is None or isinstance(df, dict) or not len(df):
        print('❌ 拉数据失败')
        return
    print(f'  全市场 {len(df)} 行', flush=True)
    
    candidates = []
    for _, row in df.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            if not code or 'ST' in name or '退' in name: continue
            
            ratio = safe(row.get(f'量比[{yyyymmdd}]'))
            d0_chg = safe(row.get(f'涨跌幅:前复权[{yyyymmdd}]'))
            d0_close = safe(row.get(f'收盘价:前复权[{yyyymmdd}]'))
            d0_open = safe(row.get(f'开盘价:前复权[{yyyymmdd}]'))
            d0_high = safe(row.get(f'最高价:前复权[{yyyymmdd}]'))
            d0_low = safe(row.get(f'最低价:前复权[{yyyymmdd}]'))
            turn = safe(row.get(f'换手率[{yyyymmdd}]'))
            
            if not all([ratio, d0_chg, d0_close, d0_open]): continue
            if d0_close < 2 or d0_close > 200: continue
            
            is_yang = d0_close >= d0_open
            is_zt_d0 = is_zt(name, d0_chg, code)
            
            # 评分
            # 极强档: 量比 ≥ 3 + 当日涨停  (4-30 实证 lift 5.88x)
            # 强档: 量比 ≥ 3 + 阳柱 + d0_chg ≥ 7  (lift 3.72x)
            score = 0
            tier = None
            if ratio >= 3 and is_zt_d0:
                tier = 'S'  # 极强档
                score = ratio + d0_chg + (10 if turn and turn > 5 else 0)
            elif ratio >= 3 and is_yang and d0_chg >= 7:
                tier = 'A'  # 强档
                score = ratio*0.7 + d0_chg*0.3
            elif ratio >= 3 and d0_chg >= 5:
                tier = 'B'  # 中档
                score = ratio*0.5 + d0_chg*0.3
            else:
                continue
            
            candidates.append({
                'code': code,
                'name': name,
                'd0_chg': d0_chg,
                'volume_ratio': ratio,
                'd0_close': d0_close,
                'd0_high': d0_high,
                'd0_low': d0_low,
                'is_yang': is_yang,
                'is_zt_d0': is_zt_d0,
                'turn': turn,
                'tier': tier,
                'score': score,
            })
        except Exception:
            continue
    
    print(f'  候选 (S/A/B 档): {len(candidates)}', flush=True)
    
    s_tier = sorted([c for c in candidates if c['tier']=='S'], key=lambda x: -x['score'])
    a_tier = sorted([c for c in candidates if c['tier']=='A'], key=lambda x: -x['score'])
    b_tier = sorted([c for c in candidates if c['tier']=='B'], key=lambda x: -x['score'])[:20]  # B 档限 20
    
    print(f'    S 档 (量比≥3 + 涨停): {len(s_tier)}', flush=True)
    print(f'    A 档 (量比≥3 + 阳柱 + chg≥7): {len(a_tier)}', flush=True)
    print(f'    B 档 (量比≥3 + chg≥5, top20): {len(b_tier)}', flush=True)
    
    # 落档
    out = WS / 'picks' / f'hvb-{target}.json'
    with open(out, 'w') as f:
        json.dump({'date': target, 'candidates': s_tier + a_tier + b_tier,
                   'summary': {'S': len(s_tier), 'A': len(a_tier), 'B': len(b_tier)}}, 
                  f, ensure_ascii=False, indent=2)
    print(f'\n💾 落档: {out}', flush=True)
    
    # 推送
    msg_lines = [f'🔬 高量柱战法 ({target} D-1)', '━━━━━━━━━━━━━━━━']
    msg_lines.append(f'核心: D-1 量比≥3 + 涨停 → 次日再涨停 (实证 lift 5.88x)')
    msg_lines.append('')
    
    if s_tier:
        msg_lines.append(f'⭐ S 档 (量比≥3 + 涨停, {len(s_tier)} 只)')
        for i, c in enumerate(s_tier[:8], 1):
            msg_lines.append(f'  {i}. {c["code"]} {c["name"][:8]}: 量比={c["volume_ratio"]:.1f}, 涨幅={c["d0_chg"]:+.2f}%')
        msg_lines.append('')
    
    if a_tier:
        msg_lines.append(f'✅ A 档 (量比≥3 + 阳柱 + chg≥7, {len(a_tier)} 只)')
        for i, c in enumerate(a_tier[:6], 1):
            msg_lines.append(f'  {i}. {c["code"]} {c["name"][:8]}: 量比={c["volume_ratio"]:.1f}, 涨幅={c["d0_chg"]:+.2f}%')
        msg_lines.append('')
    
    # 持仓股
    all_cands = s_tier + a_tier + b_tier
    watch_in = [c for c in all_cands if c['code'] in WATCH_LIST]
    if watch_in:
        msg_lines.append('━━━ 你的持仓 ━━━')
        for c in watch_in:
            msg_lines.append(f'  {c["code"]} {c["name"]}: {c["tier"]} 档, 量比={c["volume_ratio"]:.1f}')
        msg_lines.append('')
    
    msg_lines.append('━━━ 操作思路 ━━━')
    msg_lines.append('• S 档实证次日再涨停 ~16%')
    msg_lines.append('• 9:25 看撮合, 高开 +1% 以上可考虑')
    msg_lines.append('• 不破 D-1 低点 = 安全, 破 = 失败')
    msg_lines.append('• 5 天内不涨停就放弃')
    
    msg = '\n'.join(msg_lines)
    print(msg, flush=True)
    
    if len(sys.argv) > 2 and sys.argv[2] == 'dry':
        print('\n📭 dry-run, 跳过微信推送', flush=True)
    else:
        if send_wechat(msg):
            print('\n✅ 微信推送成功', flush=True)


if __name__ == '__main__':
    main()

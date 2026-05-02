#!/usr/bin/env python3
"""v1.8/v1.9 系统自检 — 节后 5-6 周三早上跑一次, 确保所有依赖都 OK
触发: 北京 5-6 周二 23:00 (= 美西 PDT 周二 8:00 / PST 7:00)
"""
import json, sys, subprocess, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import warnings; warnings.filterwarnings('ignore')

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))

WX_CHANNEL = "openclaw-weixin"
WX_ACCOUNT = "ba28cc3242ca-im-bot"
WX_TARGET = "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat"


def send_wechat(msg):
    import re
    cmd = ["openclaw", "message", "send",
           "--channel", WX_CHANNEL, "--account", WX_ACCOUNT,
           "--target", WX_TARGET, "--message", msg, "--json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def main():
    print(f'🔧 v1.8/v1.9 系统自检 @ {datetime.now(BJT).strftime("%Y-%m-%d %H:%M BJT")}', flush=True)
    
    issues = []
    ok_items = []
    
    # 1. 检查模型文件
    for v in ['v18', 'v19']:
        pkl = WS / 'picks' / f'{v}_sklearn_model.pkl'
        meta = WS / 'picks' / f'lr_{v}_ensemble_model.json'
        if pkl.exists() and meta.exists():
            ok_items.append(f'{v} model OK')
        else:
            issues.append(f'❌ {v} model 缺失')
    
    # 2. 检查 D-1 v1.4 picks (今天的 candidates 应该是昨天 17:30 跑的)
    # 找最近 7 天的 reversal-v4 picks
    candidate_files = sorted((WS / 'picks').glob('reversal-v4-*.json'), reverse=True)
    if candidate_files:
        latest_pick = candidate_files[0]
        try:
            with open(latest_pick) as f:
                d = json.load(f)
            n_cand = len(d.get('candidates', []))
            ok_items.append(f'最新 v1.4 picks: {latest_pick.name} ({n_cand} 候选)')
        except Exception as e:
            issues.append(f'❌ 读 {latest_pick.name} 失败: {e}')
    else:
        issues.append('❌ 没找到任何 reversal-v4 picks')
    
    # 3. 检查 pywencai 是否能跑
    try:
        import pywencai
        ok_items.append('pywencai 库 OK')
    except ImportError:
        issues.append('❌ pywencai 缺失 (pip install pywencai)')
    
    # 4. 检查 sklearn / numpy
    try:
        import sklearn, numpy
        ok_items.append(f'sklearn {sklearn.__version__}, numpy {numpy.__version__}')
    except ImportError as e:
        issues.append(f'❌ sklearn/numpy: {e}')
    
    # 5. 检查 cron 是否 enabled
    try:
        r = subprocess.run(['openclaw', 'cron', 'list', '--json'], 
                          capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            text = r.stdout
            idx = text.find('{')
            data = json.loads(text[idx:])
            v18_cron = next((j for j in data['jobs'] if 'v1.8 9:26' in j['name']), None)
            v19_cron = next((j for j in data['jobs'] if 'v1.9 9:36' in j['name']), None)
            if v18_cron and v18_cron.get('enabled'):
                ok_items.append('v1.8 9:26 cron 启用')
            else:
                issues.append('❌ v1.8 9:26 cron 未启用')
            if v19_cron and v19_cron.get('enabled'):
                ok_items.append('v1.9 9:36 cron 启用')
            else:
                issues.append('❌ v1.9 9:36 cron 未启用')
    except Exception as e:
        issues.append(f'⚠️ cron 检查失败: {e}')
    
    # 6. 试推送 (dry-run, 用最近一次的数据测一遍)
    # 跳过, 避免重复跑
    
    # 汇报
    today = datetime.now(BJT).strftime('%Y-%m-%d')
    msg_lines = [f'🔧 v1.8/v1.9 系统自检 {today}']
    msg_lines.append('━━━━━━━━━━━━━━━━')
    if not issues:
        msg_lines.append('✅ 全部 OK')
    else:
        msg_lines.append('⚠️ 发现问题:')
        for i in issues:
            msg_lines.append(f'  {i}')
    
    msg_lines.append('')
    msg_lines.append('━━━ 详情 ━━━')
    for o in ok_items[:8]:
        msg_lines.append(f'  ✅ {o}')
    if len(ok_items) > 8:
        msg_lines.append(f'  ... 还有 {len(ok_items)-8} 项 OK')
    
    msg = '\n'.join(msg_lines)
    print(msg, flush=True)
    
    # 只在有问题时才发微信打扰
    if issues:
        send_wechat(msg)
        print('\n⚠️ 已发微信告警', flush=True)
    
    sys.exit(0 if not issues else 1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Cron 错误监控 — 每 4 小时跑一次, 检查 REVERSAL 系列 cron 是否有连续错误
触发: 每 4 小时跑 (北京 0:00, 4:00, 8:00, 12:00, 16:00, 20:00)
"""
import json, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))

WX_CHANNEL = "openclaw-weixin"
WX_ACCOUNT = "ba28cc3242ca-im-bot"
WX_TARGET = "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat"


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
    # 拉 cron 列表
    r = subprocess.run(['openclaw', 'cron', 'list', '--json'], 
                       capture_output=True, text=True, timeout=30)
    text = r.stdout
    idx = text.find('{')
    if idx == -1:
        print('cron list 失败'); return
    
    try:
        data = json.loads(text[idx:])
    except Exception as e:
        print(f'JSON 解析失败: {e}'); return
    
    issues = []
    for j in data.get('jobs', []):
        name = j.get('name', '')
        if 'REVERSAL' not in name and 'A股' not in name: continue
        if not j.get('enabled'): continue
        
        s = j.get('state', {})
        consecutive = s.get('consecutiveErrors', 0)
        last_error = s.get('lastError', '')
        last_status = s.get('lastStatus', '')
        
        # 连续错误 ≥ 2 次才告警 (避免偶然)
        if consecutive >= 2 and last_status == 'error':
            issues.append({
                'name': name,
                'consecutive': consecutive,
                'last_error': last_error[:200],
            })
    
    if issues:
        msg_lines = [f'⚠️ Cron 告警 {datetime.now(BJT).strftime("%m-%d %H:%M BJT")}']
        msg_lines.append('━━━━━━━━━━━━━━━━')
        for i in issues:
            msg_lines.append(f'❌ {i["name"]}')
            msg_lines.append(f'   连续 {i["consecutive"]} 次错误')
            msg_lines.append(f'   最后错: {i["last_error"]}')
        msg = '\n'.join(msg_lines)
        send_wechat(msg)
        print(msg)
    else:
        print('✅ 全部 REVERSAL cron 正常')


if __name__ == '__main__':
    main()

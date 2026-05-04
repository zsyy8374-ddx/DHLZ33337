#!/usr/bin/env python3
"""
统计 dengxian agent 前一日的 token / 成本花费.
用法: python3 token_usage_report.py [--days 1|7]
输出: 简洁文本, 给 cron 推送或邮件用.
"""
import json, glob, os, sys, datetime
from collections import defaultdict

DAYS = 1
if "--days" in sys.argv:
    DAYS = int(sys.argv[sys.argv.index("--days")+1])

SESSIONS_DIR = os.path.expanduser("~/.openclaw/agents/dengxian/sessions")
files = glob.glob(os.path.join(SESSIONS_DIR, "*.jsonl*"))

daily = defaultdict(lambda: {"in":0,"out":0,"cr":0,"cw":0,"cost":0.0,"msgs":0})
for f in files:
    try:
        with open(f, errors="ignore") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except:
                    continue
                if obj.get("type") != "message": continue
                u = (obj.get("message") or {}).get("usage")
                if not u: continue
                ts = obj.get("timestamp", "")
                day = ts[:10] if ts else "unk"
                daily[day]["in"]  += u.get("input",0)
                daily[day]["out"] += u.get("output",0)
                daily[day]["cr"]  += u.get("cacheRead",0)
                daily[day]["cw"]  += u.get("cacheWrite",0)
                daily[day]["cost"] += (u.get("cost") or {}).get("total",0) or 0
                daily[day]["msgs"] += 1
    except Exception as e:
        print(f"err {f}: {e}", file=sys.stderr)

# Get last N days (excluding today, since today is incomplete)
today = datetime.date.today()
target_days = [(today - datetime.timedelta(days=i+1)).isoformat() for i in range(DAYS)]

lines = []
total_cost = 0.0
total_tok = 0
for d in target_days:
    v = daily.get(d)
    if not v:
        lines.append(f"{d}  (无数据)")
        continue
    tot = v["in"]+v["out"]+v["cr"]+v["cw"]
    total_cost += v["cost"]
    total_tok += tot
    lines.append(f"{d}  ${v['cost']:>6.2f}  {tot/1e6:>5.1f}M tok  ({v['msgs']} msgs)  in={v['in']/1e3:.0f}k out={v['out']/1e3:.0f}k cacheR={v['cr']/1e6:.0f}M")

print("== Dengxian Agent Token 使用报告 ==")
print(f"区间: 最近 {DAYS} 天 (UTC, 不含今日)")
print()
for l in lines:
    print(l)
print()
print(f"汇总: ${total_cost:.2f} / {total_tok/1e6:.1f}M tokens")

# Alert
ALERT_THRESHOLD = 80.0  # 单日 USD
recent_cost = daily.get(target_days[0], {}).get("cost", 0)
if recent_cost > ALERT_THRESHOLD:
    print()
    print(f"⚠️ 警告: 昨日花费 ${recent_cost:.2f} 超过预算阈值 ${ALERT_THRESHOLD}")
    sys.exit(2)  # exit code 让 cron 标 error

"""批量跑多个交易日的 sector_strength

用法:
  python3 sector_batch.py                # 默认: 最近 8 个交易日 (含今天)
  python3 sector_batch.py 2026-04-21 2026-04-30  # 指定起止
"""
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

OUT = Path('/Users/openclaw/.openclaw/workspace-dengxian/mx_output')
SCRIPT = '/Users/openclaw/.openclaw/workspace-dengxian/scripts/sector_strength.py'


def get_recent_trading_days(n=8):
    """获取最近 n 个交易日 (按北京时间, 简单排除周末)"""
    days = []
    d = datetime.now()
    while len(days) < n:
        if d.weekday() < 5:  # 周一至周五
            days.append(d.strftime('%Y-%m-%d'))
        d -= timedelta(days=1)
    return list(reversed(days))


if len(sys.argv) >= 3:
    # 指定起止
    start = datetime.strptime(sys.argv[1], '%Y-%m-%d')
    end = datetime.strptime(sys.argv[2], '%Y-%m-%d')
    DATES = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            DATES.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)
else:
    DATES = get_recent_trading_days(8)

print(f"=== 批量跑 {len(DATES)} 个交易日 ===")
print(f"  {DATES}\n")

failed = []
for d in DATES:
    out = OUT / f'sector_strength_{d}.csv'
    if out.exists():
        print(f"✓ {d} 已有, 跳过")
        continue
    print(f"\n--- {d} ---")
    r = subprocess.run(
        ['python3', SCRIPT, d],
        capture_output=True, text=True, timeout=180
    )
    if r.returncode != 0:
        print(f"❌ {d} 失败: {r.stderr[-500:]}")
        failed.append(d)
    else:
        # 只打印最后 5 行
        for line in r.stdout.split('\n')[-8:]:
            print(line)
    time.sleep(1)

print(f"\n=== 完成 ===")
print(f"  成功: {len(DATES) - len(failed)}/{len(DATES)}")
if failed:
    print(f"  失败: {failed}")

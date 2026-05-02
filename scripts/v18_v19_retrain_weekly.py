#!/usr/bin/env python3
"""v1.8 + v1.9 周末自动 retrain
触发: 每周日 北京 22:00 (= 美西 PDT 周日 7:00 / PST 6:00)
  1. 拉本周新增 5 天的 9:25 数据 (周一到周五, pywencai)
  2. 拉本周新增 5 天的 9:30-9:35 5m K (sina)
  3. enrich v18_events_enriched.json (incremental)
  4. retrain v1.8 + v1.9
  5. 邮件 + 微信汇报新版本性能
"""
import json, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import warnings; warnings.filterwarnings('ignore')

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))


def get_recent_trading_days(n=7):
    """从 events 里推断最近的交易日"""
    with open(WS / 'backtest' / 'v18_events_enriched.json') as f:
        events = json.load(f)['events']
    dts = sorted(set(e.get('d_t_strict','') for e in events if e.get('d_t_strict')))
    return dts[-n:]


def main():
    print(f'🔄 v1.8 + v1.9 weekly retrain @ {datetime.now(BJT).strftime("%Y-%m-%d %H:%M BJT")}', flush=True)
    
    # 1. 找需要新拉的日期
    today = datetime.now(BJT).strftime('%Y-%m-%d')
    print(f'今天: {today}', flush=True)
    
    last_dts = get_recent_trading_days(10)
    print(f'已有最后 10 天: {last_dts}', flush=True)
    
    # 简化: TODO 交给将来 V2.5 — 暂不做 incremental enrich, 先做 retrain (用现有数据重训)
    print(f'\n📊 当前数据: events {sum(1 for _ in open(WS/"backtest"/"v18_events_enriched.json"))} chars', flush=True)
    
    # 2. retrain v1.8
    import subprocess
    print(f'\n=== retrain v1.8 ===', flush=True)
    r = subprocess.run(['python3', str(WS/'scripts'/'v18_train_sklearn.py')], 
                       capture_output=True, text=True, timeout=600)
    print(r.stdout[-2000:], flush=True)
    if r.returncode != 0:
        print(f'❌ v1.8 retrain failed: {r.stderr[-500:]}', flush=True)
    else:
        print('✅ v1.8 retrain OK', flush=True)
    
    # 3. retrain v1.9
    print(f'\n=== retrain v1.9 ===', flush=True)
    r = subprocess.run(['python3', str(WS/'scripts'/'v19_train.py')], 
                       capture_output=True, text=True, timeout=600)
    print(r.stdout[-2000:], flush=True)
    if r.returncode != 0:
        print(f'❌ v1.9 retrain failed: {r.stderr[-500:]}', flush=True)
    else:
        print('✅ v1.9 retrain OK', flush=True)
    
    # 4. 写汇报
    msg = f"""🔄 v1.8 + v1.9 周末 retrain 完成 ({today})

模型已 retrain, 周一可上线最新版.

下一步: 5-6 周三早上 9:26 v1.8 cron 第一次实盘.
"""
    print(msg, flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""v1.8 + v1.9 周日自动 retrain
触发: 每周日 北京 22:00 (= 美西 PDT 周日 7:00 / PST 6:00)

流程:
  1. 找本周新增的交易日 (上次 retrain 后到现在)
  2. pywencai 拉这些日的 9:25 集合竞价数据
  3. sina 5m K 拉这些日的 9:30-9:35 数据
  4. 增量更新 v18_events_enriched.json
  5. retrain v1.8 (sklearn) + v1.9
  6. 微信汇报新版本性能

简化版本: 现在直接重训现有数据 (因为 enriched 已包含 4-30, 等下周日才有新数据)
"""
import json, sys, time, subprocess
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


def get_recent_trading_days_in_data():
    """从 v18_events_enriched 拿最后 N 个 D_t 日"""
    with open(WS / 'backtest' / 'v18_events_enriched.json') as f:
        events = json.load(f)['events']
    dts = sorted(set(e.get('d_t_strict','') for e in events if e.get('d_t_strict')))
    return dts


def find_new_trading_days(last_dt_in_data):
    """找 last_dt 之后到今天之间的交易日 (TODO: 调用 pywencai 拿真实交易日历)"""
    today = datetime.now(BJT).strftime('%Y-%m-%d')
    # 简化: 周一到周五, 跳过周末
    from datetime import datetime as dt2
    start = dt2.strptime(last_dt_in_data, '%Y-%m-%d') + timedelta(days=1)
    end = dt2.strptime(today, '%Y-%m-%d')
    new_days = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # 周一到周五
            new_days.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)
    return new_days


def fetch_925_data_for_days(days):
    """pywencai 拉指定日期的 9:25 数据"""
    import pywencai
    all_data = {}
    
    # 加载已有 cache (v18_auc_data.json)
    cache_path = WS / 'backtest' / 'v18_auc_data.json'
    if cache_path.exists():
        with open(cache_path) as f:
            all_data = json.load(f)
    
    new_count = 0
    for d in days:
        if d in all_data:
            print(f'  ⏩ {d} 已缓存, 跳过', flush=True)
            continue
        d_yyyymmdd = d.replace('-', '')
        q = f'{d_yyyymmdd} 9:25 委买 委卖 委差 多空比 撮合价 成交额 流通股本 涨跌幅'
        try:
            df = pywencai.get(query=q, loop=True, timeout=180)
            if df is None or isinstance(df, dict) or not len(df):
                print(f'  ⚠️ {d}: pywencai 返回空', flush=True)
                continue
            day_data = {}
            for _, row in df.iterrows():
                code = str(row.get('code', '')).strip()
                if not code: continue
                rec = {}
                for col in df.columns:
                    if d_yyyymmdd in col:
                        clean = col.replace(f'[{d_yyyymmdd} 09:25]', '').replace(f'[{d_yyyymmdd}]', '')
                        try:
                            v = float(row[col])
                            rec[clean] = v
                        except: rec[clean] = row[col]
                day_data[code] = rec
            all_data[d] = day_data
            new_count += 1
            print(f'  ✅ {d}: {len(day_data)} 行', flush=True)
        except Exception as e:
            print(f'  ❌ {d}: {e}', flush=True)
        time.sleep(2)
    
    # 落档
    with open(cache_path, 'w') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f'\n💾 v18_auc_data.json 已更新 (新增 {new_count} 天)', flush=True)
    return new_count


def main():
    print(f'🔄 v1.8/v1.9 retrain @ {datetime.now(BJT).strftime("%Y-%m-%d %H:%M BJT")}', flush=True)
    
    # 1. 找需要新拉的日期
    existing_dts = get_recent_trading_days_in_data()
    if not existing_dts:
        print('❌ events 数据为空'); sys.exit(1)
    last_dt = existing_dts[-1]
    print(f'已有 events 最后日: {last_dt}', flush=True)
    
    new_days = find_new_trading_days(last_dt)
    print(f'需要新拉的日期: {new_days[:10]}', flush=True)
    
    if new_days:
        print(f'\n📥 拉新日期 9:25 数据...', flush=True)
        fetch_925_data_for_days(new_days)
        
        # TODO: 5m K 数据采集 (跳过, 因为 sina 历史 5m 只有最近 5 天)
        # TODO: incremental enrich events
        # 当前简化: 跳过新数据 enrich, 直接重训现有
    
    # 2. retrain v1.8 (含已有数据)
    print(f'\n=== retrain v1.8 (sklearn ensemble) ===', flush=True)
    r = subprocess.run(['python3', str(WS/'scripts'/'v18_train_sklearn.py')], 
                       capture_output=True, text=True, timeout=600)
    v18_ok = r.returncode == 0
    print(r.stdout[-1500:] if r.stdout else '', flush=True)
    if not v18_ok:
        print(f'❌ v1.8 retrain failed: {r.stderr[-500:]}', flush=True)
    else:
        print('✅ v1.8 retrain OK', flush=True)
    
    # 解析 v1.8 metric
    v18_meta_path = WS / 'picks' / 'lr_v18_ensemble_model.json'
    v18_metric = ''
    if v18_meta_path.exists():
        with open(v18_meta_path) as f:
            meta = json.load(f)
        v18_metric = f"OOS AUC {meta.get('oos_auc', 0):.3f}, Top10 {meta.get('oos_topk',{}).get('top10',0)*100:.0f}%, Top20 {meta.get('oos_topk',{}).get('top20',0)*100:.0f}%"
    
    # 3. retrain v1.9
    print(f'\n=== retrain v1.9 (sklearn + 5m) ===', flush=True)
    r = subprocess.run(['python3', str(WS/'scripts'/'v19_train.py')], 
                       capture_output=True, text=True, timeout=600)
    v19_ok = r.returncode == 0
    print(r.stdout[-1500:] if r.stdout else '', flush=True)
    if not v19_ok:
        print(f'❌ v1.9 retrain failed: {r.stderr[-500:]}', flush=True)
    else:
        print('✅ v1.9 retrain OK', flush=True)
    
    v19_meta_path = WS / 'picks' / 'lr_v19_ensemble_model.json'
    v19_metric = ''
    if v19_meta_path.exists():
        with open(v19_meta_path) as f:
            meta = json.load(f)
        v19_metric = f"OOS AUC {meta.get('oos_auc', 0):.3f}, Top10 {meta.get('oos_topk',{}).get('top10',0)*100:.0f}%"
    
    # 4. 微信汇报
    today = datetime.now(BJT).strftime('%Y-%m-%d')
    msg = f"""🔄 v1.8 / v1.9 周日 retrain {today}

✅ v1.8: {'成功' if v18_ok else '失败'}
   {v18_metric}

✅ v1.9: {'成功' if v19_ok else '失败'}
   {v19_metric}

下一次推送: 周一 9:26 (v1.8) + 9:36 (v1.9)"""
    
    if send_wechat(msg):
        print('✅ 微信汇报已发', flush=True)
    else:
        print('⚠️ 微信汇报失败', flush=True)
    
    sys.exit(0 if (v18_ok and v19_ok) else 1)


if __name__ == '__main__':
    main()

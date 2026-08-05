#!/usr/bin/env python3
"""
凹口淘金形态扫描器 v2.1
使用 akshare (Sina数据源) 避免东方财富API封锁

用法:
  python3 scan_aokou.py --mode coarse --days 60 --max-samples 100
  python3 scan_aokou.py --mode fine --input /tmp/aokou_coarse.csv
  python3 scan_aokou.py --mode full --days 60
"""

import argparse, json, os, sys, time, random
from datetime import datetime, timedelta

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("pip install pandas numpy"); sys.exit(1)

try:
    import akshare as ak
except ImportError:
    print("pip install akshare"); sys.exit(1)


# ── 数据 ──────────────────────────────────────────────────

def get_stock_list():
    """全A列表（去ST/退市/北交所/B股）"""
    try:
        df = ak.stock_info_a_code_name()
        # akshare返回列名可能是 'code'/'name' 或 '代码'/'名称'
        if 'code' in df.columns:
            df = df.rename(columns={'code': '代码', 'name': '名称'})
    except:
        df = ak.stock_zh_a_spot_em()
        df = df[['代码', '名称']].copy()

    df = df[~df['名称'].str.contains('ST|退|N|C', na=False)]
    df = df[~df['代码'].str.startswith(('8', '4', '9'))]
    codes = df['代码'].tolist()
    names = df['名称'].tolist()
    return list(zip(codes, names))


def get_kline(code, days=120):
    """获取个股K线（akshare Sina源）"""
    try:
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=days+30)).strftime('%Y%m%d')
        df = ak.stock_zh_a_hist(symbol=code, period='daily',
                                start_date=start, end_date=end, adjust="qfq")
        if df is None or df.empty:
            return None
        df = df.rename(columns={
            '日期': 'date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
            '成交额': 'amount', '涨跌幅': 'pct_chg'
        })
        df['date'] = pd.to_datetime(df['date'])
        return df.sort_values('date').reset_index(drop=True)
    except:
        return None


# ── 筛选 ──────────────────────────────────────────────────

def find_highs(df, days=60, threshold=5.0):
    """找近期阶段高点（涨幅≥threshold%）"""
    recent = df.tail(days)
    return recent[recent['pct_chg'] >= threshold].index.tolist()


def check_pullback(df, high_idx):
    """检查高点后缩量回调"""
    if high_idx >= len(df) - 10:
        return None

    post = df.iloc[high_idx+1:high_idx+31]
    if len(post) < 5:
        return None

    high_price = df.iloc[high_idx]['close']
    low_price = post['close'].min()
    pullback = (high_price - low_price) / high_price * 100
    if pullback < 5:
        return None

    ma20 = df['volume'].rolling(20).mean()
    if high_idx >= 20 and pd.notna(ma20.iloc[high_idx]):
        ratio = post['volume'].mean() / ma20.iloc[high_idx]
        if ratio <= 0.75:
            return {
                'high_idx': high_idx,
                'high_date': df.iloc[high_idx]['date'],
                'high_pct': df.iloc[high_idx]['pct_chg'],
                'high_price': high_price,
                'low_price': low_price,
                'pullback': round(pullback, 1),
                'vol_ratio': round(ratio, 2),
                'current': df.iloc[-1]['close'],
            }
    return None


# ── 粗筛 ──────────────────────────────────────────────────

def coarse_scan(days=60, max_samples=200):
    print(f"🔍 凹口淘金粗筛（{days}天回溯, 最多{max_samples}只）")

    all_stocks = get_stock_list()
    total = len(all_stocks)
    print(f"  A股总数: {total}")

    # 采样（优先采样有换手率的中等市值，这里简单随机采样）
    if total > max_samples:
        random.seed(42)
        samples = random.sample(all_stocks, max_samples)
    else:
        samples = all_stocks

    print(f"  采样: {len(samples)} 只")

    candidates = []
    for i, (code, name) in enumerate(samples):
        df = get_kline(code, days=days)
        if df is None:
            continue

        for hi in find_highs(df, days=days):
            r = check_pullback(df, hi)
            if r:
                candidates.append({
                    '代码': code, '名称': name,
                    '高点日期': r['high_date'].strftime('%Y-%m-%d'),
                    '高点涨幅': round(r['high_pct'], 1),
                    '高点价': r['high_price'],
                    '回调最低': r['low_price'],
                    '回调幅度%': r['pullback'],
                    '缩量比': r['vol_ratio'],
                    '当前价': r['current'],
                })
                break

        if (i+1) % 50 == 0:
            print(f"  进度: {i+1}/{len(samples)} ({len(candidates)}候选)")

        time.sleep(0.12)

    print(f"✅ 粗筛: {len(candidates)} 候选")

    out = '/tmp/aokou_coarse.csv'
    if candidates:
        df_out = pd.DataFrame(candidates).sort_values('回调幅度%', ascending=False)
        df_out.to_csv(out, index=False, encoding='utf-8-sig')
        print(f"📁 {out}")
        print("\n📊 TOP 10:")
        for i, c in enumerate(candidates[:10]):
            print(f"  {i+1}. {c['代码']} {c['名称']} | +{c['高点涨幅']}%→回调{c['回调幅度%']}% | 缩量{c['缩量比']}x")
    else:
        print("⚠️ 无候选")

    return candidates


# ── 精筛 ──────────────────────────────────────────────────

def score_aokou(df, high_idx):
    scores = {}
    details = {}

    # ❶ 突然凹陷
    hr = df.iloc[high_idx]
    post = df.iloc[high_idx+1:min(high_idx+15, len(df))]
    if len(post) >= 3:
        drop = (hr['close'] - post['close'].min()) / hr['close'] * 100
        scores['❶凹陷'] = 1.0 if drop >= 7 else (0.7 if drop >= 5 else (0.4 if drop >= 3 else 0.2))
        details['凹陷%'] = round(drop, 1)

    # ❷ 首跌缩量
    ma20 = df['volume'].rolling(20).mean()
    if high_idx < len(ma20) and pd.notna(ma20.iloc[high_idx]):
        vr = hr['volume'] / ma20.iloc[high_idx]
        scores['❷缩量'] = 1.0 if vr <= 0.5 else (0.7 if vr <= 0.67 else (0.4 if vr <= 0.8 else 0.0))
        details['量比'] = round(vr, 2)

    # ❸ 凹底地量
    if high_idx + 5 < len(df):
        trough = df.iloc[high_idx+1:min(high_idx+25, len(df))]
        tmin = trough['volume'].min()
        amin = df['volume'].nsmallest(5).min()
        r = tmin/amin if amin > 0 else 99
        scores['❸地量'] = 1.0 if r <= 1.2 else (0.7 if r <= 1.5 else (0.4 if r <= 2.0 else 0.0))
        details['地量比'] = round(r, 2)

    # ❹ 凹底黄金柱
    gs = 0.0
    if high_idx + 3 < len(df):
        trough = df.iloc[high_idx+1:min(high_idx+25, len(df))]
        for j in range(len(trough)-3):
            rj = trough.iloc[j]
            pv = trough.iloc[max(0,j-1)]['volume']
            if rj['volume'] >= pv*1.8 and rj['pct_chg'] > 0:
                lb = rj['low']
                ok = all(trough.iloc[j+k]['low'] >= lb*0.97 for k in range(1, min(4, len(trough)-j)))
                if ok:
                    p3v = trough.iloc[j+1:j+4]['volume'].mean() if j+4 <= len(trough) else rj['volume']
                    gs = 1.0 if p3v < rj['volume']*0.7 else (0.7 if p3v < rj['volume'] else 0.5)
                    break
    scores['❹黄金柱'] = gs
    details['黄金柱'] = '有' if gs > 0 else '无'

    # ❺ 谷底换挡
    if high_idx + 10 < len(df):
        recent = df.iloc[max(high_idx+5, len(df)-15):]
        yd = (recent['close'] > recent['open']).sum()
        scores['❺换挡'] = 1.0 if yd >= 6 else (0.6 if yd >= 4 else (0.3 if yd >= 2 else 0.0))
        details['阳线'] = f'{yd}/{len(recent)}'

    # ❻ 过峰保顶
    bp = hr['close']
    if high_idx + 5 < len(df):
        pb = df.iloc[high_idx+3:]
        cur = df.iloc[-1]
        above = pb[pb['close'] > bp*0.95]
        if len(above) >= 3 and cur['close'] >= bp*0.9:
            pbs = above[above['close'] < bp*1.03]
            if len(pbs) >= 2:
                scores['❻保顶'] = 1.0 if pbs['volume'].mean() < above['volume'].mean()*0.7 else 0.6
            else:
                scores['❻保顶'] = 0.4
        else:
            scores['❻保顶'] = 0.0
        details['距平衡%'] = round((cur['close']-bp)/bp*100, 1)

    total = round(sum(scores.values()), 1)
    grade = '⭐⭐⭐ S' if total >= 5 else ('⭐⭐ A' if total >= 4 else ('⭐ B' if total >= 3 else '-'))
    is_hs = scores.get('❶凹陷', 0) >= 0.7

    return {
        '总评分': total, '等级': grade, '凹口类型': '横勺' if is_hs else '斜勺',
        '评分明细': json.dumps(scores, ensure_ascii=False), '详情': details
    }


def fine_scan(csv_path):
    print(f"🔬 精筛: {csv_path}")
    if not os.path.exists(csv_path):
        print(f"❌ 不存在"); return []

    df_in = pd.read_csv(csv_path)
    results = []

    for i, (_, row) in enumerate(df_in.iterrows()):
        code = str(row['代码']).zfill(6)
        name = row['名称']
        df = get_kline(code, days=120)
        if df is None:
            continue

        hd = row.get('高点日期', '')
        if hd:
            m = df[df['date'] == pd.to_datetime(hd)]
            hi = m.index[0] if not m.empty else (find_highs(df)[-1] if find_highs(df) else None)
        else:
            hl = find_highs(df)
            hi = hl[-1] if hl else None

        if hi is None:
            continue

        sc = score_aokou(df, hi)
        r = {
            '代码': code, '名称': name,
            '高点日期': hd, '高点涨幅': row.get('高点涨幅',''),
            '当前价': row.get('当前价',''), '回调幅度%': row.get('回调幅度%',''),
            **sc
        }
        for k, v in json.loads(sc['评分明细']).items():
            r[k] = v
        results.append(r)
        time.sleep(0.15)

    results.sort(key=lambda x: x['总评分'], reverse=True)

    sc = sum(1 for r in results if 'S' in r.get('等级',''))
    ac = sum(1 for r in results if 'A' in r.get('等级',''))
    bc = sum(1 for r in results if 'B' in r.get('等级',''))
    print(f"✅ S:{sc} A:{ac} B:{bc}")

    out_csv = '/tmp/aokou_results.csv'
    out_json = '/tmp/aokou_results.json'
    cols = ['代码','名称','总评分','等级','凹口类型','高点日期','高点涨幅','当前价','回调幅度%',
            '❶凹陷','❷缩量','❸地量','❹黄金柱','❺换挡','❻保顶']
    avail = [c for c in cols if c in pd.DataFrame(results).columns]
    pd.DataFrame(results)[avail].to_csv(out_csv, index=False, encoding='utf-8-sig')
    with open(out_json, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"📁 {out_csv} / {out_json}")

    print("\n" + "="*55)
    print("📐 凹口淘金结果")
    print("="*55)
    for r in results:
        if r['总评分'] < 3:
            continue
        icon = '🔥' if r['总评分'] >= 5 else ('⭐' if r['总评分'] >= 4 else '📌')
        cb = r.get('回调幅度%','?')
        print(f"{icon} {r['代码']} {r['名称']} | {r['总评分']}/6 {r['等级']} | "
              f"{r['凹口类型']}凹口 | 回调{cb}%")

    return results


# ── main ──────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description='凹口淘金扫描器 v2.1')
    p.add_argument('--mode', choices=['coarse','fine','full'], default='full')
    p.add_argument('--days', type=int, default=60)
    p.add_argument('--input', default='/tmp/aokou_coarse.csv')
    p.add_argument('--max-samples', type=int, default=100)
    args = p.parse_args()

    if args.mode in ('coarse','full'):
        c = coarse_scan(days=args.days, max_samples=args.max_samples)
        if args.mode == 'coarse' or not c:
            return

    if args.mode in ('fine','full'):
        fine_scan(args.input)


if __name__ == '__main__':
    main()

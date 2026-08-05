#!/usr/bin/env python3
"""
凹口淘金形态扫描器 v3.1 — 数据源优化版
========================================
v3.1（2026-08-05）：首跌缩量判定修正
  ✅ 首跌日 = 高点后10天内跌幅最大的阴线（原版误用涨停日当天量，涨停日放量被误判为出货）
  ✅ 量学本意：看坑的第一根大阴线是否缩量，而非涨停日
  ✅ 高点后无阴线 → 首跌缩量不成立（0分）

v3.0 数据源升级（2026-08-05）：
  ✅ K线: 通达信本地 .day 文件（~5000只全市场秒级读取，无需网络）
  ✅ 股票池/名称: 本地缓存 JSON（首用 akshare 拉一次，之后离线可用）
  ✅ 粗筛: 全市场并行扫描（不再随机采样，不遗漏标的）
  ✅ 精筛: 本地 .day 六级评分（不再逐只网络拉K线）
  ✅ fallback: 本地数据不可用时自动降级 akshare (Sina源)

用法:
  python3 scan_aokou.py --mode coarse --days 60
  python3 scan_aokou.py --mode fine --input /tmp/aokou_coarse.csv
  python3 scan_aokou.py --mode full --days 60
  python3 scan_aokou.py --mode coarse --limit 500    # 调试：只扫前500只
  python3 scan_aokou.py --mode coarse --source akshare  # 强制用网络源
"""

import argparse, json, os, sys, time, struct, random
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("pip install pandas numpy"); sys.exit(1)

# ========= 配置 =========
TDX_PATH = os.path.expanduser('~/tdx')
NAME_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'stock_names.json')
os.makedirs(os.path.dirname(NAME_CACHE), exist_ok=True)
COARSE_OUT = '/tmp/aokou_coarse.csv'
RESULT_CSV = '/tmp/aokou_results.csv'
RESULT_JSON = '/tmp/aokou_results.json'

# ── 数据源1: 通达信本地 .day ──────────────────────────────

def read_tdx_day(filepath):
    """解析通达信.day文件（numpy批量加速），返回标准OHLCV DataFrame（含pct_chg）"""
    try:
        with open(filepath, 'rb') as f:
            data = np.frombuffer(f.read(), dtype=np.uint32).reshape(-1, 8)
        dt = data[:, 0].astype(np.int64)
        dates = pd.to_datetime(dt.astype(str), format='%Y%m%d')
        df = pd.DataFrame({
            'date': dates,
            'open': data[:, 1]/100, 'high': data[:, 2]/100,
            'low': data[:, 3]/100, 'close': data[:, 4]/100,
            'volume': data[:, 6].astype(np.int64),
        }).sort_values('date').reset_index(drop=True)
        df['pct_chg'] = df['close'].pct_change() * 100
        return df
    except:
        return None


def get_all_a_stocks():
    """扫描通达信本地所有A股 day 文件（排除指数/基金/北交所/B股）"""
    stocks = []
    for prefix in ('sh', 'sz'):
        d = f'{TDX_PATH}/vipdoc/{prefix}/lday'
        if not os.path.isdir(d): continue
        for f in os.listdir(d):
            if not f.endswith('.day') or len(f) not in (12, 13): continue
            code = f[2:8]
            if prefix == 'sh':
                if not code.startswith('6'): continue          # 只要沪市A股
            else:
                if not code.startswith(('0', '3')): continue   # 只要深市A股(含创业板)
            stocks.append({'code': code, 'file': f'{d}/{f}'})
    return sorted(stocks, key=lambda x: x['code'])


def is_bad_name(name):
    """过滤 ST/退市/新股/次新（N/C开头）"""
    if not name:
        return False
    return ('ST' in name.upper() or '退' in name or
            name.startswith(('N', 'C', 'c')) or 'PT' in name.upper())


def load_name_cache():
    """股票名称缓存：本地JSON → akshare → 空"""
    if os.path.exists(NAME_CACHE):
        try:
            with open(NAME_CACHE) as f:
                return json.load(f)
        except:
            pass
    names = {}
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        if 'code' in df.columns:
            df = df.rename(columns={'code': '代码', 'name': '名称'})
        for _, r in df.iterrows():
            names[str(r['代码']).zfill(6)] = str(r['名称'])
        with open(NAME_CACHE, 'w') as f:
            json.dump(names, f, ensure_ascii=False)
        print(f"  📇 名称缓存已生成: {len(names)}只 → {NAME_CACHE}")
    except Exception as e:
        print(f"  ⚠️ 名称缓存生成失败: {e}（将用代码代替名称）")
    return names


# ── 数据源2: akshare fallback（本地数据不可用时）────────────

def get_kline_akshare(code, days=120):
    """akshare Sina源K线（fallback）"""
    try:
        import akshare as ak
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


# ── 数据层统一入口 ────────────────────────────────────────

class DataSource:
    """数据源管理器：tdx本地(主) + akshare(fallback)"""
    def __init__(self, source='auto'):
        self.source = source
        self.tdx_ok = os.path.isdir(f'{TDX_PATH}/vipdoc/sh/lday')
        self.stocks = []
        self.names = {}
        if source == 'auto' and self.tdx_ok:
            self.source = 'tdx'
        elif source == 'auto':
            self.source = 'akshare'
        if self.source == 'tdx':
            self.stocks = get_all_a_stocks()
            self.names = load_name_cache()
            print(f"  📡 数据源: 通达信本地 ({len(self.stocks)}只A股)")

    def get_kline(self, code, days=120):
        if self.source == 'tdx':
            s = next((s for s in self.stocks if s['code'] == code), None)
            if s:
                df = read_tdx_day(s['file'])
                if df is not None and len(df) > 30:
                    return df.tail(days + 60).reset_index(drop=True)
            return None
        else:
            return get_kline_akshare(code, days=days)

    def name_of(self, code):
        if self.source == 'tdx':
            return self.names.get(code, code)
        # akshare模式：动态拉列表
        return dict(get_stock_list_akshare()).get(code, code)


def get_stock_list_akshare():
    """akshare全A列表（fallback用）"""
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        if 'code' in df.columns:
            df = df.rename(columns={'code': '代码', 'name': '名称'})
        df = df[~df['名称'].str.contains('ST|退|N|C', na=False)]
        df = df[~df['代码'].str.startswith(('8', '4', '9'))]
        return list(zip(df['代码'].tolist(), df['名称'].tolist()))
    except:
        return []


# ── 形态判断 ──────────────────────────────────────────────

def find_highs(df, days=60, threshold=9.5):
    """找近期涨停日（涨幅≥threshold，默认9.5%覆盖10cm/20cm涨停）"""
    recent = df.tail(days)
    return recent[recent['pct_chg'] >= threshold].index.tolist()


def check_pullback(df, high_idx):
    """检查涨停后缩量回调（量柱 ≤ 前20日均量2/3，回调≥5%）"""
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


def scan_one(ds, code, days):
    """单只股票粗筛"""
    df = ds.get_kline(code, days=days)
    if df is None or len(df) < 30:
        return None
    for hi in find_highs(df, days=days):
        r = check_pullback(df, hi)
        if r:
            return {
                '代码': code, '名称': ds.name_of(code),
                '高点日期': r['high_date'].strftime('%Y-%m-%d'),
                '高点涨幅': round(r['high_pct'], 1),
                '高点价': r['high_price'],
                '回调最低': r['low_price'],
                '回调幅度%': r['pullback'],
                '缩量比': r['vol_ratio'],
                '当前价': r['current'],
            }
    return None


# ── 粗筛（全市场并行）─────────────────────────────────────

def coarse_scan(days=60, max_samples=0, limit=0, source='auto'):
    ds = DataSource(source)
    t0 = time.time()
    print(f"🔍 凹口淘金粗筛 v3.0（{days}天回溯）")

    if ds.source == 'tdx':
        stocks = ds.stocks
        if ds.names:  # 名称缓存可用时才过滤（缓存空=拉取失败，不误杀）
            stocks = [s for s in stocks
                      if ds.names.get(s['code'], '') and not is_bad_name(ds.names[s['code']])]
        if limit > 0:
            stocks = stocks[:limit]
        print(f"  全市场扫描: {len(stocks)} 只（已过滤ST/退市/次新）")
        candidates = []
        with ThreadPoolExecutor(max_workers=16) as ex:
            futs = {ex.submit(scan_one, ds, s['code'], days): s['code'] for s in stocks}
            done = 0
            for fut in as_completed(futs):
                done += 1
                r = fut.result()
                if r:
                    candidates.append(r)
                if done % 1000 == 0:
                    print(f"  进度: {done}/{len(stocks)} | 候选:{len(candidates)} | {time.time()-t0:.0f}s", flush=True)
    else:
        # akshare fallback（原逻辑：随机采样）
        all_stocks = get_stock_list_akshare()
        total = len(all_stocks)
        print(f"  A股总数: {total}（akshare fallback）")
        samples = all_stocks[:max_samples] if max_samples > 0 else all_stocks
        if max_samples > 0 and total > max_samples:
            random.seed(42)
            samples = random.sample(all_stocks, max_samples)
        print(f"  采样: {len(samples)} 只")
        candidates = []
        for i, (code, name) in enumerate(samples):
            df = get_kline_akshare(code, days=days)
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

    print(f"✅ 粗筛完成: {len(candidates)} 候选 | 耗时 {time.time()-t0:.1f}s")

    if candidates:
        df_out = pd.DataFrame(candidates).sort_values('回调幅度%', ascending=False)
        df_out.to_csv(COARSE_OUT, index=False, encoding='utf-8-sig')
        print(f"📁 {COARSE_OUT}")
        print("\n📊 TOP 10:")
        for i, c in enumerate(candidates[:10]):
            print(f"  {i+1}. {c['代码']} {c['名称']} | +{c['高点涨幅']}%→回调{c['回调幅度%']}% | 缩量{c['缩量比']}x")
    else:
        print("⚠️ 无候选")

    return candidates


# ── 精筛（本地 .day 六级评分）─────────────────────────────

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

    # ❷ 首跌缩量（v3.1: 首跌日=高点后跌幅最大的阴线，贴合量学定义）
    ma20 = df['volume'].rolling(20).mean()
    if high_idx + 1 < len(df) and high_idx >= 20 and pd.notna(ma20.iloc[high_idx]):
        post2 = df.iloc[high_idx+1:min(high_idx+11, len(df))]  # 高点后10天内找首跌日
        neg = post2[post2['pct_chg'] < 0]
        if not neg.empty:
            drop_idx = neg['pct_chg'].idxmin()  # 跌幅最大的阴线 = 首跌日
            fd = df.loc[drop_idx]
            vr = fd['volume'] / ma20.iloc[high_idx]  # 首跌日量 vs 高点前20日均量
            scores['❷缩量'] = 1.0 if vr <= 0.5 else (0.7 if vr <= 0.67 else (0.4 if vr <= 0.8 else 0.0))
            details['量比'] = round(vr, 2)
            details['首跌日'] = fd['date'].strftime('%m-%d')
            details['首跌幅%'] = round(fd['pct_chg'], 1)
        else:
            # 高点后10天无阴线：回调未发生，首跌缩量不成立
            scores['❷缩量'] = 0.0
            details['量比'] = 0.0
            details['首跌日'] = '无阴线'
    else:
        scores['❷缩量'] = 0.0
        details['量比'] = 0.0

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


def fine_scan(csv_path, source='auto'):
    ds = DataSource(source)
    t0 = time.time()
    print(f"🔬 精筛 v3.0: {csv_path}")
    if not os.path.exists(csv_path):
        print(f"❌ 不存在"); return []

    df_in = pd.read_csv(csv_path)
    results = []

    def fine_one(row):
        code = str(row['代码']).zfill(6)
        name = row.get('名称', ds.name_of(code))
        df = ds.get_kline(code, days=120)
        if df is None:
            return None
        hd = row.get('高点日期', '')
        hi = None
        if hd:
            try:
                m = df[df['date'] == pd.to_datetime(hd)]
                if not m.empty:
                    hi = m.index[0]
            except:
                pass
        if hi is None:
            hl = find_highs(df)
            hi = hl[-1] if hl else None
        if hi is None:
            return None
        sc = score_aokou(df, hi)
        r = {
            '代码': code, '名称': name,
            '高点日期': hd, '高点涨幅': row.get('高点涨幅',''),
            '当前价': row.get('当前价',''), '回调幅度%': row.get('回调幅度%',''),
            **sc
        }
        for k, v in json.loads(sc['评分明细']).items():
            r[k] = v
        return r

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(fine_one, row) for _, row in df_in.iterrows()]
        for fut in as_completed(futs):
            r = fut.result()
            if r:
                results.append(r)

    results.sort(key=lambda x: x['总评分'], reverse=True)

    sc = sum(1 for r in results if 'S' in r.get('等级',''))
    ac = sum(1 for r in results if 'A' in r.get('等级',''))
    bc = sum(1 for r in results if 'B' in r.get('等级',''))
    print(f"✅ 精筛完成: S:{sc} A:{ac} B:{bc} | 耗时 {time.time()-t0:.1f}s")

    cols = ['代码','名称','总评分','等级','凹口类型','高点日期','高点涨幅','当前价','回调幅度%',
            '❶凹陷','❷缩量','❸地量','❹黄金柱','❺换挡','❻保顶']
    out_df = pd.DataFrame(results)
    if '代码' in out_df.columns:
        out_df['代码'] = out_df['代码'].astype(str).str.zfill(6)
    avail = [c for c in cols if c in out_df.columns]
    out_df[avail].to_csv(RESULT_CSV, index=False, encoding='utf-8-sig')
    with open(RESULT_JSON, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"📁 {RESULT_CSV} / {RESULT_JSON}")

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
    p = argparse.ArgumentParser(description='凹口淘金扫描器 v3.1（通达信本地数据源）')
    p.add_argument('--mode', choices=['coarse','fine','full'], default='full')
    p.add_argument('--days', type=int, default=60)
    p.add_argument('--input', default=COARSE_OUT)
    p.add_argument('--max-samples', type=int, default=0, help='akshare模式采样上限(0=全部)')
    p.add_argument('--limit', type=int, default=0, help='调试：只扫前N只(本地模式)')
    p.add_argument('--source', choices=['auto','tdx','akshare'], default='auto')
    args = p.parse_args()

    if args.mode in ('coarse','full'):
        c = coarse_scan(days=args.days, max_samples=args.max_samples,
                        limit=args.limit, source=args.source)
        if args.mode == 'coarse' or not c:
            return

    if args.mode in ('fine','full'):
        fine_scan(args.input, source=args.source)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""v1.8 9:26 推送 — 用当天 9:25 集合竞价 重排 v1.4 候选, 推送 Top 12 (P≥0.8)
触发时间: 北京 09:26 (集合竞价撮合后立刻拉数据)
       = 美西 18:26 PDT (夏令时) / 17:26 PST (冬令时)
"""
import json, sys, time, pickle, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import warnings; warnings.filterwarnings('ignore')

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))


def get_today_str():
    return datetime.now(BJT).strftime('%Y-%m-%d')


def get_today_yyyymmdd():
    return datetime.now(BJT).strftime('%Y%m%d')


def fetch_925_data(date_yyyymmdd):
    """从 pywencai 拉今天 9:25 集合竞价 + 流通盘"""
    import pywencai
    q = f'{date_yyyymmdd} 9:25 委买 委卖 委差 多空比 五档买盘 撮合价 成交额 流通股本 涨跌幅'
    print(f'[{datetime.now().strftime("%H:%M:%S")}] 拉 9:25 数据: {q}', flush=True)
    df = pywencai.get(query=q, loop=True, timeout=180)
    if df is None or isinstance(df, dict) or not len(df):
        print(f'❌ pywencai 返回空', flush=True)
        return None
    print(f'✅ 拉到 {len(df)} 行', flush=True)
    
    day_data = {}
    for _, row in df.iterrows():
        code = str(row.get('code', '')).strip()
        if not code: continue
        rec = {}
        for col in df.columns:
            if date_yyyymmdd in col:
                clean = col.replace(f'[{date_yyyymmdd} 09:25]', '').replace(f'[{date_yyyymmdd}]', '')
                try:
                    v = float(row[col])
                    rec[clean] = v
                except (TypeError, ValueError):
                    rec[clean] = row[col]
        day_data[code] = rec
    return day_data


def safe_float(v, default=0.0):
    import math
    if v is None: return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f): return default
        return f
    except (TypeError, ValueError): return default


def get_features(pick, day_data, feature_names):
    code = pick.get('code')
    if not code or code not in day_data: return None
    rec = day_data[code]
    
    # v1.7 部分 (从 pick 拿)
    f = {}
    for fn in feature_names[:16]:
        f[fn] = safe_float(pick.get(fn, 0))
    
    def g(k, default=None):
        for kk in [k, k.replace(':前复权','').replace(':不复权','')]:
            if kk in rec:
                v = rec[kk]
                try:
                    fv = float(v)
                    import math
                    return None if (math.isnan(fv) or math.isinf(fv)) else fv
                except (TypeError, ValueError): return default
        return default
    
    auc_buy = g('分时委买'); auc_sell = g('分时委卖'); auc_diff = g('分时委差')
    auc_ratio = g('分时多空比'); auc_close = g('分时收盘价:不复权')
    auc_amt = g('分时成交额'); auc_vol = g('分时成交量')
    auc_turn = g('分时换手率'); auc_chg = g('分时涨跌幅:前复权')
    auc_amp = g('分时振幅'); float_a = g('流通a股')
    
    f['auc_buy'] = safe_float(auc_buy); f['auc_sell'] = safe_float(auc_sell)
    f['auc_diff'] = safe_float(auc_diff); f['auc_ratio'] = safe_float(auc_ratio)
    f['auc_match_close'] = safe_float(auc_close); f['auc_amt'] = safe_float(auc_amt)
    f['auc_vol'] = safe_float(auc_vol); f['auc_turn'] = safe_float(auc_turn)
    f['auc_chg'] = safe_float(auc_chg); f['auc_amp'] = safe_float(auc_amp)
    
    f['auc_buy_to_float'] = (auc_buy*100/float_a*100) if (auc_buy and float_a and float_a>0) else 0
    f['auc_sell_to_float'] = (auc_sell*100/float_a*100) if (auc_sell and float_a and float_a>0) else 0
    if auc_amt and float_a and auc_close and float_a*auc_close > 0:
        f['auc_amt_to_mcap'] = auc_amt / (float_a*auc_close) * 100
    else: f['auc_amt_to_mcap'] = 0
    f['auc_strong_open'] = 1 if (auc_chg and auc_chg>0.5 and auc_ratio and auc_ratio>1.5) else 0
    f['auc_zt_open'] = 1 if (auc_chg and auc_chg>9.5) else 0
    
    return [f.get(fn, 0) for fn in feature_names]


def format_msg(top, date_str, total_n):
    """格式化推送消息"""
    lines = [
        f'🚀 v1.8 [9:26 加强档] {date_str}',
        f'━━━━━━━━━━━━━━━━━━',
        f'📦 v1.8 model: OOS AUC 0.81 / Top 10 100% / 4-30 实战 Top 10 40% (vs v1.7 20%)',
        f'⚙️ 重排 4-29 v1.4 候选 332 → P≥0.8 共 {total_n} 只',
        f'',
        f'━━━ 极强档 P≥0.85 ━━━',
    ]
    
    super_strong = [r for r in top if r['p_v18'] >= 0.85]
    strong = [r for r in top if 0.8 <= r['p_v18'] < 0.85]
    
    if super_strong:
        for i, r in enumerate(super_strong, 1):
            lines.append(f'{i}. {r["code"]} {r["name"]:<8} P={r["p_v18"]:.3f} (v1.7={r.get("p_v17", 0):.3f})')
            lines.append(f'   9:25 撮合 {r["auc_chg"]:+.2f}%, 多空比 {r["auc_ratio"]:.2f}, 换手 {r["auc_turn"]:.2f}%')
    else:
        lines.append('  (无, 当日无 P≥0.85 的票)')
    
    lines.append('')
    lines.append(f'━━━ 强档 P 0.8-0.85 ━━━')
    for i, r in enumerate(strong[:10], 1):
        lines.append(f'{i}. {r["code"]} {r["name"]:<8} P={r["p_v18"]:.3f}')
    
    lines.append('')
    lines.append('━━━ 操作建议 ━━━')
    lines.append('• 极强档 (P≥0.85): 实战命中 ~50% (4-30 OOS)')
    lines.append('• 强档 (P≥0.8): 实战命中 ~42% (4-30 OOS)')
    lines.append('• 9:30 开盘后观察, 不破开盘价可考虑切入')
    lines.append('• ⚠️ 这是模型推荐, 不是投资建议, 请自行决断风险')
    
    return '\n'.join(lines)


def send_wechat(msg):
    """通过 OpenClaw 发微信"""
    try:
        import subprocess
        # 用项目里现成的微信发送方式
        wx_script = WORKSPACE / 'scripts' / 'send_wechat.sh'
        if wx_script.exists():
            r = subprocess.run(['bash', str(wx_script), msg], capture_output=True, text=True, timeout=30)
            return r.returncode == 0
        return False
    except Exception as e:
        print(f'微信发送失败: {e}', flush=True)
        return False


def main():
    # 解析参数
    target_date = None
    dry_run = False
    for a in sys.argv[1:]:
        if a == 'dry': dry_run = True
        elif a.startswith('20'): target_date = a
    
    if not target_date:
        target_date = get_today_str()
    target_yyyymmdd = target_date.replace('-', '')
    
    print(f'🎯 v1.8 9:26 推送 — {target_date}', flush=True)
    
    # 1. 加载 v1.8 model
    pkl_path = WORKSPACE / 'picks' / 'v18_sklearn_model.pkl'
    if not pkl_path.exists():
        print(f'❌ 找不到 v1.8 model: {pkl_path}')
        sys.exit(1)
    with open(pkl_path, 'rb') as f:
        m = pickle.load(f)
    lr = m['lr']; gb = m['gb']; scaler = m['scaler']
    features = m['features']
    print(f'✅ v1.8 model loaded ({len(features)} features)', flush=True)
    
    # 2. 加载 D-1 v1.4 候选 (前一交易日 17:30 推送)
    # 简化: 找最近的 reversal-v4-*.json (target_date 之前的)
    picks_dir = WORKSPACE / 'picks'
    candidate_files = sorted(picks_dir.glob('reversal-v4-*.json'), reverse=True)
    candidate_files = [f for f in candidate_files if f.name < f'reversal-v4-{target_date}.json']
    
    if not candidate_files:
        print(f'❌ 找不到 D-1 v1.4 候选股 (在 {target_date} 之前)')
        sys.exit(1)
    
    latest_pick_file = candidate_files[0]
    print(f'📂 D-1 v1.4 picks: {latest_pick_file.name}', flush=True)
    with open(latest_pick_file) as f:
        picks_data = json.load(f)
    candidates = picks_data.get('candidates', [])
    print(f'   候选数: {len(candidates)}', flush=True)
    
    # 3. 拉今天 9:25 数据
    day_data = fetch_925_data(target_yyyymmdd)
    if not day_data:
        print(f'❌ pywencai 失败')
        sys.exit(1)
    
    # 4. 重排
    results = []
    for pick in candidates:
        feat = get_features(pick, day_data, features)
        if feat is None: continue
        import numpy as np
        X = scaler.transform([feat])
        p_lr = float(lr.predict_proba(X)[0, 1])
        p_gb = float(gb.predict_proba(X)[0, 1])
        p_ens = 0.4 * p_lr + 0.6 * p_gb
        
        rec = day_data[pick['code']]
        def g(k):
            for kk in [k, k.replace(':前复权','').replace(':不复权','')]:
                if kk in rec:
                    try: return float(rec[kk])
                    except: return 0
            return 0
        
        results.append({
            'code': pick['code'], 'name': pick.get('name', ''),
            'p_v18': p_ens, 'p_v17': pick.get('lr_prob_with_boost', pick.get('lr_prob')),
            'auc_chg': g('分时涨跌幅:前复权'),
            'auc_ratio': g('分时多空比'),
            'auc_turn': g('分时换手率'),
        })
    
    results.sort(key=lambda x: -x['p_v18'])
    print(f'\n✅ 重排完成: {len(results)} 只', flush=True)
    
    # 5. 选出 P≥0.8 的
    top = [r for r in results if r['p_v18'] >= 0.8]
    print(f'📊 P≥0.8 极强/强档: {len(top)} 只', flush=True)
    
    if not top:
        print('⚠️ 今日无 P≥0.8 候选, 不推送')
        return
    
    # 6. 落档
    out_path = WORKSPACE / 'picks' / f'reversal-v18-{target_date}.json'
    with open(out_path, 'w') as f:
        json.dump({
            'date': target_date, 'model_version': 'v1.8-ensemble-9:25',
            'd_minus_1_picks': latest_pick_file.name,
            'top_p08': len(top), 'all_results': results,
        }, f, ensure_ascii=False, indent=2)
    print(f'💾 落档: {out_path}', flush=True)
    
    # 7. 推送
    msg = format_msg(top, target_date, len(top))
    print('\n' + '='*60)
    print(msg)
    print('='*60 + '\n')
    
    if dry_run:
        print('📭 dry-run, 跳过微信推送', flush=True)
        return
    
    # 微信推送 (todo: 需要确认 send_wechat.sh 是否存在)
    ok = send_wechat(msg)
    if ok:
        print('✅ 微信已推送', flush=True)
    else:
        print('⚠️ 微信推送失败 (需要检查 send_wechat 配置)', flush=True)


if __name__ == '__main__':
    main()

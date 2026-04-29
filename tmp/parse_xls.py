import sys

path = '/Users/openclaw/.openclaw/media/inbound/当天涨停20260427---a5473a8d-833c-41e2-b707-2c103d92abc7.xls'

try:
    with open(path, 'rb') as f:
        content = f.read().decode('gb18030')
except:
    with open(path, 'rb') as f:
        content = f.read().decode('utf-16')

lines = content.strip().split('\n')
headers = lines[0].split('\t')
data = []
for line in lines[1:]:
    cols = line.split('\t')
    if len(cols) >= 2:
        # Stock code often exported as ="000001"
        code = cols[0].replace('="', '').replace('"', '')
        name = cols[1]
        # Some columns might have weird chars or trailing/leading spaces
        data.append({
            'code': code,
            'name': name.strip(),
            'pct': cols[2].strip() if len(cols) > 2 else '',
            'sector': cols[-1].strip() if len(cols) > 0 else ''
        })

import json
print(json.dumps(data, ensure_ascii=False, indent=2))

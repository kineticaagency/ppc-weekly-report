import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from weekly_ads_monitor.env import load_env
from weekly_ads_monitor.http import request_json

s=load_env(Path('.env.local'))
out={}
goals=[3057451648,123623308,354433864,488106717,508905348]
for month in [7,8]:
    period={'from':f'2026-{month:02d}-01T00:00:00+0300','to':f'2026-{month:02d}-31T23:59:59+0300'}
    body={'period':period,'metrics':['leads','sales','revenue'],'dimensions':['marker_level_1','order_field_1'],'filters':[{'field':'marker_level_1','operation':'=','value':'яндекс.директ'}]}
    ro=request_json('https://cloud.roistat.com/api/v1/project/analytics/data?project=284716',headers={'Api-key':s['ROISTAT_API_KEY'],'Content-Type':'application/json'},body=body)
    params={'ids':57451648,'date1':f'2026-{month:02d}-01','date2':f'2026-{month:02d}-31','metrics':','.join(['ym:s:visits']+[f'ym:s:goal{g}reaches' for g in goals]+[f'ym:s:goal{g}visits' for g in goals]),'accuracy':'full','lang':'ru'}
    with urlopen(Request('https://api-metrika.yandex.net/stat/v1/data?'+urlencode(params),headers={'Authorization':'OAuth '+s['YANDEX_METRIKA_OAUTH_TOKEN']}),timeout=60) as r:
        met=json.load(r)
    out[str(month)]={'manual_statuses':ro,'metrika_goals':met}
Path('output/monthly-final-fetch.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved output/monthly-final-fetch.json')

import json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from weekly_ads_monitor.env import load_env
from weekly_ads_monitor.http import request_json
s=load_env(Path('.env.local'))
out={}
for month in [7,8]:
    p={'ids':57451648,'date1':f'2026-{month:02d}-01','date2':f'2026-{month:02d}-31','metrics':'ym:s:visits','accuracy':'full','lang':'ru'}
    def get(params):
        with urlopen(Request('https://api-metrika.yandex.net/stat/v1/data?'+urlencode(params),headers={'Authorization':'OAuth '+s['YANDEX_METRIKA_OAUTH_TOKEN']}),timeout=60) as r: return json.load(r)
    out[str(month)]={'converted':get({**p,'filters':' OR '.join(f"ym:s:goal{g}IsReached=='Yes'" for g in [3057451648,123623308,354433864,488106717,508905348])}),'sources':get({**p,'dimensions':'ym:s:lastTrafficSource','limit':100})}
    body={'period':{'from':f'2026-{month:02d}-01T00:00:00+0300','to':f'2026-{month:02d}-31T23:59:59+0300'},'metrics':['leads'],'dimensions':['order_field_1'],'filters':[{'field':'marker_level_1','operation':'=','value':'direct17'}]}
    out[str(month)]['statuses']=request_json('https://cloud.roistat.com/api/v1/project/analytics/data?project=284716',headers={'Api-key':s['ROISTAT_API_KEY'],'Content-Type':'application/json'},body=body)
Path('output/monthly-checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved output/monthly-checks.json')

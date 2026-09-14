import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from weekly_ads_monitor.env import load_env
from weekly_ads_monitor.http import request_json

s=load_env(Path('.env.local'))
def metrika(path,params=None):
    url='https://api-metrika.yandex.net/'+path+('?' + urlencode(params) if params else '')
    with urlopen(Request(url,headers={'Authorization':'OAuth '+s['YANDEX_METRIKA_OAUTH_TOKEN']}),timeout=60) as r:
        return json.load(r)
out={'goals':metrika('management/v1/counter/57451648/goals')}
for m in [7,8]:
    period={'from':f'2026-{m:02d}-01T00:00:00+0300','to':f'2026-{m:02d}-31T23:59:59+0300'}
    body={'period':period,'metrics':['leads','sales','revenue'],'dimensions':['marker_level_1']}
    r=request_json('https://cloud.roistat.com/api/v1/project/analytics/data?project=284716',headers={'Api-key':s['ROISTAT_API_KEY'],'Content-Type':'application/json'},body=body)
    out[str(m)]={'roistat_sources':r,'metrika':metrika('stat/v1/data',{'ids':57451648,'date1':f'2026-{m:02d}-01','date2':f'2026-{m:02d}-31','metrics':'ym:s:visits','dimensions':'ym:s:lastSignTrafficSource','accuracy':'full','limit':100,'lang':'ru'})}
Path('output/monthly-attribution.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved output/monthly-attribution.json')

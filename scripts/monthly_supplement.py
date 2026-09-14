import json
from pathlib import Path
from datetime import date
from urllib.request import Request, urlopen
from weekly_ads_monitor.env import load_env
from weekly_ads_monitor.http import request_json
from weekly_ads_monitor.yandex_direct import YandexDirectClient, aggregate
from weekly_ads_monitor.models import Period
import weekly_ads_monitor.yandex_direct as yd_module
original_request = yd_module.request_text
def unique_report(*args, **kwargs):
    kwargs['body']['params']['ReportName'] += '_monthly_all'
    return original_request(*args, **kwargs)
yd_module.request_text = unique_report

secrets = load_env(Path('.env.local'))
cfg = json.loads(Path('config/reduktor40.json').read_text(encoding='utf-8'))
out = {}
def get(url):
    with urlopen(Request(url, headers={'Authorization': 'OAuth '+secrets['YANDEX_METRIKA_OAUTH_TOKEN']}), timeout=60) as r:
        return json.load(r)
try:
    counters=get('https://api-metrika.yandex.net/management/v1/counters?per_page=1000')
    out['counters']=[c for c in counters.get('counters',[]) if 'reduktor40' in str(c).lower()]
except Exception as e:
    out['metrika_error']=str(e)
ro=cfg['roistat']
headers={'Api-key':secrets['ROISTAT_API_KEY'],'Content-Type':'application/json'}
base='https://cloud.roistat.com/api/v1/project/analytics/'
meta=request_json(base+'metrics-new?project='+str(ro['project_id']),headers=headers,body={})
out['sales_metric_definitions']=[m for m in meta.get('metrics',[]) if m.get('name') in ['sales','revenue','profit','roi','marketing_cost']]
for month in [7,8]:
    period=Period(date(2026,month,1),date(2026,month,31))
    d=cfg['yandex_direct']
    rows=YandexDirectClient(secrets['YANDEX_DIRECT_OAUTH_TOKEN'],d['client_login'],[],d['include_vat']).fetch(period)
    out[str(month)]={'direct_campaigns':{r['CampaignId']:r['CampaignName'] for r in rows},'direct_totals':vars(aggregate(rows)['account'])}
    body={'period':{'from':f'2026-{month:02d}-01T00:00:00+0300','to':f'2026-{month:02d}-31T23:59:59+0300'},'metrics':['leads','sales','revenue'],'dimensions':['marker_level_1','marker_level_2'],'filters':[{'field':'marker_level_1','operation':'=','value':ro['source_marker']}]}
    out[str(month)]['roistat']=request_json(base+'data?project='+str(ro['project_id']),headers=headers,body=body)
Path('output/monthly-supplement.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved output/monthly-supplement.json')

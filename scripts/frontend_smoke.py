"""Exercise private browser authentication and proxy boundaries on the server. Prints no secrets."""
import json,urllib.request,urllib.error,http.cookiejar
from pathlib import Path
values=dict(line.split('=',1) for line in Path('.env').read_text().splitlines() if line and not line.startswith('#'))
base=values['APP_ORIGIN'];jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
def request(path,method='GET',body=None,origin=None):
 headers={'Content-Type':'application/json'}
 if origin:headers['Origin']=origin
 req=urllib.request.Request(base+path,method=method,headers=headers,data=json.dumps(body).encode() if body is not None else None)
 try:
  with client.open(req,timeout=15) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:return e.code,json.load(e)
results={}
results['unauthenticated_proxy']=request('/api/operator/incidents')[0]
results['wrong_password']=request('/api/session','POST',{'password':'intentionally-incorrect-smoke-password'},base)[0] # secret-scan: fixture
results['login']=request('/api/session','POST',{'password':values['AIOPS_ADMIN_PASSWORD']},base)[0]
results['authenticated_history']=request('/api/operator/incidents')[0]
results['cross_origin_rejected']=request('/api/operator/incidents','POST',{'title':'must not be created'},'https://attacker.invalid')[0]
results['arbitrary_proxy_path_rejected']=request('/api/operator/anything')[0]
results['health_status'],health=request('/api/operator/health')
results['component_statuses']={k:v['status'] for k,v in health.get('components',{}).items()}
assert results['unauthenticated_proxy']==401 and results['wrong_password']==401 and results['login']==200
assert results['authenticated_history']==200 and results['cross_origin_rejected']==403 and results['arbitrary_proxy_path_rejected']==404
Path('reports').mkdir(exist_ok=True);Path('reports/frontend-smoke.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))

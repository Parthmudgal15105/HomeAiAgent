"""CPU-only, local Ollama structured tool choice microbenchmark. No server logs uploaded."""
import argparse,json,time,urllib.request,statistics,subprocess
from pathlib import Path

def api(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:11434'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=400) as r:return json.load(r)
def run(model):
    schema={'type':'object','properties':{'decision_type':{'type':'string','enum':['TOOL_CALL']},'tool':{'type':'string','enum':['docker_list','docker_logs','service_status','disk_usage','network_interfaces']},'arguments':{'type':'object'},'reason':{'type':'string'}},'required':['decision_type','tool','arguments','reason'],'additionalProperties':False}
    cases=[('CodeDuel returns502. DNS works, cloudflared is active, local API refused connection. Available tools docker_list, docker_logs(container,lines), service_status(service), disk_usage(path), network_interfaces. No container list yet.','docker_list'),('CodeDuel API container codeduel-api-1 exited. Need to find why it exited. Available tools docker_list, docker_logs(container,lines), service_status(service), disk_usage(path), network_interfaces.','docker_logs'),('Writes fail with no space left on device. Check filesystem capacity. Available tools docker_list, docker_logs(container,lines), service_status(service), disk_usage(path), network_interfaces.','disk_usage'),('Server cannot reach gateway or internet. Check network interface state. Available tools docker_list, docker_logs(container,lines), service_status(service), disk_usage(path), network_interfaces.','network_interfaces')]
    results=[]
    for prompt,expected in cases:
        t=time.monotonic()
        try:
            r=api('/api/chat',{'model':model,'messages':[{'role':'system','content':'You are a local infrastructure investigator. Choose the most useful next read-only tool. Return concise JSON matching schema. Never execute commands.'},{'role':'user','content':prompt}],'format':schema,'stream':False,'think':False,'keep_alive':'5m','options':{'temperature':0,'num_ctx':4096,'num_predict':160,'num_thread':3}})
            d=json.loads(r['message']['content']);results.append({'expected':expected,'decision':d,'valid_json':True,'correct_tool':d.get('tool')==expected,'latency_seconds':round(time.monotonic()-t,2),'load_seconds':round(r.get('load_duration',0)/1e9,2),'tokens_per_second':round(r.get('eval_count',0)/(r.get('eval_duration',1)/1e9),2)})
        except Exception as e:results.append({'expected':expected,'valid_json':False,'correct_tool':False,'latency_seconds':round(time.monotonic()-t,2),'error':str(e)[:300]})
        print(json.dumps({'model':model,'case':results[-1]}),flush=True)
    ps=api('/api/ps');stats=subprocess.run(['docker','stats','--no-stream','--format','{{json .}}','aiops-ollama-1'],capture_output=True,text=True).stdout
    api('/api/generate',{'model':model,'keep_alive':0})
    return {'model':model,'cases':results,'mean_latency_seconds':statistics.mean(r['latency_seconds'] for r in results),'json_validity':sum(r['valid_json'] for r in results)/len(results),'tool_selection_accuracy':sum(r['correct_tool'] for r in results)/len(results),'loaded_model_metadata':ps,'container_memory_stats':stats}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('models',nargs='+');args=p.parse_args();out={'hardware':'i5-8250U CPU, 16GB RAM, Ollama container limit3 CPUs/7GB','benchmark':'4 structured single-step tool-choice cases per model; not full incident root-cause accuracy','results':[]}
    Path('reports').mkdir(exist_ok=True)
    for m in args.models:
        out['results'].append(run(m));Path('reports/model-benchmark.json').write_text(json.dumps(out,indent=2))

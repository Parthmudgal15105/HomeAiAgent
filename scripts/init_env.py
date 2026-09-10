"""Generate server-local secrets once, refusing to overwrite an existing environment."""
from pathlib import Path
import secrets, os
p=Path('.env')
if p.exists():
    raise SystemExit('Existing .env preserved; edit it intentionally if needed.')
values={}
for line in Path('.env.example').read_text().splitlines():
    if line and not line.startswith('#'):
        k,v=line.split('=',1);values[k]=v
for key in ('POSTGRES_PASSWORD','AIOPS_API_TOKEN','AIOPS_ADMIN_PASSWORD','SESSION_SECRET','GATEWAY_TOKEN','GATEWAY_APPROVAL_SECRET'):
    values[key]=secrets.token_hex(24)
values['DATABASE_URL']='postgresql+psycopg://aiops:'+values['POSTGRES_PASSWORD']+'@127.0.0.1:15432/aiops'
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:f.write('\n'.join(k+'='+v for k,v in values.items())+'\n')
print('Generated .env with mode0600; secrets remain on this server.')

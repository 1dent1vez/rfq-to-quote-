"""Loopback HTTP acceptance smoke with a throwaway portfolio database."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]


def run():
 with tempfile.TemporaryDirectory(prefix='rfq-http-') as scratch:
  with socket.socket() as s:
   s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
  url=f'http://127.0.0.1:{port}'
  env={**os.environ,'RFQ_PORTFOLIO_DB':str(Path(scratch)/'portfolio.sqlite3')}
  server=None
  statuses=[]
  def call(path,payload=None):
   req=Request(url+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
   try:
    with urlopen(req,timeout=15) as response: status,data=response.status,json.load(response)
   except HTTPError as response: status,data=response.code,json.load(response)
   statuses.append(status)
   return status,data
  def start():
   process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.portfolio:application','--factory','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   for _ in range(100):
    try:
     if call('/api/health')[0]==200:return process
    except OSError:
     if process.poll() is not None:raise RuntimeError(process.stderr.read().decode())
     time.sleep(.05)
   process.terminate();process.wait(timeout=10);raise RuntimeError('Local server readiness failed')
  def create(rid):
   body={'request_id':rid,'customer':'Taller HTTP ficticio','message':'2 GP-149','suggestions':True}
   status,case=call('/api/requests',body);assert status==201
   return body,case
  def mutation(case,**extra):return {'version':case['version'],'actor':'Operador HTTP demo','reason':'Verificación sintética del flujo local',**extra}
  def review(case):
   payload=mutation(case,supplement='Cliente ficticio confirma dos GP-149 por referencia, sin vehículo solicitado.',lines=[{'id':'0','product_id':'gonher-gp-149','quantity':2,'scope':'reference','vehicle':None}],fragments=[])
   status,case=call('/api/requests/'+case['id']+'/review',payload);assert status==200
   return case
  def draft(case):
   status,case=call('/api/requests/'+case['id']+'/draft',mutation(case));assert status==200
   return case
  def edit(**extra):
   row=next(r for r in call('/api/inventory')[1] if r['product_id']=='gonher-gp-149')
   payload={'version':row['version'],'actor':'Operador HTTP demo','reason':'Cambio operacional sintético controlado','price':row['price'],'cost':row['cost'],'on_hand':row['on_hand'],**extra}
   assert call('/api/demo/inventory/gonher-gp-149',payload)[0]==200
  def approval(case):return mutation(case,snapshot=case['quote']['snapshot'])
  try:
   server=start()
   body,case=create('http-duplicate')
   assert call('/api/requests',body)[1]==case
   assert call('/api/requests',{**body,'message':'3 GP-149'})[0]==409
   assert len(call('/api/requests')[1])==1
   assert call('/api/requests/'+case['id']+'/draft',mutation(case))[0]==422
   initial=case
   case=review(case)
   assert case['original']==initial['original']
   assert call('/api/requests/'+case['id']+'/review',mutation(initial,supplement='No stale overwrite',lines=[],fragments=[]))[0]==422
   assert call('/api/requests/'+case['id']+'/draft',mutation(initial))[0]==409
   case=draft(case)
   assert (case['quote']['subtotal'],case['quote']['vat'],case['quote']['total'])==('300.00','48.00','348.00')
   edit(price='160.00')
   assert call('/api/requests/'+case['id']+'/approve',approval(case))[0]==409
   case=draft(case)
   edit(on_hand=1)
   assert call('/api/requests/'+case['id']+'/approve',approval(case))[0]==409
   edit(on_hand=20,cost='159.00')
   assert call('/api/requests/'+case['id']+'/draft',mutation(case))[0]==422
   edit(on_hand=2,price='150.00',cost='90.00')
   cases=[draft(review(create(rid)[1])) for rid in ('http-concurrent-a','http-concurrent-b')]
   def approve(case):return call('/api/requests/'+case['id']+'/approve',approval(case))
   with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(approve,cases))
   assert sorted(status for status,_ in results)==[200,409]
   winner=next(data for status,data in results if status==200)
   winner_draft=next(c for c in cases if c['id']==winner['id'])
   before=call('/api/inventory')[1]
   row=next(r for r in before if r['product_id']=='gonher-gp-149')
   assert row['reserved']==2 and row['available']==0
   assert approve(winner_draft)==(200,winner)
   assert call('/api/inventory')[1]==before
   audit=call('/api/inventory/audit')[1]
   assert sum(e['action']=='demo_reservation' for e in audit)==1
   server.terminate();server.wait(timeout=10);server=None
   server=start()
   assert call('/api/requests/'+winner['id'])[1]==winner
   assert call('/api/inventory/audit')[1]==audit
   print(json.dumps({'real_http':True,'requests':len(statuses),'status_counts':dict(Counter(statuses)),'verified':['duplicate idempotency/conflict','immutable original and optimistic stale revision','Decimal subtotal/IVA','stale price rejection','insufficient stock rejection','minimum gross margin rejection','concurrent approvals: one reservation, no oversell','repeated approval: no extra stock or audit effects','restart: exact case and inventory audit readback']}))
  finally:
   if server is not None:server.terminate();server.wait(timeout=10)


if __name__=='__main__':run()

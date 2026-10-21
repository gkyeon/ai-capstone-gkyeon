import os,sys,asyncio,tempfile
from pathlib import Path
from types import SimpleNamespace
os.environ['LANGCHAIN_TRACING_V2']='false';os.environ['LANGSMITH_TRACING']='false'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
# run in project eval/ when installed
from agent.graph import research_node, replan_check_node, _after_replan_check, finalize_node, build_graph
from agent.deps import SupervisorDeps
from agent.fake_llm import FastLLM,QualityLLM
from agent.retrieval import RunbookRetriever
class MCP:
 def __init__(self,fail=False,all_fail=False,search_fail=False):self.fail=fail;self.all_fail=all_fail;self.search_fail=search_fail
 async def call_tool(self,name,args):
  if name=='search_incident_runbooks':
   if self.search_fail:raise OSError('search unavailable')
   return {'status':'matched','selected':'high-latency','text':'# Test runbook\n1. Check\n2. Observe\n3. Record','candidates':[{'id':'high-latency','score':.8,'title':'test'}]}
  if self.all_fail or (self.fail and args['system_name']=='web-01'):raise ValueError('controlled failure')
  return {'system_name':args['system_name'],'status':'healthy','cpu_percent':40,'memory_percent':60,'alerts':[]}
 async def find_prompt(self,*a):return 'ops'
 async def get_prompt(self,*a,**k):return 'Test prompt'
 async def find_resource_template(self,*a):raise ValueError('template discovery fails')
async def main():
 tasks=[{'id':str(i),'agent':'research','status':'pending','kind':'monitoring','target':n} for i,n in enumerate(['auth-service','web-01'])]
 for fail,all_fail,expected in [(False,False,2),(True,False,1),(False,True,0)]:
  r=await research_node({'tasks':tasks,'events':[]},SimpleNamespace(mcp=MCP(fail,all_fail),retrieval_mode='semantic'))
  assert len(r['collected'])==expected and len(r['research_errors'])==2-expected
 # discovery failure is isolated from monitoring even in legacy mode
 t=tasks[:1]+[{'id':'r','agent':'research','status':'pending','kind':'runbook','target':'high-latency'}]
 r=await research_node({'tasks':t,'events':[]},SimpleNamespace(mcp=MCP(),retrieval_mode='legacy'));assert len(r['collected'])==1
 for all_fail,search_fail in [(False,False),(True,False),(False,True)]:
  deps=SupervisorDeps(FastLLM('f',0),QualityLLM('q',0),MCP(True,all_fail,search_fail),None,'v2')
  result=await build_graph(deps).ainvoke({'query':'auth-service 로그인 지연 원인 진단해줘','thread_id':'test','history':[],'events':[],'cost_usd':0})
  if all_fail:assert result['validation_failed'] and '자료 부족' in result['final']
  else:assert '일부 조사를 완료하지' in result['final'] and 'auth-service' in result['final']
  if search_fail and not all_fail:assert '매뉴얼을 확보하지 못' in result['final']
 # cache invalidation and empty corpus with deterministic vectors
 calls=[]
 def embed(texts):calls.append(texts);return [[1.,0.] for t in texts]
 with tempfile.TemporaryDirectory() as d:
  r=RunbookRetriever(d,embed=embed);assert r.search('x')['reason']=='empty_corpus'
  f=Path(d)/'one.md';f.write_text('# one');r.search('x');r.search('x');assert len(calls)==3
  f.write_text('# changed');r.search('x');assert len(calls)==5
 print('PASS: partial/all failures, discovery isolation, 3 full graph cases, index cache invalidation and empty corpus')
asyncio.run(main())

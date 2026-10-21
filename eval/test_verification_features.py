import sys,os,asyncio,json
from pathlib import Path
from types import SimpleNamespace
os.environ['LANGCHAIN_TRACING_V2']='false';os.environ['LANGSMITH_TRACING']='false'
p=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(p))
from agent.verifier import verify_answer,verification_report
from agent.graph import validate_node,finalize_failed_node,_after_validate
from eval.eval_validator import CASES
import server
E=[{'source':'monitoring','data':{'system_name':'auth-service','cpu_percent':40,'memory_percent':60,'status':'healthy','alerts':[]}}]
D='1) auth-service CPU 40%, 메모리 60%. 2) 추가 자료를 확인하고 기록하세요.'
async def main():
 counts=[sum(not verify_answer(c[3],c[2]) for c in CASES if c[4]),sum(bool(verify_answer(c[3],c[2])) for c in CASES if not c[4])];assert counts==[8,9]  # G8(임계치 인용)은 2차 검증 개선(임계치 해석)으로 통과
 r=verification_report(D,E,verify_answer(D,E));assert len(r['rows'])==2 and all(x['verdict']=='일치' for x in r['rows'])
 bad=D.replace('40%','99%');r2=verification_report(bad,E,verify_answer(bad,E));assert r2['rows'][0]['verdict']=='불일치'
 no='1) auth-service에 대해 추가 자료를 확인한 후 대응 절차를 결정하세요.'
 assert verification_report(no,E,[])['rows']==[]
 for prev,draft,ev,expected in [(0,D,E,'finalize'),(0,bad,E,'write'),(2,bad,E,'finalize_failed'),(0,D,[],'finalize_failed')]:
  state={'draft':draft,'collected':ev,'events':[],'validation_attempts':prev}
  state.update(await validate_node(state,SimpleNamespace(validator_mode='grounded')))
  assert _after_validate(state)==expected
  if not ev:
   failed=await finalize_failed_node(state,None);assert '자료 부족' in failed['final'] and state['validation_attempts']==1
 # Exercise real StreamingResponse generator, mock only upstream graph/store.
 class Graph:
  async def astream(self,*a,**kw):
   yield 'custom',{'type':'AnswerToken','delta':'SECRET_DRAFT'}
   yield 'updates',{'validate':{'events':[{'type':'Validation','verdict':'합격'}],'verification_report':r}}
   yield 'updates',{'finalize':{'final':'FINAL_APPROVED'}}
 class Store:
  def load(self,*a):return []
  def append(self,*a):pass
 server.app.state.deps=SimpleNamespace(version='v2',session_store=Store());server.app.state.graph=Graph()
 response=await server.chat_stream('test','test');body=''.join([s async for s in response.body_iterator]);assert 'SECRET_DRAFT' not in body and 'FINAL_APPROVED' in body and 'verification_report' in body and '[DONE]' in body
 print(json.dumps({'existing_normal_pass':f'{counts[0]}/{sum(c[4] for c in CASES)}','existing_error_block':f'{counts[1]}/{sum(not c[4] for c in CASES)}','report_matching_and_mismatch':'pass','empty_extraction':'pass','routing_cases':4,'stream_draft_suppression':'pass','stream_report':'pass'},ensure_ascii=False,indent=2))
asyncio.run(main())

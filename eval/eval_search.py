import sys,os,time,json
from pathlib import Path
os.environ['LANGSMITH_TRACING']='false';os.environ['LANGCHAIN_TRACING_V2']='false'
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from agent.retrieval import RunbookRetriever
from agent.graph import _classify_incident_type
p=ROOT;r=RunbookRetriever(p/'data/runbooks')
cases=[('로그인 요청은 성공하지만 응답 속도가 느립니다','high-latency'),('커넥션 풀 사용률이 95%까지 올라갔어요','high-latency'),('프로세서 사용률이 치솟고 처리량이 떨어졌어요','cpu-spike'),('CPU usage reached 95 percent','cpu-spike'),('프로세스가 할당받은 메모리를 반환하지 않습니다','memory-leak'),('heap keeps growing after garbage collection','memory-leak'),('요청이 시간 제한을 초과하며 연결이 끊깁니다','network-timeout'),('network timeout between services','network-timeout'),('로그 파일이 쌓여 파일을 더 저장할 수 없어요','disk-full'),('disk space is full','disk-full'),('데이터베이스에 접속할 수 없고 DB 프로세스가 죽었습니다','db-down'),('database down and connections refused','db-down'),('오늘 식사 메뉴를 추천해줘',None),('회사 휴가 규정 알려줘',None)]
(ROOT/'eval/search-cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
rows=[]
for q,expected in cases:
 t=time.perf_counter();old=_classify_incident_type([{'source':'monitoring','data':{'status':'degraded','alerts':[q]}}]);oldtime=time.perf_counter()-t
 t=time.perf_counter();res=r.search(q);elapsed=time.perf_counter()-t
 rows.append(dict(query=q,expected=expected,legacy=old,semantic=res.get('selected'),status=res['status'],candidates=res['candidates'],legacy_seconds=oldtime,semantic_seconds=elapsed))
(ROOT/'eval/search-evaluation-latest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps({'count':len(rows),'legacy_expected':sum(x['legacy']==x['expected'] for x in rows),'semantic_expected':sum(x['semantic']==x['expected'] for x in rows),'mismatches':[x for x in rows if x['semantic']!=x['expected']]},ensure_ascii=False,indent=2))

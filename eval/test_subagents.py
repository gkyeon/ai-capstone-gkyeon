"""research 서브에이전트(monitoring_agent·runbook_agent) 단위·분배 테스트. 외부 모델·서버 호출 없음."""
import asyncio, os, sys
from pathlib import Path
from types import SimpleNamespace
os.environ['LANGCHAIN_TRACING_V2'] = 'false'; os.environ['LANGSMITH_TRACING'] = 'false'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.graph import research_node
from agent.subagents import build_monitoring_agent, build_runbook_agent, build_research_agents


class MCP:
    def __init__(self, unknown=False, search_status='matched'):
        self.unknown, self.search_status, self.calls = unknown, search_status, []
    async def call_tool(self, name, args):
        self.calls.append(name)
        if name == 'search_incident_runbooks':
            if self.search_status != 'matched':
                return {'status': self.search_status, 'candidates': []}
            return {'status': 'matched', 'selected': 'cpu-spike', 'text': '# rb', 'candidates': []}
        status = 'unknown' if self.unknown else 'healthy'
        return {'system_name': args['system_name'], 'status': status, 'cpu_percent': 40.0,
                'memory_percent': 50.0, 'alerts': ['cpu high']}
    async def find_resource_template(self, *a): return 'ops', 'runbook://incident-response/{incident_type}'
    async def read_resource(self, uri, server=None):
        return '# Runbook Not Found' if 'missing' in uri else '# legacy rb'


def task(kind, target, i=0):
    return {'id': str(i), 'agent': 'research', 'status': 'pending', 'kind': kind, 'target': target}


async def main():
    # 1) 서브에이전트는 이름이 있는 별도 컴파일 그래프다
    agents = build_research_agents(SimpleNamespace(mcp=MCP(), retrieval_mode='semantic'))
    assert set(agents) == {'monitoring', 'runbook'}
    assert agents['monitoring'] is not agents['runbook']
    assert agents['monitoring'].name == 'monitoring_agent' and agents['runbook'].name == 'runbook_agent'

    # 2) monitoring_agent: 정상 / unknown은 근거로 쓰지 않고 예외
    deps = SimpleNamespace(mcp=MCP(), retrieval_mode='semantic')
    out = await build_monitoring_agent(deps).ainvoke({'task': task('monitoring', 'auth-service')})
    assert out['result']['source'] == 'monitoring' and out['result']['agent'] == 'monitoring_agent'
    try:
        await build_monitoring_agent(SimpleNamespace(mcp=MCP(unknown=True))).ainvoke({'task': task('monitoring', 'x')})
        raise SystemExit('unknown 상태가 예외 없이 통과했다')
    except ValueError as e:
        assert 'monitoring_unavailable' in str(e)

    # 3) runbook_agent: 의미 검색 matched / 미확정 / legacy 조회 / legacy 없는 문서
    collected = [{'source': 'monitoring', 'data': {'alerts': ['cpu high']}}]
    sem = SimpleNamespace(mcp=MCP(), retrieval_mode='semantic')
    out = await build_runbook_agent(sem).ainvoke({'task': task('runbook', 'cpu-spike'), 'query': 'q', 'collected': collected})
    assert out['result']['target'] == 'cpu-spike' and 'search_incident_runbooks' in sem.mcp.calls
    out = await build_runbook_agent(SimpleNamespace(mcp=MCP(search_status='no_match'), retrieval_mode='semantic')
                                    ).ainvoke({'task': task('runbook', 'x'), 'query': 'q', 'collected': []})
    assert out['result']['error'] == 'no_relevant_runbook'
    leg = SimpleNamespace(mcp=MCP(), retrieval_mode='legacy')
    out = await build_runbook_agent(leg).ainvoke({'task': task('runbook', 'cpu-spike')})
    assert out['result']['data'] == '# legacy rb' and 'search_incident_runbooks' not in leg.mcp.calls
    try:
        await build_runbook_agent(leg).ainvoke({'task': task('runbook', 'missing')}); raise SystemExit('없는 매뉴얼이 통과했다')
    except ValueError as e:
        assert 'runbook_unavailable' in str(e)

    # 4) supervisor(research_node)가 종류별로 분배하고 어느 에이전트가 처리했는지 기록한다
    r = await research_node({'tasks': [task('monitoring', 'auth-service', 0), task('monitoring', 'web-01', 1),
                                       task('runbook', 'cpu-spike', 2)], 'events': [], 'query': 'q'},
                            SimpleNamespace(mcp=MCP(), retrieval_mode='semantic'))
    done = [e for e in r['events'] if e['type'] == 'TaskCompleted']
    assert [e['agent'] for e in done] == ['monitoring_agent', 'monitoring_agent', 'runbook_agent'], done
    assert len(r['collected']) == 3 and not r['research_errors']
    print('PASS: 서브에이전트 이름·분배, monitoring unknown 가드, runbook 의미/legacy/미확정/없는 문서, supervisor 이벤트의 agent 기록')

asyncio.run(main())

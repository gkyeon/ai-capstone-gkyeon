"""근거 점검 노드(evidence_gate): 모니터링 자료가 하나도 없으면 작성 모델을 호출하지 않는다."""
import asyncio, os, sys
from pathlib import Path
from types import SimpleNamespace
os.environ['LANGCHAIN_TRACING_V2'] = 'false'; os.environ['LANGSMITH_TRACING'] = 'false'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.deps import SupervisorDeps
from agent.fake_llm import FastLLM, QualityLLM
from agent.graph import build_graph


class CountingQuality(QualityLLM):
    calls = 0
    async def write(self, *a, **k):
        CountingQuality.calls += 1
        return await super().write(*a, **k)


class MCP:
    """billing-service만 조사 대상이 되도록 모든 모니터링 조회를 unknown으로 돌려준다."""
    async def call_tool(self, name, args):
        if name == 'search_incident_runbooks':
            return {'status': 'no_match', 'candidates': []}
        return {'system_name': args['system_name'], 'status': 'unknown', 'cpu_percent': 0.0,
                'memory_percent': 0.0, 'alerts': []}
    async def find_prompt(self, *a): return 'ops'
    async def get_prompt(self, *a, **k): return 'prompt'
    async def find_resource_template(self, *a): return 'ops', 'runbook://x/{incident_type}'
    async def read_resource(self, *a, **k): return '# Runbook Not Found'


async def run(mode):
    CountingQuality.calls = 0
    deps = SupervisorDeps(FastLLM('f', 0), CountingQuality('q', 0), MCP(), None, 'v2', validator_mode=mode,
                          retrieval_mode='legacy')
    return await build_graph(deps).ainvoke({'query': 'billing-service 응답이 느려요. 장애 진단해주세요', 'thread_id': 't',
                                            'history': [], 'events': [], 'cost_usd': 0.0}), CountingQuality.calls


async def main():
    r, calls = await run('grounded')
    assert calls == 0, f'근거가 없는데 작성 모델을 {calls}번 호출했다'
    assert r['validation_failed'] and '자료 부족' in r['final'] and 'billing-service' in r['final']
    assert any(e['type'] == 'EvidenceGate' and not e['passed'] for e in r['events'])
    assert not any(e['type'] == 'DraftWritten' for e in r['events'])
    assert r['verification_report']['status'] == '자료 부족 · 검증 불가'
    # legacy(개선 전 비교용)는 기존처럼 작성 호출이 일어난다
    r, calls = await run('legacy')
    assert calls >= 1
    print(f'PASS: 근거 0건이면 작성 모델 호출 0회(개선 전 설정은 {calls}회), 자료 부족 안내·보고표·이벤트 확인')

asyncio.run(main())

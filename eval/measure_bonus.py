"""보너스 수치용 측정 2가지 (fake 작성 모델 + 실제 MCP 서버, 의미 검색 끄고 legacy 검색 사용).

1) 병렬 vs 직렬 조사 시간: research_node의 asyncio.gather를 순차 실행으로 바꾼 경우와 비교.
   주의: run_one에는 원본 제공 코드의 고정 지연 0.35초/태스크가 들어 있다(실제 I/O 지연이 아님).
   따라서 이 수치는 '구조(동시 실행)의 효과'이며 실제 서비스 지연이 아니다.
2) 모델 분리 비용 추정: 같은 토큰 수를 fast/quality 단가로 나눠 계산한 값 vs 전부 quality 단가로 계산한 값.
   단가는 server.py의 가정값(fast 0.00015, quality 0.005 USD/1k 토큰), 토큰은 글자수/4 추정이다.
사용: .venv/bin/python eval/measure_bonus.py  → eval/bonus-measure-<날짜>.md
"""
import asyncio, os, statistics, sys, time, types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.update(LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false", FAKE_DRAFT_MODE="normal")

import agent.graph as graph
import agent.nodes.research as research_mod   # research_node가 있는 모듈 — gather를 여기서 교체한다
from agent import fake_llm
from agent.deps import SupervisorDeps
from agent.fake_llm import FastLLM, QualityLLM
from agent.mcp_client import MCPClient
from agent.session_store import SqliteSessionStore

FAST_PRICE, QUALITY_PRICE = 0.00015, 0.005
RESEARCH_ROUNDS: list[float] = []   # gather 한 번(=조사 라운드)의 소요 시간
USAGE: list[tuple[str, int]] = []   # (모델 이름, 추정 토큰)

_orig_usage = fake_llm.FakeLLM._usage
def _spy_usage(self, prompt, completion):
    u = _orig_usage(self, prompt, completion)
    USAGE.append((self.name, u["tokens"]))
    return u
fake_llm.FakeLLM._usage = _spy_usage

_real = asyncio
async def _timed_gather(*aws, return_exceptions=False):
    t = time.perf_counter()
    out = await _real.gather(*aws, return_exceptions=return_exceptions)
    RESEARCH_ROUNDS.append(time.perf_counter() - t); return out
async def _serial_gather(*aws, return_exceptions=False):
    t, out = time.perf_counter(), []
    for a in aws:
        try: out.append(await a)
        except Exception as e:
            if not return_exceptions: raise
            out.append(e)
    RESEARCH_ROUNDS.append(time.perf_counter() - t); return out
def shim(gather):
    return types.SimpleNamespace(gather=gather, sleep=_real.sleep, wait_for=_real.wait_for,
                                 CancelledError=_real.CancelledError)

QUERIES = ["gateway-service에서 payments-service로 가는 요청이 타임아웃 나고 있어요. 장애 진단해주세요",
           "auth-service 로그인 응답이 느려요. 장애 원인 확인해주세요",
           "payments-service 결제 응답이 느려지고 CPU가 치솟았어요. 장애 진단해주세요",
           "cache-service 메모리 사용률이 계속 올라가고 있어요. 장애 진단해주세요"]


async def main():
    mcp = MCPClient(); await mcp.start(); store = SqliteSessionStore()
    deps = SupervisorDeps(FastLLM("fast", FAST_PRICE), QualityLLM("quality", QUALITY_PRICE), mcp, store,
                          "v2", validator_mode="grounded", retrieval_mode="legacy")
    run = lambda q: graph.build_graph(deps).ainvoke(
        {"query": q, "thread_id": "bonus", "history": [], "events": [], "cost_usd": 0.0})
    try:
        await run(QUERIES[0])   # 워밍업(MCP 첫 호출의 의도된 재시도 지연 제거)
        stats = {}
        for name, gather in (("parallel", _timed_gather), ("serial", _serial_gather)):
            research_mod.asyncio = shim(gather); RESEARCH_ROUNDS.clear(); wall = []
            for _ in range(5):
                t = time.perf_counter(); await run(QUERIES[0]); wall.append(time.perf_counter() - t)
            first = RESEARCH_ROUNDS[0::2]   # 라운드1: 모니터링 3개 / 라운드2: 재조사 1개
            stats[name] = (first, wall)
        research_mod.asyncio = _real
        USAGE.clear(); costs = []
        for q in QUERIES:
            USAGE.clear(); res = await run(q)
            fast = sum(t for n, t in USAGE if n == "fast"); qual = sum(t for n, t in USAGE if n == "quality")
            split = fast / 1000 * FAST_PRICE + qual / 1000 * QUALITY_PRICE
            allq = (fast + qual) / 1000 * QUALITY_PRICE
            costs.append((q, fast, qual, split, allq, res["cost_usd"]))
    finally:
        research_mod.asyncio = _real; await mcp.stop(); store.close()

    f = lambda xs: f"{statistics.mean(xs):.2f}s (min {min(xs):.2f}, max {max(xs):.2f})"
    out = [f"# 보너스 수치 측정 ({date.today()})", "",
           "## 1. 병렬 vs 직렬 조사 (모니터링 3개 동시 조회 라운드, 5회)", "",
           "| 방식 | 조사 라운드 시간 | 그래프 전체 시간 |", "|---|---|---|"]
    for name in ("parallel", "serial"):
        out.append(f"| {name} | {f(stats[name][0])} | {f(stats[name][1])} |")
    sp = statistics.mean(stats["serial"][0]) / statistics.mean(stats["parallel"][0])
    out += ["", f"조사 라운드 속도 비율(직렬/병렬) ≈ {sp:.1f}배. 단, 태스크당 0.35초 고정 지연은 원본의 시뮬레이션 지연이며 "
            "실제 네트워크 지연이 아니다. 동시 실행 구조의 효과만 보여준다.", "",
            "## 2. 모델 분리 비용 추정 (fake 작성 모델, 질문 4종)", "",
            "| 질문 | fast 토큰 | quality 토큰 | 분리 비용 | 전부 quality 가정 | 상태 누적 cost_usd |", "|---|---|---|---|---|---|"]
    for q, fa, qu, sc, aq, cu in costs:
        out.append(f"| {q[:22]}… | {fa} | {qu} | ${sc:.6f} | ${aq:.6f} | ${cu:.6f} |")
    ts, ta = sum(c[3] for c in costs), sum(c[4] for c in costs)
    out += ["", f"합계: 분리 ${ts:.6f} vs 전부 quality ${ta:.6f} → 약 {(1 - ts / ta):.1%} 절감 (추정).", "",
            "한계: 토큰은 글자수/4 추정, 단가는 server.py의 가정값이며 Ollama는 실제 과금이 없다. "
            "fake 모델의 정해진 응답 길이 기준이라 실모델 비용과 다르다. 모델 분리 자체는 과제 원본 구조다."]
    path = ROOT / "eval" / f"bonus-measure-{date.today():%Y%m%d}.md"
    path.write_text("\n".join(out) + "\n"); print("\n".join(out))

asyncio.run(main())

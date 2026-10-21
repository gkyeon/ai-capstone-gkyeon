"""대상 시스템 해석(폴백) 개선 전후 비교.

문제: 질문에 목록에 없는 시스템(예: billing-service)이 있으면, 실모델 계획 정규화가 이를 조용히
auth-service로 바꿨다. 그러면 사용자가 묻지 않은 시스템에 대한 '근거 있는 답변'이 만들어진다.

1) plan: OllamaFastLLM.plan의 정규화 코드를 실제로 호출한다. 모델 출력은 스텁이며 '질문에 적힌
   시스템명을 그대로 task로 내놓고, 없으면 프롬프트 지시대로 auth-service를 내놓는' 모델을 가정한다
   (실모델 호출 아님 — 정규화 코드의 동작만 본다).
2) graph: fake LLM + 실제 MCP로 전체 그래프를 돌려 사용자에게 보이는 최종 답변을 기록한다.
사용: .venv/bin/python eval/eval_targets.py [--save-baseline]   (baseline은 코드 변경 전에 저장)
"""
import asyncio, json, os, re, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.update(LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false", FAKE_DRAFT_MODE="normal")

from agent.ollama_llm import OllamaFastLLM

CASES = [
    ("A1", "billing-service 응답이 느려요. 장애 진단해주세요", "없는 시스템 → 그 이름이 조사 대상으로 남아야 함"),
    ("A2", "auth-service와 billing-service가 같이 느려요. 장애 진단해주세요", "알려진+없는 시스템 혼합"),
    ("A3", "로그인 응답이 느려요. 장애 원인 확인해주세요", "시스템명 없음 → 기본값 적용을 알려야 함"),
    ("A4", "auth-service 로그인 응답이 느려요. 장애 진단해주세요", "정상: 알려진 시스템"),
    ("A5", "gateway-service에서 payments-service로 가는 요청이 타임아웃 나요. 장애 진단해주세요", "정상: 알려진 2개"),
    ("A6", "Payments_Service 결제 응답이 느려요. 장애 진단해주세요", "대소문자·밑줄 표기 → 알려진 payments-service"),
    ("A7", "payments-service-3 인스턴스가 느려요. 장애 진단해주세요", "인스턴스 표기 → payments-service"),
    ("A8", "billing-service is slow. please diagnose the incident", "영어 질문, 없는 시스템"),
]


def stub_model_output(query: str) -> str:
    names = re.findall(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*-(?:service|\d+)", query.lower().replace("_", "-"))
    names = list(dict.fromkeys(names)) or ["auth-service"]
    return json.dumps({"needs_analysis": False,
                       "tasks": [{"agent": "research", "target": n} for n in names]})


def plan_targets(query: str) -> list[str]:
    llm = OllamaFastLLM("stub", usd_per_1k_tokens=0)
    llm._chat = lambda system, user, schema=None: (stub_model_output(query), {"usd": 0, "tokens": 0, "model": "stub"})
    result, _ = llm.plan(query, "procedure")
    return [t["target"] for t in result["tasks"] if t["agent"] == "research"]


async def graph_outcome() -> dict:
    from agent.deps import SupervisorDeps
    from agent.fake_llm import FastLLM, QualityLLM
    from agent.graph import build_graph
    from agent.mcp_client import MCPClient
    from agent.session_store import SqliteSessionStore
    mcp = MCPClient(); await mcp.start(); store = SqliteSessionStore()
    deps = SupervisorDeps(FastLLM("f", 0), QualityLLM("q", 0), mcp, store, "v2",
                          validator_mode="grounded", retrieval_mode="legacy")
    out = {}
    try:
        for cid, query, _ in CASES:
            r = await build_graph(deps).ainvoke({"query": query, "thread_id": "targets", "history": [],
                                                 "events": [], "cost_usd": 0.0})
            out[cid] = {"final": r["final"], "failed": bool(r.get("validation_failed")),
                        "collected": [c["data"]["system_name"] for c in r.get("collected", []) if c["source"] == "monitoring"],
                        "research_errors": [e["target"] for e in r.get("research_errors", [])],
                        "events": [e["type"] for e in r["events"] if e["type"].startswith("Target")]}
    finally:
        await mcp.stop(); store.close()
    return out


def main():
    rows = {cid: {"query": q, "note": n, "plan_targets": plan_targets(q)} for cid, q, n in CASES}
    for cid, o in asyncio.run(graph_outcome()).items():
        rows[cid].update(o)
    name = "targets-baseline-20261021.json" if "--save-baseline" in sys.argv else "targets-after-20261021.json"
    (ROOT / "eval" / name).write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    for cid, r in rows.items():
        print(cid, r["plan_targets"], "| 수집:", r["collected"], "| 실패:", r["research_errors"], "| 검증실패:", r["failed"])
        print("    ", r["final"][:110].replace("\n", " / "))

main()

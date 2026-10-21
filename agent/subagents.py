"""Research 서브에이전트 — 조사 작업 종류별 전문 에이전트(컴파일된 LangGraph 서브그래프).

기존에는 research_node 안의 run_one 한 함수가 모니터링 조회와 매뉴얼 조회를 모두 처리했다.
이제 메인 그래프의 research_node는 supervisor 역할만 하고(작업 분배·병렬 실행·결과 취합),
실제 조사는 아래 두 서브에이전트가 맡는다.

- monitoring_agent : 모니터링 도구 호출(재시도·15초 제한) → 관측값 검사(unknown 상태는 근거로 쓰지 않음)
- runbook_agent    : 검색 모드에 따라 의미 검색(60초 제한) 또는 기존 URI 조회(15초 제한)

두 에이전트는 서로의 상태를 모르고, 입력(task·query·collected)과 출력(result)만 주고받는다.
예외는 삼키지 않고 그대로 올려 보낸다 — 부분 실패 격리는 supervisor의 gather가 담당한다.
의존성(deps)은 메인 그래프와 같은 방식으로 주입한다(Wave 13).
"""
import asyncio
from functools import partial
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .retry import with_retry

MONITORING_TIMEOUT = 15
SEARCH_TIMEOUT = 60
LEGACY_LOOKUP_TIMEOUT = 15


class SubState(TypedDict, total=False):
    task: dict          # supervisor가 넘긴 조사 작업
    query: str          # 사용자 질문 (의미 검색 입력)
    collected: list     # 지금까지 수집된 자료 (의미 검색 입력에 알림 문구 포함)
    observation: dict   # monitoring_agent 중간 결과
    retries: int
    result: dict        # 서브에이전트의 최종 산출물


# ── monitoring_agent ────────────────────────────────────────────────────
async def _fetch_monitoring(state: SubState, deps) -> dict:
    data, retries = await asyncio.wait_for(with_retry(
        deps.mcp.call_tool, "get_monitoring_status",
        {"system_name": state["task"]["target"]}), timeout=MONITORING_TIMEOUT)
    return {"observation": data, "retries": retries}


async def _check_observation(state: SubState, deps) -> dict:
    data = state["observation"]
    if data.get("status") == "unknown":
        raise ValueError("monitoring_unavailable")   # unknown의 기본값 0은 관측값이 아니다
    return {"result": {"source": "monitoring", "data": data,
                       "retries": state.get("retries", 0), "agent": "monitoring_agent"}}


def build_monitoring_agent(deps):
    g = StateGraph(SubState)
    g.add_node("fetch", partial(_fetch_monitoring, deps=deps))
    g.add_node("check", partial(_check_observation, deps=deps))
    g.add_edge(START, "fetch")
    g.add_edge("fetch", "check")
    g.add_edge("check", END)
    return g.compile(name="monitoring_agent")


# ── runbook_agent ───────────────────────────────────────────────────────
async def _semantic_search(state: SubState, deps) -> dict:
    observations = " ".join(" ".join(c["data"].get("alerts", []))
                            for c in state.get("collected", []) if c.get("source") == "monitoring")
    result = await asyncio.wait_for(deps.mcp.call_tool(
        "search_incident_runbooks", {"query": state.get("query", "") + " " + observations}),
        timeout=SEARCH_TIMEOUT)
    if result.get("status") != "matched":
        return {"result": {"source": "runbook", "error": "no_relevant_runbook",
                           "retrieval": result, "agent": "runbook_agent"}}
    return {"result": {"source": "runbook", "data": result["text"], "retries": 0,
                       "target": result["selected"], "agent": "runbook_agent",
                       "retrieval": {k: v for k, v in result.items() if k != "text"}}}


async def _legacy_lookup(state: SubState, deps) -> dict:
    server, template = await deps.mcp.find_resource_template("get_incident_runbook")
    data = await asyncio.wait_for(deps.mcp.read_resource(
        template.format(incident_type=state["task"]["target"]), server=server),
        timeout=LEGACY_LOOKUP_TIMEOUT)
    if data.startswith("# Runbook Not Found"):
        raise ValueError("runbook_unavailable")
    return {"result": {"source": "runbook", "data": data, "retries": 0, "agent": "runbook_agent"}}


def build_runbook_agent(deps):
    g = StateGraph(SubState)
    g.add_node("semantic_search", partial(_semantic_search, deps=deps))
    g.add_node("legacy_lookup", partial(_legacy_lookup, deps=deps))
    g.add_conditional_edges(
        START, lambda _s: "semantic_search"
        if getattr(deps, "retrieval_mode", "semantic") == "semantic" else "legacy_lookup",
        {"semantic_search": "semantic_search", "legacy_lookup": "legacy_lookup"})
    g.add_edge("semantic_search", END)
    g.add_edge("legacy_lookup", END)
    return g.compile(name="runbook_agent")


def build_research_agents(deps) -> dict:
    """작업 종류(kind) → 담당 서브에이전트. supervisor(research_node)가 이 표로 분배한다."""
    return {"monitoring": build_monitoring_agent(deps), "runbook": build_runbook_agent(deps)}

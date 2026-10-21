"""근거 점검 노드 — 모니터링 근거가 없으면 작성 모델을 호출하지 않는다(비용 최적화, ADR-14)."""
from langsmith import traceable

from ..deps import SupervisorDeps
from ..state import AgentState
from ..verifier import verification_report


@traceable(name="evidence_gate_node")
async def evidence_gate_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """작성 전 근거 점검 — 모니터링 자료가 하나도 없으면 비싼 작성 모델을 호출하지 않고 곧바로
    '자료 부족 · 검증 불가'로 끝낸다(비용 최적화). 어차피 근거가 없으면 작성한 답변은 검증할 수 없고,
    이전에는 쓸모없는 작성 호출 한 번이 먼저 일어났다. legacy 검증 모드(개선 전 비교용)는 건너뛴다."""
    collected = state.get("collected", [])
    if deps.validator_mode == "legacy" or any(c.get("source") == "monitoring" for c in collected):
        return {"events": state["events"] + [{"type": "EvidenceGate", "passed": True}]}
    issues = [{"code": "no_evidence", "message": "모니터링 자료가 없어 수치 대조를 수행할 수 없습니다."}]
    return {"validation_failed": True, "validation_issues": issues,
            "verification_report": verification_report("", collected, issues),
            "events": state["events"] + [{"type": "EvidenceGate", "passed": False, "skipped": "write"}]}


def _after_evidence_gate(state: AgentState) -> str:
    return "finalize_failed" if state.get("validation_failed") else "write"

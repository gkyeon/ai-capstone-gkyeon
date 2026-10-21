"""2026-10-21 리뷰에서 찾은 미조회 수치·시스템명 부분 매칭 회귀 검사."""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
os.environ.update(LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.targets import resolve_targets
from agent.verifier import verify_answer, verification_report
from agent.graph import validate_node, _after_validate

E = [{"source": "monitoring", "data": {"system_name": "auth-service", "cpu_percent": 40,
      "memory_percent": 60, "status": "healthy", "alerts": []}}]
TAIL = " 2) 추가 지표를 확인하고 결과를 기록하세요."

async def main():
    # 다른 시스템과 같은 값/다른 값 모두 거절. CPU와 메모리, 본문과 표를 검사.
    for label, field, same in [("CPU", "cpu_percent", 40), ("메모리", "memory_percent", 60)]:
        for value in [same, 99]:
            for body in [f"auth-service CPU 40%. billing-service {label} {value}%입니다.",
                         f"조사 결과입니다.\n| 시스템 | {label} |\n|---|---|\n| auth-service | {same}% |\n| billing-service | {value}% |\n"]:
                draft = "1) " + body + TAIL
                issues = verify_answer(draft, E, unavailable=["billing-service"])
                assert any(i["code"] == f"{field}_unsupported" for i in issues), (draft, issues)
                assert verification_report(draft, E, issues)["status"] == "검증 반려"
    # 미조회 사실과 조건문을 정직하게 설명하는 답변까지 막지 않는다.
    for body in ["auth-service CPU 40%. billing-service는 조회하지 못했습니다.",
                 "auth-service CPU 40%. billing-service는 조회하지 못했습니다. CPU가 90%를 넘으면 점검하세요."]:
        assert not verify_answer("1) " + body + TAIL, E, unavailable=["billing-service"])
    known = {"auth-service", "web-01", "payments-service"}
    cases = [
        ("oauth-service 로그인 지연", [], ["oauth-service"]),
        ("web-010 CPU 급증", [], ["web-010"]),
        ("x-auth-service 응답 지연", [], ["x-auth-service"]),
        ("auth-service-backup 지연", [], ["auth-service-backup"]),
        ("auth-service와 web-01이 느려요", ["auth-service", "web-01"], []),
        ("Payments_Service", ["payments-service"], []),
        ("payments-service-3 지연", ["payments-service"], []),
        ("web-01-2 지연", ["web-01"], []),
        ("oauth-service와 auth-service", ["auth-service"], ["oauth-service"]),
        ("auth-service auth-service", ["auth-service"], []),
    ]
    for query, expected_known, expected_unknown in cases:
        result = resolve_targets(query, known)
        assert result["known"] == expected_known and result["unknown"] == expected_unknown, (query, result)
        assert not result["defaulted"]
        assert result["targets"] == expected_known + expected_unknown
    assert resolve_targets("로그인이 느려요", known)["defaulted"]
    # 정확한 이름이 인스턴스처럼 보여도 실제 등록된 시스템이면 우선한다.
    assert resolve_targets("payments-service-3", known | {"payments-service-3"})["targets"] == ["payments-service-3"]
    bad = "1) auth-service CPU 40%. billing-service CPU 40%." + TAIL
    for attempts, expected in [(0, "write"), (2, "finalize_failed")]:
        state = {"draft": bad, "collected": E, "events": [], "validation_attempts": attempts,
                 "research_errors": [{"target": "billing-service"}]}
        state.update(await validate_node(state, SimpleNamespace(validator_mode="grounded")))
        assert _after_validate(state) == expected, state
    print("PASS: 미조회 수치 8건, 정직한 미조회/임계치 2건, 대상 해석 12건, 재작성/실패 분기 2건")

asyncio.run(main())

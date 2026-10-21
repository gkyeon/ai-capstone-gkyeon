"""개선 전(legacy) vs 개선 후(grounded) 검증기 비교.

1) 오프라인 평가셋: 같은 (수집 자료, 답변) 사례를 두 검증기에 넣어 판정을 비교한다.
2) --e2e: 실제 그래프(fake LLM + 실제 MCP 서버)를 FAKE_DRAFT_MODE별로 돌려
   재작성 횟수·최종 결과·소요 시간을 비교한다.

실행: .venv/bin/python eval/eval_validator.py [--e2e]
"""
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.graph import _legacy_validate
from agent.verifier import verify_answer


def mon(name, cpu, mem, status="degraded"):
    return {"source": "monitoring", "data": {
        "system_name": name, "status": status, "cpu_percent": cpu,
        "memory_percent": mem, "alerts": []}}


AUTH, WEB, PAY = mon("auth-service", 78.3, 61.2), mon("web-01", 34.5, 48.1, "healthy"), \
    mon("payments-service", 91.4, 55.2)
TAIL = " 3) 정상화 확인 후 재발 방지 대책을 문서화하세요."

# (id, 설명, 수집 자료, 답변, 기대: True=통과해야 함 / False=차단해야 함)
CASES = [
    ("G1", "정상: 두 시스템 수치 일치", [AUTH, WEB],
     "1) 모니터링: auth-service CPU 78.3%, web-01 CPU 34.5% 2) 커넥션 풀을 점검하세요." + TAIL, True),
    ("G2", "정상: 단일 시스템", [PAY],
     "1) payments-service 상태=degraded, CPU 91.4% 2) 인스턴스를 재시작하세요." + TAIL, True),
    ("G3", "정상: 반올림 인용(78.3→78)", [AUTH],
     "1) auth-service의 CPU는 약 78%로 높습니다. 2) 풀 설정을 확인하세요." + TAIL, True),
    ("G4", "정상: 'CPU 사용률은 N%로' 서술형", [AUTH, WEB],
     "1) auth-service는 CPU 사용률은 78.3%로 높고 web-01은 CPU 사용률이 34.5%로 정상입니다."
     " 2) 풀을 점검하세요." + TAIL, True),
    ("G5", "정상: 인스턴스 표기(payments-service-3)", [PAY],
     "1) payments-service CPU 91.4%, payments-service-3 인스턴스가 느립니다. 2) 재시작하세요." + TAIL, True),
    ("G6", "정상: CPU+메모리 일치", [AUTH],
     "1) auth-service CPU 78.3%, 메모리 61.2% 2) 풀을 점검하세요." + TAIL, True),
    ("G7", "정상(경계): 수치 없이 시스템명만", [AUTH],
     "1) auth-service가 degraded 상태입니다. 2) 풀 설정을 점검하세요." + TAIL, True),
    ("G8", "정상(한계 탐침): 임계치 80%를 CPU 옆에 인용", [AUTH],
     "1) auth-service CPU 78.3%, CPU 임계치 80%에 근접했습니다. 2) 풀을 점검하세요." + TAIL, True),
    ("B1", "오류: CPU 수치 틀림", [AUTH],
     "1) auth-service CPU 93.3%로 매우 높습니다. 2) 풀을 점검하세요." + TAIL, False),
    ("B2", "오류: 다른 시스템 수치 섞음(바꿔 씀)", [AUTH, WEB],
     "1) auth-service CPU 34.5%, web-01 CPU 78.3% 2) 풀을 점검하세요." + TAIL, False),
    ("B3", "오류: 수집 안 된 시스템 언급", [AUTH],
     "1) auth-service CPU 78.3%, billing-service도 느립니다. 2) 풀을 점검하세요." + TAIL, False),
    ("B4", "오류: 메모리 수치 틀림", [AUTH],
     "1) auth-service CPU 78.3%, 메모리 85.0% 2) 풀을 점검하세요." + TAIL, False),
    ("B5", "오류: 시스템명 없이 근거 없는 수치", [AUTH],
     "1) CPU 사용률이 99%로 매우 높습니다. 2) 서비스를 재시작하고 풀을 점검하세요." + TAIL, False),
    ("B6", "오류: 너무 짧은 답변", [AUTH], "재시작하면 됩니다.", False),
    ("B7", "오류: 번호 절차 없음(수치는 일치)", [AUTH],
     "auth-service는 CPU 78.3%로 높으니 커넥션 풀 설정을 점검하고 재시작하세요, 확인 후 문서화하세요.", False),
    ("B8", "오류: 2개 시스템 중 한쪽만 틀림", [AUTH, WEB],
     "1) auth-service CPU 78.3%, web-01 CPU 60.0% 2) 풀을 점검하세요." + TAIL, False),
    ("B9", "오류: 근거와 다른 시스템명으로 대체", [AUTH],
     "1) payments-service CPU 91.4%로 높습니다. 2) 인스턴스를 재시작하세요." + TAIL, False),
]


def legacy_ok(draft):
    return _legacy_validate(draft, attempts=1)[0]


def offline():
    rows, t_old, t_new = [], 0.0, 0.0
    for cid, desc, collected, draft, should_pass in CASES:
        t = time.perf_counter(); old = legacy_ok(draft); t_old += time.perf_counter() - t
        t = time.perf_counter(); issues = verify_answer(draft, collected); t_new += time.perf_counter() - t
        rows.append((cid, desc, should_pass, old, not issues, [i["code"] for i in issues]))
    good = [r for r in rows if r[2]]
    bad = [r for r in rows if not r[2]]
    out = ["## 오프라인 평가셋 (동일 사례 %d개: 정상 %d, 오류 %d, G8은 한계 탐침)" % (len(rows), len(good), len(bad)), "",
           "| 사례 | 설명 | 기대 | 개선 전 | 개선 후 | 개선 후 검출 사유 |", "|---|---|---|---|---|---|"]
    mark = lambda ok: "통과" if ok else "차단"
    for cid, desc, sp, old, new, codes in rows:
        flag = "" if new == sp else " ❌"
        out.append(f"| {cid} | {desc} | {mark(sp)} | {mark(old)} | {mark(new)}{flag} | {', '.join(codes)} |")
    pct = lambda n, d: f"{n}/{d} ({n / d:.0%})"
    out += ["", "| 지표 | 개선 전 | 개선 후 |", "|---|---|---|",
            f"| 잘못된 답변 차단율 | {pct(sum(not r[3] for r in bad), len(bad))} | {pct(sum(not r[4] for r in bad), len(bad))} |",
            f"| 정상 답변 통과율 | {pct(sum(r[3] for r in good), len(good))} | {pct(sum(r[4] for r in good), len(good))} |",
            f"| 검증 1회 평균 시간 | {t_old / len(rows) * 1e6:.1f}µs | {t_new / len(rows) * 1e6:.1f}µs |"]
    return "\n".join(out)


async def e2e():
    from agent.deps import SupervisorDeps
    from agent.fake_llm import FastLLM, QualityLLM
    from agent.graph import build_graph
    from agent.mcp_client import MCPClient
    from agent.session_store import SqliteSessionStore

    query = "auth-service 로그인 응답이 느려요. 장애 원인 확인해주세요"
    mcp = MCPClient(); await mcp.start()
    store = SqliteSessionStore()
    out = ["## 그래프 전체 실행 (fake LLM + 실제 MCP, 질문: `%s`)" % query, "",
           "| 작성 모드 | 검증기 | 재작성(시도) 횟수 | 최종 결과 | 소요 시간 |", "|---|---|---|---|---|"]
    try:
        for mode in ("normal", "wrong_cpu_once", "cross_system", "always_wrong"):
            os.environ["FAKE_DRAFT_MODE"] = mode
            for vmode in ("legacy", "grounded"):
                deps = SupervisorDeps(FastLLM("f", 0.00015), QualityLLM("q", 0.005), mcp, store,
                                      "v2", validator_mode=vmode, retrieval_mode="legacy")
                t = time.perf_counter()
                res = await build_graph(deps).ainvoke(
                    {"query": query, "thread_id": "eval", "history": [], "events": [], "cost_usd": 0.0})
                dt = time.perf_counter() - t
                verdicts = [e["verdict"] for e in res["events"] if e["type"] == "Validation"]
                if res.get("validation_failed"):
                    result = "검증 실패(답변 미제공)"
                else:
                    wrong = bool(verify_answer(res["final"], res["collected"]))
                    result = "⚠️ 틀린 답변이 그대로 최종 응답" if wrong else "근거와 일치하는 답변"
                out.append(f"| {mode} | {vmode} | {res['validation_attempts']} ({' → '.join(verdicts)}) | {result} | {dt:.2f}s |")
    finally:
        await mcp.stop(); store.close()
    return "\n".join(out)


if __name__ == "__main__":
    parts = [offline()]
    if "--e2e" in sys.argv:
        parts.append(asyncio.run(e2e()))
    text = "\n\n".join(parts)
    print(text)
    (Path(__file__).parent / "results.md").write_text(text + "\n")

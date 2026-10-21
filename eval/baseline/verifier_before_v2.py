# 2차 검증 개선 직전의 verifier.py 스냅샷(비교 기준선 재현용). 앱에서 import하지 않는다.
"""근거 기반 답변 검증 — 작성된 답변을 수집된 모니터링 자료와 대조한다.

기존 validate_node는 '30자 이상 + "1)" 포함'만 보고 합격시켰다. 여기서는 답변에 적힌
시스템명과 CPU/메모리 사용률을 collected(실제로 수집된 모니터링 결과)와 직접 비교한다.
범위는 일부러 좁다: 자료와 곧바로 대조할 수 있는 항목(시스템명, 사용률 %)만 본다.
원인 설명이 사실인지까지는 판정하지 않는다.

순수 함수만 둔다 — LLM·네트워크 없이 단위 테스트와 평가셋에서 그대로 재사용한다.
"""
import re

# 수집값은 호출마다 jitter가 붙는 소수 첫째 자리 값이다. 모델이 반올림해 인용해도
# (78.3 → 78) 잘못으로 보지 않도록 허용 오차를 둔다.
TOLERANCE = 0.5

_SYSTEM_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*-(?:service|\d+)")
_METRICS = {
    "CPU": re.compile(r"CPU[^\d\n]{0,10}?(\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
    "메모리": re.compile(r"(?:메모리|memory)[^\d\n]{0,10}?(\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
}
_METRIC_FIELD = {"CPU": "cpu_percent", "메모리": "memory_percent"}


def _monitoring(collected: list[dict]) -> dict[str, dict]:
    return {c["data"]["system_name"]: c["data"]
            for c in collected if c.get("source") == "monitoring"}


def _system_mentions(draft: str, evidence: dict[str, dict]) -> list[tuple[int, str]]:
    """답변 속 시스템명 위치. 'payments-service-3'처럼 수집된 시스템 이름에 접미사가
    붙은 인스턴스 표기는 그 시스템으로 본다."""
    found = []
    for m in _SYSTEM_RE.finditer(draft):
        token = m.group(0)
        owner = next((s for s in evidence if token == s or token.startswith(s + "-")), token)
        found.append((m.start(), owner))
    return found


def _owner_of(pos: int, mentions: list[tuple[int, str]]) -> str | None:
    """수치가 가리키는 시스템 = 바로 앞에 나온 시스템명(없으면 바로 뒤에 나온 것)."""
    before = [name for p, name in mentions if p < pos]
    if before:
        return before[-1]
    after = [name for p, name in mentions if p > pos]
    return after[0] if after else None


def verify_answer(draft: str, collected: list[dict]) -> list[dict]:
    """불일치 목록을 반환한다. 비어 있으면 근거와 일치하는 답변이다.

    각 항목: {"code": 유형, "message": 작성 담당에게 줄 구체적 피드백}.
    """
    issues: list[dict] = []
    if len(draft) < 30 or "1)" not in draft:   # 기존 형식 요건은 유지
        issues.append({"code": "format", "message":
                       f"응답 형식이 맞지 않습니다({len(draft)}자). 최소 30자로 "
                       f"1) 2) 3) 번호 절차를 포함해 작성하세요."})

    evidence = _monitoring(collected)
    if not evidence:
        return issues + [{"code": "no_evidence", "message": "모니터링 자료가 없어 수치 대조를 수행할 수 없습니다."}]
    mentions = _system_mentions(draft, evidence)

    for name in dict.fromkeys(n for _, n in mentions):
        if name not in evidence:
            issues.append({"code": "unknown_system", "message":
                           f"'{name}'은(는) 수집된 자료에 없는 시스템입니다. 수집된 시스템: "
                           f"{', '.join(evidence)}. 이 시스템 언급을 제거하세요."})
    if not any(n in evidence for _, n in mentions):
        issues.append({"code": "no_system", "message":
                       f"답변에 수집된 시스템명이 없습니다. {', '.join(evidence)} 중 "
                       f"조사한 시스템을 이름으로 명시하세요."})

    all_values = {f: {round(d[f], 1) for d in evidence.values()} for f in _METRIC_FIELD.values()}
    for label, pattern in _METRICS.items():
        field = _METRIC_FIELD[label]
        for m in pattern.finditer(draft):
            claimed = float(m.group(1))
            owner = _owner_of(m.start(), mentions)
            if owner in evidence:
                actual = evidence[owner][field]
                if abs(claimed - actual) > TOLERANCE:
                    others = [s for s, d in evidence.items()
                              if s != owner and abs(claimed - d[field]) <= TOLERANCE]
                    hint = f" (이 값은 {', '.join(others)}의 수치입니다)" if others else ""
                    issues.append({"code": f"{field}_mismatch", "message":
                                   f"{owner}의 {label} 사용률은 수집값 {actual}%인데 답변에는 "
                                   f"{claimed:g}%로 적혀 있습니다{hint}. 수집된 값을 그대로 인용하세요."})
            elif not any(abs(claimed - v) <= TOLERANCE for v in all_values[field]):
                issues.append({"code": f"{field}_unsupported", "message":
                               f"{label} {claimed:g}%는 수집된 어떤 시스템의 값과도 일치하지 않습니다. "
                               f"수집값: " + ", ".join(f"{s} {d[field]}%" for s, d in evidence.items())})
    return issues


def evidence_summary(collected: list[dict]) -> list[str]:
    """검증 실패 시 사용자에게 보여줄, 수집 자료에서 직접 확인 가능한 사실 목록."""
    lines = []
    for name, d in _monitoring(collected).items():
        alerts = f", 알림: {'; '.join(d['alerts'])}" if d.get("alerts") else ""
        lines.append(f"{name}: 상태={d['status']}, CPU {d['cpu_percent']}%, "
                     f"메모리 {d['memory_percent']}%{alerts}")
    return lines


def verification_report(draft: str, collected: list[dict], issues: list[dict]) -> dict:
    """Recognized claims only; missing extraction must never imply full verification."""
    evidence = _monitoring(collected)
    mentions = _system_mentions(draft, evidence)
    rows = []
    for label, pattern in _METRICS.items():
        field = _METRIC_FIELD[label]
        for match in pattern.finditer(draft):
            owner = _owner_of(match.start(), mentions)
            claimed = float(match.group(1))
            actual = evidence.get(owner, {}).get(field)
            rows.append({"system": owner or "연결 불명", "metric": label,
                         "collected": actual, "claimed": claimed,
                         "verdict": "대조 불가" if actual is None else
                         ("일치" if abs(actual - claimed) <= TOLERANCE else "불일치")})
    return {"status": "자료 부족 · 검증 불가" if not evidence else
            ("검증 반려" if issues else "검사 통과"),
            "rows": rows, "issues": [i["message"] for i in issues],
            "scope": "정해진 표현에서 추출한 시스템명·CPU·메모리 수치만 대조합니다. 원인 설명·상태·권장 조치의 진실성은 검증하지 않습니다.",
            "coverage": "추출한 수치만 표시하며 누락 가능성이 있습니다." if rows else
                        "대조한 수치가 없습니다. 수치 검증 완료를 뜻하지 않습니다."}

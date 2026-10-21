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

_SYS = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*-(?:service|\d+)"
_SYSTEM_RE = re.compile(_SYS)
# 지표 이름(동의어 포함). 표현이 늘면 여기에 추가한다.
_WORD = {
    "CPU": r"(?:CPU|프로세서|중앙\s*처리\s*장치)",
    "메모리": r"(?:메모리|memory|RAM)",
}
_NUM = r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트|percent)"
_MORE = re.compile(rf"\s*(?:[,，、]|와|과|및|그리고)\s*{_NUM}")
_THRESH_WORDS = re.compile(r"임계|기준|threshold|한계|목표|SLA", re.IGNORECASE)
# 조건문 수치만 제외한다: 'CPU 90% 이상 지속 시', 'CPU 90%를 넘으면'. '99% 이상 지속되고 있습니다',
# '99%를 넘었습니다'처럼 현재 상태를 말하는 문장은 측정값 주장이므로 그대로 대조한다.
_THRESH_SUFFIX = re.compile(r"^\s*(?:이상|초과|이하|미만)\s*(?:지속\s*시|이면|일\s*때|인\s*경우)"
                            r"|^\s*(?:를|을)?\s*(?:넘으면|넘기면|넘는\s*경우|넘을\s*때|넘고\s*지속(?:되면|될\s*때|시)|초과하면)")
_NEGATED = re.compile(r"^\s*(?:가|이)?\s*아니")
_AFTER_NEG = re.compile(rf"^\s*(?:가|이)?\s*아니(?:라|고|며)\s*[^\d\n]{{0,6}}?{_NUM}")
_METRIC_FIELD = {"CPU": "cpu_percent", "메모리": "memory_percent"}
_FORWARD = {l: re.compile(rf"{w}[^\d\n]{{0,12}}?{_NUM}", re.IGNORECASE) for l, w in _WORD.items()}
_BACKWARD = {l: re.compile(rf"{_NUM}\s*(?:의|인|짜리)?\s*{w}", re.IGNORECASE) for l, w in _WORD.items()}
# 영어 'CPU usage of payments-service is 99%' — 시스템명이 지표 이름과 수치 사이에 끼는 형태
_OF_SYS = {l: re.compile(rf"{w}\s*(?:usage|utilization|load)?\s*(?:of|for|on)\s+({_SYS})[^\d\n]{{0,12}}?{_NUM}",
                         re.IGNORECASE) for l, w in _WORD.items()}


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


def _blank_tables(draft: str) -> tuple[str, list[dict]]:
    """마크다운 표를 열 단위로 읽어 (시스템, 지표, 값) 주장으로 바꾸고, 본문 스캔에서는 가린다."""
    claims, scan, offset = [], list(draft), 0
    lines = draft.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        start = offset
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|?\s*$", lines[i + 1]):
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            cols = {}
            for idx, h in enumerate(headers):
                for label, w in _WORD.items():
                    if re.search(w, h, re.IGNORECASE):
                        cols[idx] = label
            block_end, j, pos = i + 2, i + 2, offset + len(line) + 1 + len(lines[i + 1]) + 1
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                sm = _SYSTEM_RE.search(cells[0]) if cells else None
                for idx, label in cols.items():
                    if idx < len(cells) and sm:
                        nm = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트|percent)?", cells[idx])
                        if nm:
                            claims.append({"label": label, "claimed": float(nm.group(1)), "pos": pos,
                                           "owner_token": sm.group(0), "ignored": None})
                pos += len(lines[j]) + 1
                j += 1
            end = offset
            for k in range(i, j):
                end += len(lines[k]) + 1
            for q in range(start, min(end, len(scan))):
                if scan[q] != "\n":
                    scan[q] = " "
            offset, i = end, j
            continue
        offset += len(line) + 1
        i += 1
    return "".join(scan), claims


def _extract_claims(draft: str, mentions: list[tuple[int, str]], evidence: dict) -> list[dict]:
    """답변에서 CPU·메모리 사용률 주장을 모은다. 임계치·부정 표현은 ignored로 표시해 제외한다."""
    scan, claims = _blank_tables(draft)

    def own(token):
        return next((s for s in evidence if token == s or token.startswith(s + "-")), token)

    for c in claims:
        c["owner"] = own(c.pop("owner_token"))
    seen = {c["pos"] for c in claims}

    for label in _WORD:
        for m in _OF_SYS[label].finditer(scan):
            pos = m.start(2)
            if pos not in seen:
                seen.add(pos)
                claims.append({"label": label, "claimed": float(m.group(2)), "pos": pos,
                               "owner": own(m.group(1)), "ignored": None})
        for m in _FORWARD[label].finditer(scan):
            pos = m.start(1)
            if pos in seen:
                continue
            seen.add(pos)
            gap = scan[m.start():pos]
            nums = [(pos, float(m.group(1)), m.end())]
            if "각각" in gap:   # '각각 91.4%, 34.5%' — 앞에 나온 시스템을 순서대로 대응
                end = m.end()
                while (mm := _MORE.match(scan, end)):
                    nums.append((mm.start(1), float(mm.group(1)), mm.end())); end = mm.end()
            before = []
            for p, name in mentions:
                if p < m.start():
                    before = [x for x in before if x != name] + [name]
            owners = before[-len(nums):] if "각각" in gap else None
            for n, (p, val, e) in enumerate(nums):
                ignored = None
                if _THRESH_WORDS.search(gap) and n == 0:
                    ignored = "threshold"
                elif _THRESH_SUFFIX.match(scan[e:e + 24]):
                    ignored = "threshold"
                elif _NEGATED.match(scan[e:e + 12]):
                    ignored = "negated"
                if owners is not None:
                    k = len(nums) - len(owners)   # 시스템이 숫자보다 적으면 앞쪽 숫자는 연결 불명
                    owner = owners[n - k] if n >= k else None
                else:
                    owner = _owner_of(p, mentions)
                claims.append({"label": label, "claimed": val, "pos": p, "owner": owner, "ignored": ignored})
                if ignored == "negated" and (am := _AFTER_NEG.match(scan[e:e + 40])):
                    # '91.4%가 아니라 99%입니다' — 부정된 수치는 제외하되 뒤의 긍정 주장은 대조한다.
                    claims.append({"label": label, "claimed": float(am.group(1)), "pos": e + am.start(1),
                                   "owner": owner, "ignored": None})
        for m in _BACKWARD[label].finditer(scan):
            pos = m.start(1)
            if pos in seen:
                continue
            seen.add(pos)
            e = m.end(1) + 0
            tail = scan[m.end():m.end() + 12]
            claims.append({"label": label, "claimed": float(m.group(1)), "pos": pos,
                           "owner": _owner_of(pos, mentions),
                           "ignored": "negated" if _NEGATED.match(tail) else None})
    return sorted(claims, key=lambda c: c["pos"])


def verify_answer(draft: str, collected: list[dict], unavailable: list[str] | None = None) -> list[dict]:
    """불일치 목록을 반환한다. 비어 있으면 근거와 일치하는 답변이다.

    각 항목: {"code": 유형, "message": 작성 담당에게 줄 구체적 피드백}.
    unavailable: 조사했지만 자료를 얻지 못한 시스템(목록에 없음·조회 실패). 답변이 '조회하지 못했다'고
    밝히는 것은 정직한 서술이므로 허용하지만, 그 시스템의 수치를 주장하면 근거 없는 수치로 반려한다.
    """
    unavailable = set(unavailable or [])
    issues: list[dict] = []
    if len(draft) < 30 or "1)" not in draft:   # 기존 형식 요건은 유지
        issues.append({"code": "format", "message":
                       f"응답 형식이 맞지 않습니다({len(draft)}자). 최소 30자로 "
                       f"1) 2) 3) 번호 절차를 포함해 작성하세요."})

    evidence = _monitoring(collected)
    if not evidence:
        return issues + [{"code": "no_evidence", "message": "모니터링 자료가 없어 수치 대조를 수행할 수 없습니다."}]
    mentions = _system_mentions(draft, evidence)
    claims = [c for c in _extract_claims(draft, mentions, evidence) if not c["ignored"]]

    for name in dict.fromkeys(n for _, n in mentions):
        if name not in evidence and name not in unavailable:
            issues.append({"code": "unknown_system", "message":
                           f"'{name}'은(는) 수집된 자료에 없는 시스템입니다. 수집된 시스템: "
                           f"{', '.join(evidence)}. 이 시스템 언급을 제거하세요."})
    # 수치 주장이 있는데 어느 수집 시스템 얘기인지 알 수 없을 때만 시스템명을 요구한다.
    # 수치를 인용하지 않는 일반 서술에는 시스템명을 강제하지 않는다(불필요한 재작성 방지).
    if claims and not any(n in evidence for _, n in mentions):
        issues.append({"code": "no_system", "message":
                       f"수치를 인용했지만 수집된 시스템명이 없습니다. {', '.join(evidence)} 중 "
                       f"조사한 시스템을 이름으로 명시하세요."})

    for c in claims:
        label, claimed, owner = c["label"], c["claimed"], c["owner"]
        field = _METRIC_FIELD[label]
        if owner in evidence:
            actual = evidence[owner][field]
            if abs(claimed - actual) > TOLERANCE:
                others = [s for s, d in evidence.items()
                          if s != owner and abs(claimed - d[field]) <= TOLERANCE]
                hint = f" (이 값은 {', '.join(others)}의 수치입니다)" if others else ""
                issues.append({"code": f"{field}_mismatch", "message":
                               f"{owner}의 {label} 사용률은 수집값 {actual}%인데 답변에는 "
                               f"{claimed:g}%로 적혀 있습니다{hint}. 수집된 값을 그대로 인용하세요."})
        else:
            # 숫자가 다른 시스템과 같아도 해당 시스템의 근거를 대신할 수 없다.
            subject = f"'{owner}'의" if owner else "시스템 연결이 불명확한"
            issues.append({"code": f"{field}_unsupported", "message":
                           f"{subject} {label} {claimed:g}%를 뒷받침하는 수집 자료가 없습니다. "
                           "미조회 시스템의 측정값은 제시하지 말고 조회 불가로 안내하세요. "
                           "수치의 시스템 연결이 불명확하면 수집된 시스템명을 명시하세요."})
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
    rows, ignored = [], []
    for c in _extract_claims(draft, mentions, evidence):
        label, claimed, owner = c["label"], c["claimed"], c["owner"]
        if c["ignored"]:
            ignored.append(f"{label} {claimed:g}% ({'임계치·조건문' if c['ignored'] == 'threshold' else '부정 표현'}으로 해석해 제외)")
            continue
        actual = evidence.get(owner, {}).get(_METRIC_FIELD[label])
        rows.append({"system": owner or "연결 불명", "metric": label,
                     "collected": actual, "claimed": claimed,
                     "verdict": "대조 불가" if actual is None else
                     ("일치" if abs(actual - claimed) <= TOLERANCE else "불일치")})
    coverage = ("추출한 수치만 표시하며 누락 가능성이 있습니다." if rows else
                "대조한 수치가 없습니다. 수치 검증 완료를 뜻하지 않습니다.")
    if ignored:
        coverage += f" 임계치·조건문·부정 표현으로 해석한 수치 {len(ignored)}개는 대조에서 제외했습니다."
    return {"status": "자료 부족 · 검증 불가" if not evidence else
            ("검증 반려" if issues else "검사 통과"),
            "rows": rows, "issues": [i["message"] for i in issues], "ignored": ignored,
            "scope": "정해진 표현에서 추출한 시스템명·CPU·메모리 수치만 대조합니다. 원인 설명·상태·권장 조치의 진실성은 검증하지 않습니다.",
            "coverage": coverage}

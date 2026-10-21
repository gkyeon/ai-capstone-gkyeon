"""대상 시스템 해석 — 질문에서 조사할 시스템을 코드가 결정하고, 폴백을 숨기지 않는다.

기존에는 graph·ollama_llm·openai_llm이 각자 KNOWN_SYSTEMS와 "못 찾으면 auth-service" 폴백을 갖고 있었다.
그래서 목록에 없는 시스템(예: billing-service)을 물으면 계획 정규화가 이를 조용히 auth-service로
바꿨고, 사용자가 묻지 않은 시스템에 대한 '근거 있는 답변'이 만들어졌다.

여기서는 한 곳에서 다음을 구분한다.
- known    : monitoring.json에 있는 시스템 (대소문자·밑줄 표기 차이는 무시, 숫자 접미사 인스턴스 표기는 소속 시스템)
- unknown  : 시스템 이름 꼴인데 목록에 없는 것 → 바꾸지 않고 그대로 조사 대상에 남긴다(조회 실패로 드러남)
- defaulted: 시스템명이 전혀 없을 때만 기본값을 쓰되, 기본값을 썼다는 사실을 플래그로 남긴다
"""
import json
import re
from pathlib import Path

DEFAULT_TARGET = "auth-service"
# 한국어 조사와 붙어 있어도 인식하되 영문 식별자 내부에서는 잘라 매칭하지 않는다.
_TOKEN_RE = re.compile(r"(?<![a-z0-9-])[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?![a-z0-9-])")
_SYSTEM_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*-(?:service|\d+)")


def load_known_systems() -> set[str]:
    """data/monitoring.json의 최상위 키가 조사 가능한 시스템 목록이다. 읽지 못하면 최소 목록으로 대체한다."""
    data_file = Path(__file__).resolve().parents[1] / "data" / "monitoring.json"
    try:
        return set(json.loads(data_file.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {"web-01", "auth-service"}


KNOWN_SYSTEMS = load_known_systems()


def resolve_targets(query: str, known: set[str] | None = None) -> dict:
    known = KNOWN_SYSTEMS if known is None else known
    text = query.lower().replace("_", "-")
    known_found: list[str] = []
    unknown: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        token = m.group(0)
        # 정확한 식별자를 우선한다. 소속 시스템으로 합치는 접미사는 숫자 인스턴스만 허용.
        owner = token if token in known else next(
            (k for k in sorted(known, key=lambda x: (-len(x), x))
             if token.startswith(k + "-") and token[len(k) + 1:].isdigit()), None)
        if owner is not None:
            if owner not in known_found:
                known_found.append(owner)
        elif (_SYSTEM_RE.fullmatch(token) or "service" in token.split("-")) and token not in unknown:
            unknown.append(token)

    defaulted = not known_found and not unknown
    targets = known_found + unknown if not defaulted else [DEFAULT_TARGET]
    return {"known": known_found, "unknown": unknown, "defaulted": defaulted,
            "targets": targets, "primary": targets[0]}

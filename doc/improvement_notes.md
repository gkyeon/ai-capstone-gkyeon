# 개인과제: 근거 기반 답변 검증 및 실패 처리 개선

## 문제 (개선 전, `agent/graph.py`의 `_legacy_validate`)
- 합격 조건이 `len(draft) >= 30 and "1)" in draft` 뿐이라, 수집 자료와 다른 CPU 수치·다른 시스템 수치도 통과.
- 3회 불합격 시 `ok = True`로 바꿔 강제 합격 → 틀린 답변이 최종 응답이 됨.
- 피드백이 "짧습니다"로 고정 → 무엇이 틀렸는지 작성 쪽에 전달 안 됨.

## 변경
| 파일 | 내용 |
|---|---|
| `agent/verifier.py` (신규) | 답변의 시스템명·CPU·메모리 %를 수집 자료와 대조. 불일치 사유를 문장으로 반환. 허용 오차 0.5%p |
| `agent/graph.py` | `validate_node`가 verifier 사용. 3회 실패 시 `validation_failed` → 새 노드 `finalize_failed`(답변 미제공 + 사유 + 수집값 안내) |
| `agent/deps.py`, `server.py` | `VALIDATOR_MODE=legacy|grounded`(기본 grounded). metadata에 `validation_failed` 추가 |
| `agent/fake_llm.py` | `FAKE_DRAFT_MODE`(wrong_cpu_once / cross_system / always_wrong)로 틀린 답변 재현 |
| `web_chat.html` | 검증 반려 사유·검증 실패 상태 표시 |
| `eval/eval_validator.py` | 평가셋 17개 + 그래프 전체 실행 비교 → `eval/results.md` |

## 재현·비교
```bash
.venv/bin/python eval/eval_validator.py --e2e          # 전후 비교표 생성
FAKE_DRAFT_MODE=always_wrong VALIDATOR_MODE=legacy .venv/bin/python server.py   # 개선 전 화면
FAKE_DRAFT_MODE=always_wrong .venv/bin/python server.py                         # 개선 후 화면
```

## 한계
- 시스템명·CPU·메모리 % 일치만 확인. 원인 설명(예: "커넥션 풀 때문")의 진실성은 판정 안 함.
- "CPU 임계치 80%"처럼 CPU 옆에 다른 수치를 인용하면 오탐(평가셋 G8).
- 수치가 어느 시스템 것인지는 '바로 앞 시스템명' 규칙으로 추정.

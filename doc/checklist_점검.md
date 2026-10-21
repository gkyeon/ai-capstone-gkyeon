# checklist.md 점검 결과 (2026-10-21, Claude)

원본 `checklist.md`는 수정하지 않았다. 판정 기준: ✅ 코드로 확인 / ⚠️ 일부만 충족·근거 약함 / ❌ 없음.
"제공 기반"은 과제 원본 zip에 이미 있던 구조라서, 발표에서 직접 구현했다고 말하면 안 된다. (프로젝트 경로: `all_total_vue_student/`)

## 1. 15개 요소

| # | 항목 | 판정 | 코드 근거 | 약한 부분·주의 |
|---|---|---|---|---|
| 1 | ADR | ✅ | `doc/ADR.md` ADR-01~09 | ADR-05~09는 제공 구조의 결정을 사후 정리한 것(원작자 의도 확인 아님). MCP 선택 이유는 따로 적지 않음 |
| 2 | FastAPI | ✅ 제공 기반 | `server.py` (lifespan, `/chat`, `/chat/stream`, `/health`) | 우리는 metadata 필드와 env 전환만 추가 |
| 3 | MCP Server | ✅ | `mcp_server.py` Tool·Resource·Prompt | **우리가 `search_incident_runbooks` 도구를 추가** |
| 4 | SSE 백엔드 | ✅ 제공 기반 | `server.py` `/chat/stream`, `text/event-stream` | |
| 5 | SSE 프런트 | ✅ 제공 기반 | `web_chat.html` `EventSource` (Vue 3) | 화면 디자인·검증표·검색 후보 표시는 우리가 변경 |
| 6 | Multi-agent Streaming | ⚠️ | 진행 단계 이벤트는 스트리밍됨 | **초안 토큰 스트리밍을 일부러 막음**(`server.py` AnswerToken `continue`, ADR-04). 답변 본문은 완료 후 한 번에 나온다. 원래도 ollama/openai 작성은 토큰 단위가 아니었다. 트레이드오프로 설명해야 함 |
| 7 | Query Routing | ✅ 제공 기반 | `graph.py` `route_node`, `_after_route` | |
| 8 | Dynamic Planning | ✅ 제공 기반 | `plan_node`(MCP Prompt+LLM 태스크), `replan_check_node`(gap task) | 우리는 `should_replan`/`is_sufficient` 분리만 수정 |
| 9 | Validator | ✅ **직접 구현** | `agent/verifier.py`, `validate_node`, `finalize_failed_node` | 한계: 한글 동의어·표 형태·부정문 오탐/누락 (agent.md C절) |
| 10/11 | Error Handling | ✅ | `retry.py` 재시도, `asyncio.wait_for` 타임아웃, `return_exceptions=True` 부분 실패 격리, 검증 실패 종료 | 매뉴얼/검색 호출은 재시도 없음(모니터링만 재시도) |
| 12 | Cost Optimization | ✅ | fast/quality 분리(제공)·이력 10개 제한(제공)·**`evidence_gate` 조기 종료(직접, ADR-14)**·재작성 감소 | 프롬프트 압축·요약 없음. 비용은 글자수 기반 추정. 조기 종료는 근거 0건일 때만 동작(단일 질문 실측: 36.6s→1.2~2.7s) |
| 13 | 동시 실행 | ✅ 제공 기반 | `research_node`의 `asyncio.gather` | 직렬 대비 시간 측정 기록이 보고서에 없음(`parallel_elapsed`는 metadata에 있음) |
| 14 | Stateless Session | ✅ 제공 기반 | `session_store.py` SQLite, `thread_id`로 이력 로드 | 프로세스 안에 사용자별 상태 없음. 단 MCP 클라이언트·그래프는 프로세스 싱글턴(사용자 상태 아님) |
| 15 | 모듈화 | ✅ | `agent/` 패키지(graph, verifier, retrieval, retry, deps, *_llm) | 우리가 `verifier.py`, `retrieval.py` 분리 추가 |
| - | Observability & Eval | ✅(기록 확인) | 추적 1회 실행, LangSmith 59개 run 트리 확인(서브에이전트·evidence_gate·validate 포함) | 비교 평가(데이터셋·평가자) 미수행, 평가는 자체 스크립트. 화면 캡처는 로그인 필요라 미포함 |
| - | Multi-agent 통합 | ✅(얕은 형태) | `agent/subagents.py` 컴파일된 서브그래프 2개 + supervisor `research_node`, ADR-10, `eval/test_subagents.py` | 작업자는 도구 호출형이며 LLM 판단·상호 협상 없음. PDF 예시의 3분할 중 로그 분석은 없음. 성능 이득 없음(오버헤드 약 0.01초) |

## 2. LangGraph 노드·엣지 (`graph.py:401-428`)

| 항목 | 판정 | 비고 |
|---|---|---|
| route / `_after_route` | ✅ | `_after_route`는 노드가 아니라 분기 함수 |
| plan, gate, research, replan_check, analysis, write, validate, finalize | ✅ | 전부 `add_node`에 존재 |
| 추가: finalize_failed | ✅ 직접 추가 | validate 실패 한도 도달 시 종료 경로 |
| 엣지 흐름 | ✅ | route→(chat_answer\|plan)→gate→research→replan_check→(research\|analysis)→write→validate→(write\|finalize\|finalize_failed) |

## 3. 평가서 기준별 현재 위치

| 영역 | 배점 | 상태 | 가장 큰 공백 |
|---|---|---|---|
| 기능 구현 완성도 | 30 | 테스트 통과, 로컬 서버+임베딩+모의 모델로 UI 실행 | **확장 후 실제 생성 모델 실행 기록 없음** |
| 기술 요소 반영도 | 30 | 위 표 | 6번 스트리밍 결정 설명, LangSmith 실제 기록, 멀티에이전트 표현 |
| 한계·트레이드오프 | 20 | 한계 자료는 충분(검증 오탐/누락, 검색 12/14, 초안 비공개 지연) | 12번 비용 최적화의 한계 설명 |
| 발표·보고서 | 20 | 제출물이 확장 전 버전 | **최신화 필요** |
| [보너스] 수치 비교 | +10 | **미획득 상태** | 12번 비용 최적화 또는 모듈화 전후 지연·비용 수치가 없음. 13번 병렬 vs 직렬 지연이 가장 쉬움 |

## 4. 점수를 올리려면 (우선순위, 기능 추가 최소)

1. **제출물 최신화** (발표·보고서 20점 + 완성도 근거)
2. **확장 후 Ollama 실행 기록**: 이 실행의 metadata(`cost_usd`, `parallel_elapsed`, `retry_count`)를 같이 저장하면 아래 3번의 재료가 됨
3. **보너스 수치 1~2개**: ① 병렬 vs 직렬 조사 시간(13번) ② fast/quality 분리 vs 전부 quality 모델 시 비용 추정(12번, 단가는 가정값임을 명시). 둘 다 제공 기반 기능의 측정이라 "직접 구현"이 아니라 "측정"으로 말해야 함
4. ~~ADR 보강~~ 완료(ADR-05~09 추가)
5. **6번 스트리밍**: "초안 비공개를 위해 토큰 스트리밍을 포기" 트레이드오프로 발표에 포함
6. LangSmith: `.env`에 본인 키가 있다면 실제 추적 화면 1장 캡처 가능. 없다면 "코드에 @traceable 적용, 이번 실험에서는 추적 비활성화"로 정직하게 표기

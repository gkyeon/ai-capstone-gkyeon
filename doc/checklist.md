# AI 미니 프로젝트: 아키텍처 기반 상세 평가 체크리스트 및 평가서

본 체크리스트는 프로젝트의 요구 아키텍처 및 데이터 흐름 다이어그램(`image_a89a5e.png`)에 명시된 모든 모듈과 노드가 정상적으로 구현되었는지 확인하기 위한 통합 평가 기준입니다.

## 1. 아키텍처 및 핵심 모듈 구현 체크리스트 (15개 필수 요소 + 추가 확장)

다이어그램 상단 목차에 명시된 핵심 기술 요소들의 적용 여부를 점검합니다.

* [x] **1. ADR (Architecture Decision Record)**: 아키텍처 결정 사항이 명확히 문서화되어 있는가?  
  → 근거: `doc/ADR.md` ADR-01~09 (ADR-05~09는 제공 구조의 결정을 사후 정리)
* [x] **2. FastAPI 통합**: Backend 서버가 FastAPI 기반으로 정상 연동 및 구성되었는가?  
  → 근거: `server.py` (제공 기반)
* [x] **3. MCP Server**: 외부 도구/리소스 연동을 위한 MCP 서버가 정상적으로 연결 및 동작하는가?  
  → 근거: `mcp_server.py` Tool·Resource·Prompt, 검색 도구는 직접 추가
* [x] **4. SSE - BACKEND**: 백엔드에서 Server-Sent Events(SSE) 스트리밍 구현이 되어있는가?  
  → 근거: `/chat/stream` (제공 기반)
* [x] **5. SSE - FRONTEND**: 프론트엔드(Client/React)에서 SSE 스트리밍 데이터를 정상적으로 수신 및 렌더링하는가?  
  → 근거: `web_chat.html` EventSource, Vue (제공 기반)
* [ ] **6. MULTI-AGENT Streaming**: 멀티 에이전트 환경에서 생성되는 응답이 끊김 없이 스트리밍되는가?  
  → ⚠️ 진행 이벤트는 스트리밍하나 초안 토큰은 검증 전 노출 방지를 위해 의도적으로 차단(ADR-04, 트레이드오프)
* [x] **7. Query Routing**: 사용자의 질의 의도에 맞게 적절한 경로(일반 챗 vs 분석 로직)로 라우팅되는가?  
  → 근거: `route_node` (제공 기반)
* [x] **8. Dynamic Planning**: 동적으로 태스크(Task)를 정의하고 계획을 수립하는 로직이 있는가?  
  → 근거: `plan_node`·`replan_check_node` (제공 기반)
* [x] **9. Validator**: 최종 응답 전, 결과가 충분한지 검증(Validate)하는 모듈이 동작하는가?  
  → 근거: `agent/verifier.py` 직접 구현
* [x] **10/11. Error Handling**: 시스템 전반 및 에이전트 실행 과정의 예외 처리(Error Handling)가 꼼꼼하게 되어 있는가?  
  → 근거: 재시도·타임아웃·부분 실패 격리·검증 실패 종료·대상 시스템 폴백을 숨기지 않고 안내(`targets.py`, ADR-11)
* [x] **12. Cost Optimization**: 토큰 사용량 최적화, 프롬프트 압축 등 비용 최적화(Cost Optimization) 기법이 적용되었는가?  
  → 근거: ① fast/quality 모델 분리(제공, 추정 약 59% 절감) ② 이력 10개 제한(제공) ③ **근거 0건이면 작성 모델 호출 생략**(`evidence_gate`, ADR-14: billing-service 36.6s→1.2~2.7s, 작성 호출 1→0회) ④ 재작성 감소(평균 2.0→1.0회, 정확도 향상 아님). 한계: 프롬프트 압축·요약은 없고 비용은 글자수 기반 추정
* [x] **13. 동시 실행 (Concurrent Execution)**: 병렬 처리가 필요한 작업들이 동시 실행 구조로 구현되었는가?  
  → 근거: `asyncio.gather` (제공 기반), 병렬 0.36~0.37s vs 직렬 1.07~1.08s 측정
* [x] **14. Stateless Session**: 서버 상태를 유지하지 않는 무상태(Stateless) 기반의 세션 관리가 이루어지는가?  
  → 근거: SQLite `thread_id` 세션 (제공 기반)
* [x] **15. Modularization (모듈화)**: 코드가 단일 구조가 아닌, 목적에 맞게 분리 및 모듈화되어 있는가?  
  → 근거: `agent/` 패키지 — `state.py`, `nodes/` 6개 모듈(graph.py 425줄→58줄), `targets.py`, `subagents.py`, `verifier.py`, `retrieval.py` (ADR-13)
* [x] **Observability & Eval**: LangSmith 등을 활용하여 에이전트의 동작 과정을 모니터링하고 평가할 수 있는가?  
  → 근거: 추적을 켜고 1회 실행해 LangSmith에 59개 run 트리 기록 확인(서브에이전트·evidence_gate·validate 포함, `eval/langsmith-trace-20261021.txt`). 한계: LangSmith 기반 **비교 평가는 미수행**, 평가는 자체 스크립트(`eval/`), 화면 캡처는 로그인이 필요해 미포함
* [x] **Multi-agent 통합 개발**: 복수의 에이전트(Supervisor, Worker 등)가 유기적으로 협력하는 구조인가?  
  → 근거: supervisor(`research_node`) + 서브에이전트 2개(`agent/subagents.py` monitoring_agent·runbook_agent, ADR-10). 단 작업자는 LLM이 판단하지 않는 도구 호출형이고 서로 협상하지 않음

## 2. LangGraph 워크플로우(Node & Edge) 체크리스트

다이어그램 하단에 명시된 LangGraph 기반의 절차적 흐름이 정확히 구현되었는지 점검합니다.

### 라우팅 및 분기 로직
* [x] `route` 노드: 사용자 입력(결함에 관한 것인가?)을 판단하여 경로를 결정하는가?  
  → 근거: `agent/graph.py` `add_node`/엣지 확인
* [x] `_after_route` 노드: 라우팅 결과에 따라 일반 챗(`Chat_answer` -> `END`)으로 갈지, 분석 로직(`plan`)으로 갈지 정상 분기하는가?  
  → 근거: `agent/graph.py` `add_node`/엣지 확인

### 분석 및 실행 로직
* [x] `plan` 노드: MCP에 Prompt 문의 및 LLM Task 정의 요청을 정상적으로 수행하는가?  
  → 근거: `agent/graph.py` `add_node`/엣지 확인
* [x] `gate` 노드: Analysis 설정이 맞는지 검문/제어하는 역할을 수행하는가?  
  → 근거: `agent/graph.py` `add_node`/엣지 확인
* [x] `research` 노드: 모니터링 정보(Tool) 및 Runbook 리소스 정보 요청을 수행하는가?  
  → 근거: `agent/graph.py` `add_node`/엣지 확인
* [x] `replan_check` 노드: 수집된 Runbook 정보 등이 충분한지 확인하고 재계획(Replan) 여부를 판단하는가?  
  → 근거: `agent/graph.py` `add_node`/엣지 확인
* [x] `Analysis` 노드: 수집된 데이터를 바탕으로 로그/메트릭 패턴 분석을 수행하는가?  
  → 근거: `agent/graph.py` `add_node`/엣지 확인
* [x] `write` 노드: 분석 결과를 바탕으로 최종 답변의 초안을 작성하는가?  
  → 근거: `agent/graph.py` `add_node`/엣지 확인
* [x] `validate` 노드: 작성된 결과가 충분한지 검증하는가?  
  → 근거: `agent/graph.py` `add_node`/엣지 확인
* [x] `finalize` 노드: 최종적으로 사용자에게 전달할 응답을 확정하고 마무리하는가?  
  → 근거: `agent/graph.py` `add_node`/엣지 확인

## 3. 업데이트된 종합 평가서 (아키텍처 항목 반영)

기존 PDF 가이드의 배점 기준에 다이어그램 세부 항목을 통합한 최종 평가서입니다.

| 평가 항목 | 세부 평가 기준 (다이어그램 항목 포함) | 배점 | 획득 점수 |
| :--- | :--- | :---: | :---: |
| **기능 구현 완성도** | - 선택한 과제가 정상 동작하는가?<br>- Client(React/Vue) ↔ Backend(FastAPI) ↔ Agent 통신이 원활한가?<br>- Graph의 전체 Node 흐름(`route`부터 `finalize`까지)이 중단 없이 이어지는가? | **30** | / 30 |
| **기술 요소 반영도** | - 15대 아키텍처 필수 항목(SSE, 동시 실행, Stateless, 모듈화 등)이 코드에 잘 녹아있는가?<br>- Multi-Agent, MCP 연동, LangSmith 모니터링이 완벽히 결합되어 있는가? | **30** | / 30 |
| **한계 및 트레이드오프** | - 에러 핸들링(Error Handling), 비용 최적화(Cost Optimization) 과정에서 드러난 시스템적 한계나 포기해야 했던 이점을 명확히 설명할 수 있는가? | **20** | / 20 |
| **발표 및 보고서** | - 다이어그램과 본인의 실제 구현 내용을 비교하며, 문제 개선 포인트 → 실측 수치 → 향후 개선점을 발표하였는가? | **20** | / 20 |
| **[보너스] 수치 비교** | - 적용된 비용 최적화(12번), 모듈화 전후의 성능/비용 변화를 구체적인 데이터(지연시간 등)로 증명했는가? | **+10** | / 10 |
| **총합계** | | **100+10** | **/ 110** |

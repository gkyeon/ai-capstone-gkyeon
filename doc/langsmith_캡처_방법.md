# LangSmith 추적 캡처 방법 (직접 해야 하는 부분)

이 프로젝트의 노드(`route`·`plan`·`research`·서브에이전트 `monitoring_agent`/`runbook_agent`·`validate` 등)는 `@traceable`/컴파일된 서브그래프 이름으로 LangSmith에 계층 기록되도록 되어 있다. 다만 개인과제 폴더에는 `.env`(API 키)가 없어서 이번 실험은 모두 추적을 끄고 돌렸다. 평가 기준의 "LangSmith"를 근거 있게 말하려면 아래대로 1회 실행해 화면을 캡처한다. 키는 본인 계정의 값이며 이 저장소에 커밋하지 않는다(`.gitignore`에 `.env` 포함).

1. 수업 실습 폴더의 `.env`를 프로젝트로 복사한다(값은 열어 보지 않아도 된다).
   ```bash
   cp "$HOME/workspace/19 AI capstone/AI_Capstone_실습_20261019/wave14_base-langsmith/.env" \
      "$HOME/workspace/19 AI capstone/개인과제/all_total_vue_student/.env"
   ```
2. 실습 프로젝트와 기록이 섞이지 않게 프로젝트 이름을 덮어써서 서버를 띄운다(fake 모델이면 비용 없음).
   ```bash
   cd "$HOME/workspace/19 AI capstone/개인과제/all_total_vue_student"
   LLM_BACKEND=fake LANGCHAIN_TRACING_V2=true LANGCHAIN_PROJECT=capstone-personal .venv/bin/python server.py
   ```
3. 다른 터미널에서 질문 1개를 보낸다.
   ```bash
   curl -s localhost:8100/chat -X POST -H 'content-type: application/json' \
     -d '{"message":"auth-service 로그인 지연 원인 진단해줘","thread_id":"ls1"}' > /dev/null
   ```
4. https://smith.langchain.com 에 로그인해 프로젝트 `capstone-personal`의 최신 `chat_request` 실행을 열고, 노드 트리(route → plan → gate → research(→ monitoring_agent·runbook_agent) → … → validate → finalize)가 보이는 화면을 캡처한다.
5. 보고서·PPT에는 "추적 코드는 제공 기반이고, 이번 개선의 서브에이전트·검증 노드가 같은 트리에 기록됨을 확인"으로 쓰고, LangSmith 기반 비교 평가는 하지 않았다는 점은 그대로 둔다.

주의: 추적을 켜면 질문과 모델 응답이 LangSmith 서버로 전송된다. 위 질문은 가상 시스템에 대한 것이라 민감하지 않다.

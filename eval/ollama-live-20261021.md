# 확장 후 Ollama 실모델 실행 (2026-10-21, Claude)

- 작성 모델 qwen3:8b, 보조 qwen2.5:0.5b, 임베딩 qwen3-embedding:0.6b. 질문 4종 × 설정 2종 × 1회(총 8회). 원본: `ollama-live-20261021.json`, 스크립트: `run_live_ollama.py`
- before = `VALIDATOR_MODE=legacy` + `RETRIEVAL_MODE=legacy`, after = `grounded` + `semantic`. 코드는 확장 후 동일 버전.
- 표본이 작아 통계적 결론은 못 낸다. 각 설정 1회씩이라 LLM 무작위성이 섞여 있다.

| 질문 | before 시도·시간 | after 시도·시간 | after 반려 사유 | after 검색 선택(점수) |
|---|---|---|---|---|
| auth-service 로그인 지연 | 1 · 37.4s | 2 · 61.5s | no_system | high-latency (0.683) |
| payments-service CPU | 1 · 25.9s | 2 · 52.0s | cpu_percent_mismatch | cpu-spike (0.677) |
| cache-service 메모리 | 1 · 48.1s | 2 · 69.4s | no_system | memory-leak (0.727) |
| log-service 디스크 | 1 · 38.0s | 2 · 125.1s | no_system | disk-full (0.780) |
| 평균 | 1.0 · 37.4s | 2.0 · 77.0s | | |

관찰과 주의:
- after 4건 모두 첫 초안이 반려됐고 재작성 후 통과했다. 검증 실패 종료는 없었다.
- 반려 4건 중 3건은 no_system(시스템명 미표기), 1건은 실제 CPU 수치 불일치였다.
- before 답변의 수치가 수집값과 맞았는지는 수집값을 저장하지 않아 확인하지 못했다. "before 답변이 틀렸다"는 근거로 쓰지 않는다.
- after 첫 건의 `parallel_elapsed` 9.64s는 임베딩 모델 첫 로딩(콜드 스타트) 영향으로 보인다. 나머지는 0.36~0.42s.
- after payments 최종 답변이 알림 원문을 "CPU 95.2% (threshold 80%)"로 인용했다. 실제 알림 문구는 "CPU 91% (threshold 80%)"다. 수집된 CPU 값과는 같아서 검증을 통과했지만 알림 인용이 바뀐 것이므로, 검증기가 알림 문구 인용의 정확성까지는 보지 않는다는 한계의 실제 사례다.
- cost_usd는 토큰 수 추정 × 가정 단가라 실제 비용이 아니다.

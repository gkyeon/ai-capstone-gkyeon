"""확장 후(의미 검색·부분 실패·근거 검증) 실제 Ollama 작성 모델 소수 케이스 실행.

설정 2종(개선 전: legacy 검증+legacy 검색 / 개선 후: grounded 검증+semantic 검색)을 같은 질문으로 호출하고
요청·응답 전체(events, metadata, verification_report 포함)를 eval/ollama-live-<날짜>.json에 저장한다.
사용: .venv/bin/python eval/run_live_ollama.py [--r2]
"""
import json, os, subprocess, sys, time, urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = [
    "auth-service 로그인 응답이 느려요. 장애 원인 확인해주세요",
    "payments-service 결제 응답이 느려지고 CPU가 치솟았어요, 원인 확인해주세요",
    "cache-service 메모리 사용률이 계속 올라가고 있어요. 장애 진단해주세요",
    "log-service 디스크 공간이 부족하다는 알림이 왔어요. 장애 진단해주세요",
]
# 2차 실행(--r2)은 같은 4개 질문에 대상 시스템 해석을 보는 2개 질문을 더한다.
EXTRA_R2 = ["billing-service 응답이 느려요. 장애 진단해주세요",
            "로그인 응답이 느려요. 장애 원인 확인해주세요"]
CONFIGS = {
    "before": {"VALIDATOR_MODE": "legacy", "RETRIEVAL_MODE": "legacy"},
    "after": {"VALIDATOR_MODE": "grounded", "RETRIEVAL_MODE": "semantic"},
}


def run(name: str, cfg: dict, questions: list[str]) -> list[dict]:
    env = {**os.environ, "LLM_BACKEND": "ollama", "OLLAMA_FAST_MODEL": "qwen2.5:0.5b",
           "OLLAMA_QUALITY_MODEL": "qwen3:8b", "LANGCHAIN_TRACING_V2": "false",
           "LANGSMITH_TRACING": "false", "SUPERVISOR_VERSION": "v2", **cfg}
    srv = subprocess.Popen([str(ROOT / ".venv/bin/python"), "server.py"], cwd=ROOT, env=env,
                           stdout=open(f"/tmp/live_{name}.log", "w"), stderr=subprocess.STDOUT)
    rows = []
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen("http://127.0.0.1:8100/health", timeout=2); break
            except Exception:
                time.sleep(1)
        for q in questions:
            t = time.time()
            req = urllib.request.Request("http://127.0.0.1:8100/chat",
                                         json.dumps({"message": q, "thread_id": f"live-{name}-{time.time()}"}).encode(),
                                         {"content-type": "application/json"})
            row = {"config": name, "settings": cfg, "question": q}
            try:
                d = json.load(urllib.request.urlopen(req, timeout=600))
                row.update(seconds=round(time.time() - t, 1), response=d)
            except Exception as e:
                row.update(seconds=round(time.time() - t, 1), error=repr(e))
            rows.append(row)
            print(name, row["seconds"], "error" in row, flush=True)
    finally:
        srv.kill(); srv.wait()
    return rows


if __name__ == "__main__":
    r2 = "--r2" in sys.argv
    questions = QUESTIONS + (EXTRA_R2 if r2 else [])
    out = []
    for name, cfg in CONFIGS.items():
        out += run(name, cfg, questions)
    # 이전 실행 결과를 덮어쓰지 않도록 2차 실행은 -r2 파일에 저장한다.
    path = ROOT / "eval" / f"ollama-live-{date.today():%Y%m%d}{'-r2' if r2 else ''}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("saved", path)

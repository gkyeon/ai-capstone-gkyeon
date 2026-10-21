"""의미 검색(임베딩) 도입이 만든 비용·지연 측정 — '개선이 새로 만든 약점'을 수치로 확인한다.

측정: ① 임베딩 모델이 메모리에 없을 때(콜드) 첫 검색 ② 모델이 올라와 있을 때 인덱스 재구축(문서 6개)
③ 인덱스가 있을 때(웜) 검색 1회 ④ 기존 키워드 분류기와의 비교 ⑤ 모델 디스크 크기.
사용: .venv/bin/python eval/measure_embedding.py  → eval/embedding-cost-20261021.md
"""
import os, statistics, subprocess, sys, time
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.update(LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false")
from agent.retrieval import RunbookRetriever
from agent.graph import _classify_incident_type

QUERIES = ["로그인 요청은 성공하지만 응답 속도가 느립니다", "프로세서 사용률이 치솟고 처리량이 떨어졌어요",
           "로그 파일이 쌓여 파일을 더 저장할 수 없어요", "heap keeps growing after garbage collection",
           "데이터베이스에 접속할 수 없고 DB 프로세스가 죽었습니다"]
MODEL = os.environ.get("EMBEDDING_MODEL", "qwen3-embedding:0.6b")

def t(fn):
    s = time.perf_counter(); fn(); return time.perf_counter() - s

def main():
    subprocess.run(["ollama", "stop", MODEL], capture_output=True)          # 모델을 메모리에서 내려 콜드 상태로
    time.sleep(2)
    r = RunbookRetriever(ROOT / "data" / "runbooks")
    cold = t(lambda: r.search(QUERIES[0]))                                      # 모델 로드 + 인덱스 생성 + 질의
    warm = [t(lambda q=q: r.search(q)) for q in QUERIES * 4]                    # 인덱스·모델 모두 준비된 상태
    rebuild = []
    for _ in range(5):                                                           # 문서가 바뀌었을 때(지문 불일치) 재구축
        r._fingerprint = None
        rebuild.append(t(lambda: r.search(QUERIES[0])))
    legacy = statistics.mean(t(lambda q=q: _classify_incident_type([{"source": "monitoring", "data": {"status": "degraded", "alerts": [q]}}]))
                             for q in QUERIES * 50)
    size = next((l.split()[2:4] for l in subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout.splitlines()
                 if l.startswith(MODEL.split(":")[0])), ["?", "?"])
    q = sorted(warm)
    out = [f"# 임베딩 검색 도입 비용·지연 측정 ({date.today()})", "",
           f"모델 `{MODEL}`, 매뉴얼 6개, 로컬 Ollama. 단일 머신·소표본 측정이라 절대값보다 자릿수를 본다.", "",
           "| 항목 | 측정값 |", "|---|---|",
           f"| 콜드 첫 검색(모델 로드+인덱스 생성+질의) | {cold:.2f}s |",
           f"| 인덱스 재구축(모델 로드된 상태, 5회) | 평균 {statistics.mean(rebuild):.2f}s (최소 {min(rebuild):.2f}, 최대 {max(rebuild):.2f}) |",
           f"| 웜 검색 1회({len(warm)}회) | 평균 {statistics.mean(warm)*1000:.0f}ms, 중앙값 {statistics.median(warm)*1000:.0f}ms, 최대 {q[-1]*1000:.0f}ms |",
           f"| 기존 키워드 분류기 1회 | 평균 {legacy*1e6:.1f}µs |",
           f"| 모델 디스크 크기 | {' '.join(size)} |", "",
           "해석: 웜 상태의 검색은 에이전트 전체 응답(수십 초, 대부분 작성 모델)에 비해 작지만, 콜드 첫 요청에는 "
           "모델 로드가 더해져 웜보다 크게 느리다(이 측정은 임베딩 모델만 올린 상태의 값이며, 실서버 첫 요청에서 작성 모델과 메모리를 나눠 쓸 때는 9.64s가 관찰됐다: `ollama-live-20261021.json`의 첫 개선 후 요청). 인덱스는 메모리 캐시라 프로세스를 재시작하거나 매뉴얼이 바뀌면 다시 만든다. "
           "기존 키워드 분류는 거의 0에 가까운 비용이었으므로, 의미 검색은 정확도(6/14→12/14)를 얻는 대신 지연·디스크·로컬 모델 의존성을 지불한다."]
    (ROOT / "eval" / f"embedding-cost-{date.today():%Y%m%d}.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))

main()

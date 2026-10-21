"""검증기 개선(2차) 전후 비교 — 규칙을 고치기 전에 작성·기준선 저장한 사례 세트.

구성
- T(표적 회귀 28개): 이전에 문서화한 약점 유형(임계치·한글 동의어·숫자 먼저·표·부정문·'각각'·정직한 미조회 언급·
  시스템명 없는 일반 답변)에서 가져온 사례. 개선 대상으로 지목한 유형이므로 '독립 평가'가 아니라 표적 회귀 확인이다.
- V(자체 점검에서 발견한 부작용·회귀 탐침 8개): 개선 직후 '새 규칙이 진짜 주장을 가리지 않는가'를 점검하다 찾은 약점.
- U(설계 시 보지 않은 변형 6개): 구현 전에 적어 둔 변형. 개선 규칙이 일반화되는지 정직하게 보는 용도.
정상(통과해야 함)·오류(차단해야 함) 양쪽을 같이 둬서 '다 막기만 하는' 개선을 걸러낸다.
사용: .venv/bin/python eval/eval_verifier_v2.py [--output 새결과.json]
기본 실행은 과거 결과 파일을 보존하고, 기대 불일치 시 종료 코드 1을 반환한다.
(기준선은 eval/baseline/verifier_before_v2.py 스냅샷으로 즉석 계산)
"""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent.verifier import verify_answer


def mon(name, cpu, mem, status="degraded", alerts=()):
    return {"source": "monitoring", "data": {"system_name": name, "status": status, "cpu_percent": cpu,
                                             "memory_percent": mem, "alerts": list(alerts)}}

PAY = mon("payments-service", 91.4, 55.2, alerts=["CPU 91% (threshold 80%)"])
WEB = mon("web-01", 34.5, 48.1, "healthy")
AUTH = mon("auth-service", 78.3, 61.2)
TAIL = " 2) 인스턴스를 점검하세요. 3) 정상화 후 재발 방지 대책을 문서화하세요."

# (id, 설명, 수집 자료, 미조회 시스템, 답변, 기대 통과 여부)
CASES = [
 # ---- 정상(통과해야 함)
 ("T-P1","임계치 괄호 인용(현재값 일치)",[PAY],[],"1) payments-service CPU 91.4% (경고 기준 80% 초과)"+TAIL,True),
 ("T-P2","CPU 임계치 80%를 넘음 서술",[PAY],[],"1) payments-service의 CPU 사용률은 91.4%로 CPU 임계치 80%를 넘었습니다."+TAIL,True),
 ("T-P3","런북 문장 'CPU 90% 이상 지속 시'",[PAY,WEB],[],"1) payments-service CPU 91.4%, web-01 CPU 34.5%."+" 2) 표준 절차에 따라 CPU 90% 이상 지속 시 오토스케일링으로 인스턴스를 추가하세요. 3) 문서화하세요.",True),
 ("T-P4","시스템명·CPU·메모리 수치 없는 일반 답변",[AUTH],[],"1) 커넥션 풀 사용률 92%로 임계치를 초과했습니다. 2) p95 지연이 2.4s로 느립니다. 3) 풀 크기 확장 또는 타임아웃 설정을 검토하세요.",True),
 ("T-P5","정직한 미조회 언급(billing-service)",[WEB],["billing-service"],"1) billing-service는 모니터링 대상에 없어 조회하지 못했습니다. 2) web-01 CPU 34.5%는 정상입니다. 3) 시스템명을 확인하세요.",True),
 ("T-P6","부정문 '85%가 아니라 91.4%'",[PAY],[],"1) payments-service의 CPU는 85%가 아니라 91.4%입니다."+TAIL,True),
 ("T-P7","'각각' 두 시스템 순서 일치",[PAY,WEB],[],"1) payments-service와 web-01의 CPU 사용률은 각각 91.4%, 34.5%입니다."+TAIL,True),
 ("T-P8","마크다운 표(일치)",[PAY,WEB],[],"1) 조사 결과입니다.\n| 시스템 | CPU | 메모리 |\n|---|---|---|\n| payments-service | 91.4% | 55.2% |\n| web-01 | 34.5% | 48.1% |\n2) 점검하세요. 3) 문서화하세요.",True),
 ("T-P9","동의어 '프로세서 사용률'(일치)",[PAY],[],"1) payments-service의 프로세서 사용률은 91.4%입니다."+TAIL,True),
 ("T-P10","숫자 먼저 '91.4%의 CPU 사용률'(일치)",[PAY],[],"1) 91.4%의 CPU 사용률을 보이는 payments-service를 점검하세요."+" 2) 재시작하세요. 3) 문서화하세요.",True),
 ("T-P11","'91.4퍼센트' 표기(일치)",[PAY],[],"1) payments-service CPU 사용률은 91.4퍼센트입니다."+TAIL,True),
 ("T-P12","영어 서술(일치)",[PAY],[],"1) CPU usage of payments-service is 91.4%."+TAIL,True),
 ("T-P13","메모리 일치 + '중앙처리장치'",[PAY],[],"1) payments-service 중앙처리장치 사용률 91.4%, 메모리 55.2%입니다."+TAIL,True),
 ("T-P14","'약 91%' 반올림 + 임계치 별도 문장",[PAY],[],"1) payments-service CPU는 약 91%입니다. 2) CPU 임계치는 80%이므로 초과 상태입니다. 3) 문서화하세요.",True),
 # ---- 오류(차단해야 함)
 ("T-B1","동의어 '프로세서 사용률' 틀림",[PAY],[],"1) payments-service의 프로세서 사용률은 99%입니다."+TAIL,False),
 ("T-B2","'중앙처리장치 사용률' 틀림",[PAY,WEB],[],"1) payments-service CPU 91.4%, web-01의 중앙처리장치 사용률은 77%입니다."+TAIL,False),
 ("T-B3","'CPU 점유율' 틀림",[AUTH],[],"1) auth-service CPU 점유율은 55%입니다."+TAIL,False),
 ("T-B4","숫자 먼저 틀림",[PAY],[],"1) 99%의 CPU 사용률을 보이는 payments-service를 점검하세요."+" 2) 재시작하세요. 3) 문서화하세요.",False),
 ("T-B5","표 틀림(CPU 열)",[PAY,WEB],[],"1) 조사 결과입니다.\n| 시스템 | CPU | 메모리 |\n|---|---|---|\n| payments-service | 99% | 55.2% |\n| web-01 | 34.5% | 48.1% |\n2) 점검하세요. 3) 문서화하세요.",False),
 ("T-B6","'99퍼센트' 틀림",[PAY],[],"1) payments-service CPU 사용률은 99퍼센트입니다."+TAIL,False),
 ("T-B7","'각각' 순서 바뀜",[PAY,WEB],[],"1) payments-service와 web-01의 CPU 사용률은 각각 34.5%, 91.4%입니다."+TAIL,False),
 ("T-B8","메모리 틀림(동의어)",[PAY],[],"1) payments-service CPU 91.4%, 메모리 사용률 85%입니다."+TAIL,False),
 ("T-B9","미조회 시스템의 수치를 지어냄",[WEB],["billing-service"],"1) billing-service CPU 70%로 높습니다. 2) web-01 CPU 34.5%. 3) 점검하세요.",False),
 ("T-B10","임계치 표현이 있어도 현재값 틀림",[PAY],[],"1) payments-service CPU 99% (경고 기준 80% 초과)"+TAIL,False),
 ("T-B11","영어 틀림",[PAY],[],"1) CPU usage of payments-service is 99%."+TAIL,False),
 ("T-B12","표 틀림(메모리 열, 두 번째 행)",[PAY,WEB],[],"1) 조사 결과입니다.\n| 시스템 | CPU | 메모리 |\n|---|---|---|\n| payments-service | 91.4% | 55.2% |\n| web-01 | 34.5% | 90% |\n2) 점검하세요. 3) 문서화하세요.",False),
 ("T-B13","수집 안 된 새 시스템 환각",[PAY],[],"1) payments-service CPU 91.4%, shipping-service도 느립니다."+TAIL,False),
 ("T-B14","'각각' 두 번째 값 틀림",[PAY,WEB],[],"1) payments-service와 web-01의 CPU 사용률은 각각 91.4%, 60%입니다."+TAIL,False),
 # ---- 설계 시 보지 않은 변형(U)
 ("U1","'CPU 사용량' 틀림",[PAY],[],"1) payments-service의 CPU 사용량은 99%입니다."+TAIL,False),
 ("U2","'CPU utilization' 틀림",[PAY],[],"1) CPU utilization of payments-service: 99%."+TAIL,False),
 ("U3","'CPU가 99%까지' 틀림",[PAY],[],"1) payments-service CPU가 99%까지 올랐습니다."+TAIL,False),
 ("U4","'CPU 부하' 틀림",[PAY],[],"1) payments-service의 CPU 부하는 99%입니다."+TAIL,False),
 ("U5","'메모리 점유율' 틀림",[WEB],[],"1) web-01 메모리 점유율 99%입니다."+TAIL,False),
 ("U6","'CPU가 91.4%까지' 일치",[PAY],[],"1) payments-service CPU가 91.4%까지 올랐습니다."+TAIL,True),
 # ---- V: 개선 직후 자체 점검에서 발견한 부작용 탐침(임계치·부정 표현 제외 규칙이 진짜 주장을 가리지 않는지)
 ("V1","'99% 이상 지속되고 있습니다'(틀림)",[PAY],[],"1) payments-service CPU 사용률이 99% 이상 지속되고 있습니다."+TAIL,False),
 ("V2","'기준 시각 현재 99%'(틀림)",[PAY],[],"1) 기준 시각 현재 payments-service CPU 99%입니다."+TAIL,False),
 ("V3","'99%를 넘었습니다'(틀림)",[PAY],[],"1) payments-service CPU가 99%를 넘었습니다."+TAIL,False),
 ("V4","'91.4%가 아니라 99%'(틀림)",[PAY],[],"1) payments-service의 CPU는 91.4%가 아니라 99%입니다."+TAIL,False),
 ("V5","'91% 이상 지속되고 있습니다'(정상)",[PAY],[],"1) payments-service CPU 사용률이 91% 이상 지속되고 있습니다."+TAIL,True),
 ("V6","런북 '90% 이상 지속 시'(정상)",[PAY],[],"1) payments-service CPU 91.4%. 2) CPU 90% 이상 지속 시 오토스케일링하세요. 3) 문서화하세요.",True),
 ("V7","런북 'CPU가 90%를 넘기면'(정상)",[PAY],[],"1) payments-service CPU 91.4%. 2) CPU가 90%를 넘기면 인스턴스를 추가하세요. 3) 문서화하세요.",True),
 ("V8","실제 런북 문장 'CPU가 90%를 넘고 지속되면'(정상)",[PAY],[],"1) payments-service CPU 91.4%. 2) CPU가 90%를 넘고 지속되면 해당 인스턴스를 오토스케일링 그룹에서 한 대 더 띄워 부하를 분산한다. 3) 문서화하세요.",True),
]


def _load_baseline():
    import importlib.util
    spec = importlib.util.spec_from_file_location("verifier_before_v2", ROOT / "eval" / "baseline" / "verifier_before_v2.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.verify_answer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="새 평가 결과를 저장할 경로(생략하면 출력만)")
    args = parser.parse_args()
    before = _load_baseline()          # 2차 개선 직전 검증기 스냅샷
    rows = []
    for cid, desc, coll, unav, draft, should_pass in CASES:
        old = not before(draft, coll)
        new = not verify_answer(draft, coll, unavailable=unav)
        rows.append({"id": cid, "desc": desc, "expect_pass": should_pass, "before": old, "after": new,
                     "before_ok": old == should_pass, "after_ok": new == should_pass})
    def agg(prefix, key):
        r = [x for x in rows if x["id"].startswith(prefix)]
        good = [x for x in r if x["expect_pass"]]; bad = [x for x in r if not x["expect_pass"]]
        return {"정상 통과": f"{sum(x[key] for x in good)}/{len(good)}", "오류 차단": f"{sum(not x[key] for x in bad)}/{len(bad)}"}
    summary = {g: {"before": agg(p, "before"), "after": agg(p, "after")} for g, p in (("T", "T-"), ("U", "U"), ("V", "V"))}
    if args.output:
        args.output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for x in rows:
        if not x["after_ok"]:
            print("  ✗(개선 후)", x["id"], x["desc"], "| 기대", "통과" if x["expect_pass"] else "차단")

    return 1 if any(not x["after_ok"] for x in rows) else 0


if __name__ == "__main__":
    sys.exit(main())

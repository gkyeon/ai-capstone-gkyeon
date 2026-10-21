"""평가 기대 불일치와 실행 오류가 실패 종료로 이어지는지 독립 프로세스로 검사."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
env = dict(os.environ, LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false")
# 실제 평가기를 호출하되 결과 파일을 쓰지 않고 모든 답변을 통과시키는 오류만 주입한다.
script = "import sys; sys.path.insert(0, sys.argv[1]); import agent.verifier as v; v.verify_answer=lambda *a, **k: []; import runpy; path=sys.argv[1]+'/eval/eval_verifier_v2.py'; sys.argv=[path]; runpy.run_path(path, run_name='__main__')"
r = subprocess.run([sys.executable, "-c", script, str(ROOT)], env=env, capture_output=True, text=True)
assert r.returncode == 1 and "✗(개선 후)" in r.stdout, (r.returncode, r.stderr)
# 셸 실행기의 복사본에서만 하위 평가의 정상/기대 불일치/실행 오류를 재현한다.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp); (root / "eval").mkdir(); (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/python").symlink_to(sys.executable)
    (root / "eval/run_tests.sh").write_text((ROOT / "eval/run_tests.sh").read_text())
    for name in ["test_subagents", "test_expansion", "test_verification_features", "test_evidence_gate", "test_review_regressions", "test_evaluation_exit"]:
        (root / "eval" / (name + ".py")).write_text("pass\n")
    for code, expected in [("pass", 0), ("raise SystemExit(1)", 1), ("raise RuntimeError('injected')", 1)]:
        (root / "eval/eval_verifier_v2.py").write_text(code)
        r = subprocess.run(["bash", str(root / "eval/run_tests.sh")], env=env, capture_output=True, text=True)
        assert r.returncode == expected, (code, r.stdout, r.stderr)
print("PASS: 평가 기대 불일치 종료 코드, 전체 실행기 정상/평가 실패/실행 오류 전달")

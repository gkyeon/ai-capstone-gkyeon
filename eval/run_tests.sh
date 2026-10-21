#!/usr/bin/env bash
# 외부 과금 모델 없이 도는 테스트 모음. 프로젝트 루트에서: bash eval/run_tests.sh
set -uo pipefail
cd "$(dirname "$0")/.."
PY=".venv/bin/python"; [ -x "$PY" ] || PY=python3
fail=0
log_dir=$(mktemp -d "${TMPDIR:-/tmp}/capstone-tests.XXXXXX")
echo "Test logs: $log_dir"
for t in test_subagents test_expansion test_verification_features test_evidence_gate test_review_regressions test_evaluation_exit; do
  if $PY "eval/$t.py" >"$log_dir/$t.log" 2>&1; then echo "PASS  $t"; else echo "FAIL  $t ($log_dir/$t.log)"; fail=1; fi
done
# 기대 불일치와 실행 오류 모두 전체 테스트 실패로 전달한다. 과거 측정 파일은 보존한다.
if $PY eval/eval_verifier_v2.py; then
  echo "PASS  eval_verifier_v2"
else
  echo "FAIL  eval_verifier_v2"
  fail=1
fi
exit $fail

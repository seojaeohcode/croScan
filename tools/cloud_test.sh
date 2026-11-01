#!/bin/sh
# Run the croScan test suites on the server, in the app's own image (same Python, Java, libraries as production),
# against the working copy in /data/dev/croScan_app (code + tools + samples; samples never go into the image).
#   sh tools/cloud_test.sh            questions + extraction + work plans (about 3 min on 8 vCPU)
#   sh tools/cloud_test.sh quick      questions + work plans only
# The tests write only to throwaway temp folders, on the data disk (/data/tmp/croscan_test, emptied after each
# run): the 10 GB system disk holds the Docker images and is too small for the work-plan stress files.
set -e
DEV=${DEV:-/data/dev/croScan_app}
TMP=${TMP:-/data/tmp/croscan_test}
mkdir -p "$TMP" && chown 10001 "$TMP"
trap 'rm -rf "$TMP"/*' EXIT
run() { docker run --rm -u 10001 -e PYTHONIOENCODING=utf-8 -e HOME=/tmp -e TMPDIR=/tmp -v "$TMP":/tmp -v "$DEV":/w:ro -w /w --entrypoint sh croscan:latest -c "$1"; }
echo "== 반장 질문 (check_questions)";  run "python tools/check_questions.py | tail -1"
if [ "$1" != "quick" ]; then
  echo "== 허가서 추출 (check_extract)"; run "python tools/check_extract.py 2>&1 | tail -1"
fi
echo "== 작업계획서 (stress_workplan)"; run "python tools/stress_workplan.py ${WP_PLANS:-20} ${WP_SEED:-7} | grep -E 'PASS|FAIL|통과'"

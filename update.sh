#!/usr/bin/env bash
# 모든 차트와 스냅샷을 다시 만든다. 로컬과 GitHub Actions에서 같은 것을 쓴다.
#
# 한 스크립트가 실패해도 나머지는 돌린다 — 외부 API 하나가 죽었다고 전체
# 갱신을 버릴 이유가 없다. 실패가 있으면 마지막에 0이 아닌 값으로 끝내
# Actions가 빨간불을 띄우게 한다.
set -uo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-./.venv/bin/python}"
command -v "$PY" >/dev/null 2>&1 || PY=python3

failed=()
run() {
  echo "--- $*"
  "$PY" "$@" || failed+=("$*")
}

run disclosures.py
run progress.py
run segments.py
run sites.py
run backlog.py
run arr_model.py
run funding.py
run peers.py
run valuation.py
run snapshot.py

mkdir -p assets
for f in progress segments sites backlog arr_model funding peers valuation; do
  [ -f "output/$f.png" ] && cp "output/$f.png" "assets/$f.png"
done

# 사이트는 assets/ 를 참조하므로 복사가 끝난 뒤에 만든다
run build_site.py

if [ ${#failed[@]} -gt 0 ]; then
  printf '\n실패한 스크립트:\n'
  printf '  %s\n' "${failed[@]}"
  exit 1
fi
echo "모두 완료"

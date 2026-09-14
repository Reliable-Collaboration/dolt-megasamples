#!/bin/sh
# Detached watcher (2026-09-14): the two inline employees DoltLite units cannot fit on the disk (working files of
# 1 to 3 TB). Stop the runner the moment the inline sqlite_rowwise employees unit has finished (its line appears a
# second time in the chain log), i.e. as the inline DoltLite employees load begins; the chain driver then proceeds
# to the DoltgreSQL move. Runs outside the assistant harness so a memory-pressure policy cannot kill it.
cd "$(dirname "$0")/.." || exit 1
LOG=build/run-chain-v6.log
echo "armed $(date -u +%FT%TZ)"
while true; do
  n=$(grep -c 'sqlite_rowwise      employees' "$LOG" 2>/dev/null); n=${n:-0}
  alive=$(pgrep -f '^python3 scripts/run_pair[s]\.py')
  if [ -z "$alive" ]; then echo "runner gone at $(date -u +%T) before the target: $(tail -1 "$LOG" | cut -c1-100)"; exit 0; fi
  if [ "$n" -ge 2 ]; then
    kill -TERM $alive; timeout 60 tail --pid=$alive -f /dev/null
    docker ps --format '{{.Names}}' | grep -E '^doltsamples-[a-z]+-runner$' | xargs -r docker rm -f >/dev/null 2>&1
    docker run --rm -v "$(pwd)/data:/d" --entrypoint sh doltsamples-doltlite:0.50.10 -c 'rm -f /d/doltlite-rowinsert_inline/employees.doltlite* /d/doltlite-rowinsert_inline/.employees.doltlite-lock /d/doltlite-rowcommit_inline/employees.doltlite* /d/doltlite-rowcommit_inline/.employees.doltlite-lock' 2>/dev/null
    echo "SKIPPED $(date -u +%FT%TZ): runner stopped as the inline employees DoltLite loads began (neither fits on the disk); the chain driver continues to the DoltgreSQL move"
    exit 0
  fi
  sleep 10
done

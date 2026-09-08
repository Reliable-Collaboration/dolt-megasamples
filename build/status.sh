#!/usr/bin/env bash
# One status block, assembled fully before anything is printed so it arrives as a single
# notification rather than one per line. Every figure names its unit and what it measures.
cd /home/mattc/wsldev/dolt-megasamples || exit 1
LOG=/tmp/claude-1000/-home-mattc-wsldev-mysql-megasamples/72c536ac-76b5-441c-a32b-42a207ab7990/scratchpad/full_experiment.log

phase=$(grep '^=== ' "$LOG" 2>/dev/null | tail -1 | sed 's/^=== //;s/ 20[0-9-]*T.*//')
out=$(python3 scripts/summary.py --outstanding 2>/dev/null | sed -n '/OUTSTANDING/,$p')
# The most recently written trace of ANY mode. Globbing `rowcommit-*` missed the inline loads
# entirely -- they are written as `rowcommit_inline-<db>.json`, which does not match -- so for ten
# hours this line reported a completed deferred load as if it were the one running.
livefile=$(ls -t build/trace/*.json 2>/dev/null | head -1)
livemode=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['mode'])" "$livefile" 2>/dev/null)
livedb=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['database'])" "$livefile" 2>/dev/null)
tr_=$(python3 scripts/trace_report.py --mode "$livemode" --only "$livedb" 2>/dev/null \
      | grep -E "sample\(s\)|at .* rows:|anon slope|reaches the" | sed 's/^ *//')
worker=$(docker stats --no-stream --format '{{.MemUsage}}' doltsamples-dolt-runner 2>/dev/null)
timing=$(docker stats --no-stream --format '{{.MemUsage}}' doltsamples-mysql-timing 2>/dev/null)

printf 'STATUS %s — phase: %s\n%s\n\n  live per-row-commit load (peak load RAM is anon; disk is bytes stored):\n  %s\n\n  RESOURCES\n    worker container RAM in use / limit : %s\n    timing MySQL RAM in use / limit     : %s\n    host RAM available                  : %s MB\n    filesystem free                     : %s\n' \
  "$(date '+%H:%M')" "${phase:-?}" "$out" "$(echo "$tr_" | sed 's/^/  /')" \
  "${worker:-not running}" "${timing:-not running}" \
  "$(free -m | awk 'NR==2{print $7}')" "$(df -h /home | awk 'NR==2{print $4}')"

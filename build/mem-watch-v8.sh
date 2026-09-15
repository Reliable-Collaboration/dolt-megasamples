#!/bin/sh
# Detached memory watch for chain v8 (12 GiB cap): every 30 s, the DoltgreSQL runner container's anonymous
# memory and its cgroup total, keeping the running peak per unit, so an OOM kill leaves a trace of how far
# the engine got. Log: build/mem-watch-v8.log. Ends when the chain ends.
cd "$(dirname "$0")/.." || exit 1
peak=0; unit=""
while pgrep -f '^sh build/run-[c]hain-v8\.sh' >/dev/null; do
  u=$(python3 scripts/progress.py 2>/dev/null | grep -E '^\s+running' | sed 's/ — .*//; s/^ *running: //')
  if [ "$u" != "$unit" ]; then
    [ -n "$unit" ] && echo "$(date -u +%FT%TZ) END   [$unit] engine peak $((peak / 1048576)) MiB"
    unit="$u"; peak=0
  fi
  s=$(docker exec doltsamples-doltgres-runner sh -c 'grep -E "^(anon|shmem) " /sys/fs/cgroup/memory.stat; cat /sys/fs/cgroup/memory.current' 2>/dev/null)
  if [ -n "$s" ]; then
    anon=$(echo "$s" | awk '/^anon /{a=$2} /^shmem /{b=$2} END{print a+b}')
    cur=$(echo "$s" | tail -1)
    [ "$anon" -gt "$peak" ] 2>/dev/null && peak=$anon
    echo "$(date -u +%FT%TZ) [$unit] engine $((anon / 1048576)) MiB (peak $((peak / 1048576)) MiB), cgroup $((cur / 1048576)) MiB"
  fi
  sleep 30
done
[ -n "$unit" ] && echo "$(date -u +%FT%TZ) END   [$unit] engine peak $((peak / 1048576)) MiB"
echo "$(date -u +%FT%TZ) chain v8 gone; memory watch ends"

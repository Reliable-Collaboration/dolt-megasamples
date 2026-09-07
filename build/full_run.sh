#!/usr/bin/env bash
# The whole experiment at both index policies. Deferred first, so the primary result is complete
# before the variant starts; each invocation is resumable, so re-running this picks up where it
# stopped rather than starting over.
cd /home/mattc/wsldev/dolt-megasamples || exit 1
echo "=== DEFERRED: 5 phases x 21 databases  $(date -Is) ==="
python3 -u scripts/run_all.py --restart --repeat 3 --repeat-budget 180
echo "=== deferred finished with $?  $(date -Is) ==="
echo "=== INLINE: 3 row-by-row phases x 21 databases  $(date -Is) ==="
python3 -u scripts/run_all.py --indexes inline --repeat 3 --repeat-budget 180
echo "=== inline finished with $?  $(date -Is) ==="
echo "=== ALL RUNS COMPLETE  $(date -Is) ==="

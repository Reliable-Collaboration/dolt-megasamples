#!/usr/bin/env bash
# The whole experiment, unattended: both index policies over every database, then the report.
#
#   scripts/run_experiment.sh 2>&1 | tee build/run.log
#
# Roughly a day of wall clock. The deferred pass is the primary result -- five tests over 21
# databases -- and the inline pass repeats the three row-by-row tests with every index maintained,
# which is the comparison and is deliberately last.
#
# Neither pass uses --restart. A run is resumable by design: a unit already recorded as done is
# skipped, so an interrupted run continues rather than starting over, and a unit that failed is
# retried. Add --restart to run_all.py by hand if you want the previous results discarded.
cd "$(dirname "$0")/.." || exit 1
say() { echo "=== $* $(date -Is) ==="; }


say "source MySQL up"
(cd ../mysql-megasamples && docker compose up -d mysql)
for i in $(seq 90); do docker exec megasamples-mysql mysql -uroot -proot -e "SELECT 1" >/dev/null 2>&1 && break; sleep 2; done

say "preflight: every schema into both engines"
python3 -u scripts/preflight.py || say "PREFLIGHT REPORTED PROBLEMS - continuing, they are in the log"

say "DEFERRED PASS: 5 tests x 21 databases, indexes deferred"
python3 -u scripts/run_all.py --repeat 3 --repeat-budget 180
say "deferred pass exited $?"

say "INLINE PASS: the 3 row-by-row tests x 21 databases, indexes maintained"
python3 -u scripts/run_all.py --indexes inline --repeat 3 --repeat-budget 180
say "inline pass exited $?"

say "measuring rows and index parity for every mode"
(cd ../mysql-megasamples && docker compose up -d mysql) && sleep 20
make measure-all

say "report, figures and documents"
make report
make check || say "CHECK REPORTED PROBLEMS - see above"

say "ALL DONE"

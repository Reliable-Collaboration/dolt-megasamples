#!/usr/bin/env bash
# The whole experiment, unattended. Waits for the employees load already running, then does
# everything else and produces the report.
#
# The deferred pass deliberately does NOT use --restart: employees/dolt_rowcommit is the single most
# expensive unit in the experiment at about three hours, it is being loaded right now by this same
# code, and re-running it would buy nothing. Every other unit is still to do.
cd /home/mattc/wsldev/dolt-megasamples || exit 1
SP=/tmp/claude-1000/-home-mattc-wsldev-mysql-megasamples/72c536ac-76b5-441c-a32b-42a207ab7990/scratchpad
say() { echo "=== $* $(date -Is) ==="; }

say "waiting for the employees load to finish"
while pgrep -f "run_all.py --only employees" >/dev/null 2>&1; do sleep 60; done
say "employees finished"
python3 -c "
import json
u=json.load(open('build/progress.json'))['units'].get('dolt_rowcommit/employees',{})
print(f\"  employees/dolt_rowcommit: {u.get('status')} {u.get('seconds')}s {u.get('bytes')} bytes\")
print(f\"  error: {u.get('error')}\" if u.get('error') else '  no error')"

say "source MySQL up"
(cd ../mysql-megasamples && docker compose up -d mysql)
for i in $(seq 90); do docker exec megasamples-mysql mysql -uroot -proot -e "SELECT 1" >/dev/null 2>&1 && break; sleep 2; done

say "preflight: every schema into both engines"
python3 -u scripts/preflight.py || say "PREFLIGHT REPORTED PROBLEMS - continuing, they are in the log"

say "DEFERRED PASS: 5 phases x 21 databases (keeping the employees unit already done)"
python3 -u scripts/run_all.py --repeat 3 --repeat-budget 180
say "deferred pass exited $?"

say "INLINE PASS: 3 row-by-row phases x 21 databases"
python3 -u scripts/run_all.py --indexes inline --repeat 3 --repeat-budget 180
say "inline pass exited $?"

say "measuring rows and index parity for every mode"
(cd ../mysql-megasamples && docker compose up -d mysql) && sleep 20
make measure-all

say "report, figures and documents"
make report
make check || say "CHECK REPORTED PROBLEMS - see above"

say "ALL DONE"

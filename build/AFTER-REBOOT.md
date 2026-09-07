# Picking up after the WSL2 restart

`.wslconfig` was set to `memory=20GB, swap=8GB`. The worker's limit is computed from MemTotal,
so it becomes about 16-17 GB with no code change; `python3 scripts/facts.py | head -1` and
`python3 -c "import sys;sys.path.insert(0,'scripts');from common import HOST_GB,MEM_WORKER;
print(HOST_GB, MEM_WORKER)"` both confirm it.

    cd ~/wsldev/mysql-megasamples && docker compose up -d mysql     # source only, 1 GB
    cd ../dolt-megasamples
    python3 -u scripts/run_all.py --only employees --phase dolt_rowcommit --restart --allow-busy

If that is OOM-killed, the fallback is `--gc-every 20`, which packs the store during the load. It
changes what is measured and says so in the load's notes, and it is the only lever that lowers the
memory: the trace's idle reading showed the growth is the cost of opening accumulated history, not
of the chunk being loaded.

Traces kept from before the restart:

  build/trace/employees-at-7gb-limit.json   51 samples, reached 1,274,973 rows at 4.5 GB anon
  build/trace/rowcommit-employees.json      the 12 GB attempt, stopped by the restart
  build/trace/rowcommit-chinook.json        a complete small load, for comparison

The full experiment has not been run on the fixed method. `build/results.json` is absent and
`make check` fails because of it, which is correct. `make estimate` projects 14.5 h for the deferred
pass and 13.7 h for the inline pass.

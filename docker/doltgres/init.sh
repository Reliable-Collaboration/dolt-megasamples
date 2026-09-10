#!/bin/sh
# The same two accounts the Dolt side has, on DoltgreSQL: `demo` reads every database, `admin` can
# do anything. Applied on every `up` by the doltgres-init service (the image's own psql), because
# the data directory is written by the loads before the server ever starts and the image's
# first-start hook never fires. Every statement is allowed to fail on its own -- a role that
# already exists is the normal case on the second `up` -- and what failed is printed.
set -u
export PGPASSWORD="${DOLTGRES_PASSWORD:-doltsamples}"
P="psql -X -h doltgres -U postgres -v ON_ERROR_STOP=0 -q"
for i in $(seq 30); do $P -d postgres -c 'SELECT 1' >/dev/null 2>&1 && break; sleep 2; done
$P -d postgres -c "CREATE ROLE demo LOGIN PASSWORD '${DEMO_PASSWORD:-demo}'" 2>&1 | grep -v 'already exists'
$P -d postgres -c "CREATE ROLE admin LOGIN PASSWORD '${ADMIN_PASSWORD:-admin}' SUPERUSER" 2>&1 | grep -v 'already exists'
for db in $($P -d postgres -tAc "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres'"); do
  $P -d "$db" -f /init.sql 2>&1 | grep -v '^$' | sed "s/^/$db: /"
done
echo "accounts applied"

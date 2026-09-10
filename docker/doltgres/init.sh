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
# a password inside a PostgreSQL string literal (standard_conforming_strings): single quotes doubled.
# ALTER ROLE applies a changed password to a role that already exists; CREATE ROLE alone kept the
# first one for good (2026-09-10 review).
esc() { printf "%s" "$1" | sed "s/'/''/g"; }
DEMO=$(esc "${DEMO_PASSWORD:-demo}")
ADMIN=$(esc "${ADMIN_PASSWORD:-admin}")
$P -d postgres -c "CREATE ROLE demo LOGIN PASSWORD '$DEMO'" 2>&1 | grep -v 'already exists'
$P -d postgres -c "ALTER ROLE demo WITH LOGIN PASSWORD '$DEMO'" 2>&1 | grep -v '^ALTER ROLE$'
$P -d postgres -c "CREATE ROLE admin LOGIN PASSWORD '$ADMIN' SUPERUSER" 2>&1 | grep -v 'already exists'
$P -d postgres -c "ALTER ROLE admin WITH LOGIN SUPERUSER PASSWORD '$ADMIN'" 2>&1 | grep -v '^ALTER ROLE$'
for db in $($P -d postgres -tAc "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres'"); do
  $P -d "$db" -f /init.sql 2>&1 | grep -v '^$' | sed "s/^/$db: /"
done
echo "accounts applied"

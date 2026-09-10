#!/bin/sh
# The same two accounts sql-megasamples uses, so the comparison is like for like: `demo` can read and
# nothing else, `admin` can do anything. Applied by the dolt-init service on every `up` rather than by
# the image's /docker-entrypoint-initdb.d hook, which only fires when the data directory is empty --
# and ours is not: it is written by the loads before the server ever starts.
#
# The passwords are DEMO_PASSWORD and ADMIN_PASSWORD, the variables the consoles, the landing page and
# `make test-stack` read, and ALTER USER applies a changed one to an account that already exists. The
# first version typed 'demo' and 'admin' into a static init.sql, so a password set in .env was
# published and tested but refused by the server (2026-09-10 review).
set -u
# a password inside a MySQL string literal: backslashes and single quotes escaped
esc() { printf "%s" "$1" | sed -e 's/\\/\\\\/g' -e "s/'/''/g"; }
DEMO=$(esc "${DEMO_PASSWORD:-demo}")
ADMIN=$(esc "${ADMIN_PASSWORD:-admin}")
SQL="CREATE USER IF NOT EXISTS 'demo'@'%' IDENTIFIED BY '$DEMO';
ALTER USER 'demo'@'%' IDENTIFIED BY '$DEMO';
CREATE USER IF NOT EXISTS 'admin'@'%' IDENTIFIED BY '$ADMIN';
ALTER USER 'admin'@'%' IDENTIFIED BY '$ADMIN';
GRANT SELECT, SHOW VIEW ON *.* TO 'demo'@'%';
GRANT ALL PRIVILEGES ON *.* TO 'admin'@'%' WITH GRANT OPTION;"
for i in $(seq 30); do
  if printf "%s\n" "$SQL" | mysql -hdolt -P3306 -uroot -p"${DOLT_ROOT_PASSWORD:-root}"; then
    echo "accounts applied"
    exit 0
  fi
  sleep 2
done
echo "could not apply the accounts"
exit 1

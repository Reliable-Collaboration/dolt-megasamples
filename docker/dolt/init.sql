-- The same two accounts mysql-megasamples uses, so the comparison is like for like: `demo` can read
-- and nothing else, `admin` can do anything. Applied by the `dolt-init` service on every `up`
-- rather than by the image's /docker-entrypoint-initdb.d hook, which only fires when the data
-- directory is empty -- and ours is not: it is written by the loader before the server ever starts.
CREATE USER IF NOT EXISTS 'demo'@'%'  IDENTIFIED BY 'demo';
CREATE USER IF NOT EXISTS 'admin'@'%' IDENTIFIED BY 'admin';
GRANT SELECT, SHOW VIEW ON *.* TO 'demo'@'%';
GRANT ALL PRIVILEGES ON *.* TO 'admin'@'%' WITH GRANT OPTION;

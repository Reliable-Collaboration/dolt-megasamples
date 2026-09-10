-- Run once per database by init.sh: what the read-only account needs to browse it.
GRANT USAGE ON SCHEMA public TO demo;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO demo;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO demo;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_catalog TO demo;

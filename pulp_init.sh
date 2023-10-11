#!/usr/bin/env bash
(grep -qxF "listen_addresses = '*'" /var/lib/pgsql/data/postgresql.conf || echo "listen_addresses = '*'" >> /var/lib/pgsql/data/postgresql.conf) &&
(grep -qxF "host all all 0.0.0.0/0 md5" /var/lib/pgsql/data/pg_hba.conf || echo "host all all 0.0.0.0/0 md5" >> /var/lib/pgsql/data/pg_hba.conf) &&
(grep -qxF "host all all ::/0 md5" /var/lib/pgsql/data/pg_hba.conf || echo "host all all ::/0 md5" >> /var/lib/pgsql/data/pg_hba.conf) &&
runuser postgres -c 'echo "ALTER USER postgres WITH PASSWORD '"'"'password'"'"';" | /usr/bin/psql'

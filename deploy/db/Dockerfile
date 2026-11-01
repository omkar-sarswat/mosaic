# PostgreSQL 18 + PostGIS 3.6 + Apache AGE 1.8 (from the PGDG apt repository).
FROM postgis/postgis:18-3.6
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-18-age \
 && rm -rf /var/lib/apt/lists/*
# Do not preload AGE (session_preload_libraries): its hooks expect ag_catalog to exist and break
# initdb. DRISHTI runs CREATE EXTENSION age and LOAD 'age' on its own connections.

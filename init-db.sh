#!/bin/bash
set -e

# 'biz_rag' 데이터베이스는 docker-compose에서 자동으로 생성됩니다.
# 여기서는 해당 데이터베이스에 접속하여 확장을 활성화합니다.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "biz_rag" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS pgvector;
    CREATE EXTENSION IF NOT EXISTS age;
    LOAD 'age';
    SET search_path = ag_catalog, "$user", public;
    SELECT create_graph('biz_rag_graph');
EOSQL

# 'biz_table' 데이터베이스를 추가로 생성하고 확장을 활성화합니다.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
    CREATE DATABASE biz_table;
EOSQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "biz_table" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS pgvector;
EOSQL

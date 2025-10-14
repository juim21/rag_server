#!/bin/bash
set -e

# PostgreSQL이 시작될 때까지 대기
until pg_isready -U "$POSTGRES_USER"; do
  echo "Waiting for PostgreSQL to start..."
  sleep 2
done

echo "PostgreSQL is ready. Initializing databases..."

# pgvector 확장 및 데이터베이스 생성
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- pgvector 확장 활성화
    CREATE EXTENSION IF NOT EXISTS vector;

    -- biz_rag 데이터베이스 생성
    SELECT 'CREATE DATABASE biz_rag'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'biz_rag')\gexec

    -- biz_table 데이터베이스 생성
    SELECT 'CREATE DATABASE biz_table'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'biz_table')\gexec
EOSQL

# biz_rag 데이터베이스에 pgvector 확장 추가
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "biz_rag" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

# biz_table 데이터베이스에 pgvector 확장 추가
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "biz_table" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

echo "Database initialization completed successfully!"

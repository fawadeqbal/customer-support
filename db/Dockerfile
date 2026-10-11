# Postgres 16 (Alpine) + the pgvector extension, compiled from source.
# The official postgres:16-alpine image does not include pgvector.
FROM postgres:16-alpine

ARG PGVECTOR_VERSION=v0.8.0

RUN apk add --no-cache --virtual .build-deps git build-base \
    && git clone --branch ${PGVECTOR_VERSION} --depth 1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make with_llvm=no OPTFLAGS="" \
    && make with_llvm=no install \
    && cd / && rm -rf /tmp/pgvector \
    && apk del .build-deps

# Runs once, the first time the database is created
COPY init.sql /docker-entrypoint-initdb.d/

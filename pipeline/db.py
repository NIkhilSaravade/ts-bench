"""T5: a thin psycopg connection helper. Reads DATABASE_URL from the
environment, defaulting to the local infra/docker-compose.yml credentials
so `uv run ...` scripts work out of the box against a local Postgres."""

import os

import psycopg

DEFAULT_DATABASE_URL = "postgresql://tsbench:tsbench@localhost:5432/tsbench"


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))

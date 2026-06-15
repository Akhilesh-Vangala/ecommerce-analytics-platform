"""Shared database connection helper.

Reads connection settings from `.env` (see `.env.example`). Used by all ETL
and SQL-runner scripts so connection logic lives in exactly one place.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def get_connection_params() -> dict:
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
        "dbname": os.environ.get("DB_NAME", "olist_analytics"),
        "user": os.environ.get("DB_USER", ""),
        "password": os.environ.get("DB_PASSWORD", ""),
    }


def get_psycopg2_connection():
    params = get_connection_params()
    conn_kwargs = {k: v for k, v in params.items() if v}
    return psycopg2.connect(**conn_kwargs)


def get_engine() -> Engine:
    p = get_connection_params()
    auth = p["user"]
    if p["password"]:
        auth += f":{p['password']}"
    url = f"postgresql+psycopg2://{auth}@{p['host']}:{p['port']}/{p['dbname']}"
    return create_engine(url)

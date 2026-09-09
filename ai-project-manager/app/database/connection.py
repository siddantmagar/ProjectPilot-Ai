"""Database connection setup; swapping to Postgres only requires changing DATABASE_URL.

This remains portable provided no other code imports sqlite3 or uses SQLite-specific SQL
directly.
"""

import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./project_pilot.db")

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
	engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)


class Base(DeclarativeBase):
	"""Shared declarative base for all ORM models."""

	pass


SessionLocal = sessionmaker(
	bind=engine,
	autoflush=False,
	autocommit=False,
)


def get_session() -> Generator[Session, None, None]:
	"""Yield a database session and close it after use."""
	session = SessionLocal()
	try:
		yield session
	finally:
		session.close()
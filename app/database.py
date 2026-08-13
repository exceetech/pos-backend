from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# pool_pre_ping: issues a cheap "is this connection still alive" check
# before handing it out. Without this, a connection that Cloud SQL (or
# any managed Postgres) has silently closed after sitting idle surfaces
# as a hard-to-debug "server closed the connection unexpectedly" error
# on whatever request happened to draw it next, instead of SQLAlchemy
# quietly reconnecting.
# pool_size/max_overflow: explicit instead of relying on SQLAlchemy's
# defaults (5/10) — each Cloud Run instance holds its own pool, and
# multiple instances can spin up under load, so this is worth being
# deliberate about rather than inheriting whatever the default happens
# to be.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
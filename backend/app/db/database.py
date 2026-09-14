import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Normally you'd use python-dotenv, but for simplicity we can fall back to the env var directly
# We will use dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_rFvRn3LNpm0q@ep-fancy-morning-ax0tgw8p-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = f"postgresql+psycopg2://postgres:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST', 'localhost')}:5432/cronos_db"


engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

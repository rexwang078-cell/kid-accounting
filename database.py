import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 優先讀取 Render 環境變數裡的資料庫網址，如果沒有，就用本地的 SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kid_accounting.db")

# 修正 SQLAlchemy 對 postgres:// 協定的相容性問題
if DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"):
    # 強制將開頭替換為 postgresql+psycopg://
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# 判斷連線方式
if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

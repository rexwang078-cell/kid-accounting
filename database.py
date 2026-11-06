from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 建立 SQLite 資料庫檔案 (會在專案資料夾產生 kid_accounting.db)
SQLALCHEMY_DATABASE_URL = "sqlite:///./kid_accounting.db"

# 建立資料庫引擎
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 建立資料庫會話 (Session) 類別
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 建立 Base 類別，後續的模型都會繼承它
Base = declarative_base()
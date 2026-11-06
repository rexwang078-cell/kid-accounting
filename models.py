from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    line_id = Column(String, unique=True, index=True)
    name = Column(String)
    role = Column(String)
    personal_balance = Column(Float, default=0.0)
    deposited_balance = Column(Float, default=0.0)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    actor_id = Column(Integer)
    type = Column(String)
    amount = Column(Float)
    note = Column(String)
    status = Column(String, default="completed") # ★ 新增：pending, completed, rejected
    timestamp = Column(DateTime, default=datetime.utcnow)

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    line_id = Column(String, unique=True, index=True)
    name = Column(String)
    role = Column(String)                             
    personal_balance = Column(Float, default=0.0)     # ★ 手邊的個人餘額 (可為負數)
    deposited_balance = Column(Float, default=0.0)    # ★ 寄放在家長的餘額

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id")) # 這筆帳影響的小孩 ID
    actor_id = Column(Integer)                        # 誰填寫的 (大人或小孩)
    type = Column(String)                             # 類型
    amount = Column(Float)                            
    note = Column(String, nullable=True)              
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
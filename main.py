from pydantic import BaseModel
from fastapi import FastAPI, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse # ★ 新增：用於下載檔案
from sqlalchemy.orm import Session
import models
from database import engine, SessionLocal
from datetime import datetime, timedelta
import os

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="親子記帳系統 API")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root(): return {"message": "API 運行中"}

@app.post("/init_users/")
def init_users(db: Session = Depends(get_db)):
    if db.query(models.User).first(): return {"message": "已存在"}
    users = [
        models.User(line_id="test_dad", name="爸爸", role="parent"),
        models.User(line_id="test_mom", name="媽媽", role="parent"),
        models.User(line_id="test_child_01", name="大寶", role="child", personal_balance=0.0, deposited_balance=0.0),
        models.User(line_id="test_child_02", name="二寶", role="child", personal_balance=0.0, deposited_balance=0.0)
    ]
    db.add_all(users)
    db.commit()
    return {"message": "初始成功"}

@app.get("/app")
def read_ui(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

class TransactionCreate(BaseModel):
    user_id: int
    actor_id: int
    type: str
    amount: float
    note: str = ""

@app.post("/api/transaction/")
def create_transaction(transaction: TransactionCreate, db: Session = Depends(get_db)):
    actor = db.query(models.User).filter(models.User.id == transaction.actor_id).first()
    if actor and actor.role == 'child' and transaction.type in ['allowance', 'withdraw_deposit']:
        return {"status": "error", "message": "權限不足：小孩無法執行大人的動作！"}

    db_transaction = models.Transaction(
        user_id=transaction.user_id, actor_id=transaction.actor_id,
        type=transaction.type, amount=transaction.amount, note=transaction.note
    )
    db.add(db_transaction)
    
    target_user = db.query(models.User).filter(models.User.id == transaction.user_id).first()
    if target_user:
        if transaction.type == 'expense':
            target_user.personal_balance -= transaction.amount
        elif transaction.type == 'deposit':
            target_user.deposited_balance += transaction.amount
        elif transaction.type == 'allowance':
            target_user.personal_balance += transaction.amount
        elif transaction.type == 'withdraw_deposit':
            target_user.personal_balance += transaction.amount
            target_user.deposited_balance -= transaction.amount
            
    db.commit()
    return {"status": "success"}

# ★ 新增：修改餘額用的資料格式
class BalanceUpdate(BaseModel):
    personal_balance: float
    deposited_balance: float

# ★ 新增：家長設定初始值 / 校正餘額的 API
@app.put("/api/user/{user_id}/balance")
def update_balance(user_id: int, actor_id: int, balances: BalanceUpdate, db: Session = Depends(get_db)):
    actor = db.query(models.User).filter(models.User.id == actor_id).first()
    if not actor or actor.role != 'parent':
        return {"status": "error", "message": "只有家長可以修改餘額！"}

    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if target_user:
        # 新增一筆校正紀錄，方便日後查閱 (類型為 adjustment，不影響收支統計)
        note_str = f"⚙️ 家長校正餘額：手邊改為 ${balances.personal_balance}, 寄放改為 ${balances.deposited_balance}"
        db_transaction = models.Transaction(
            user_id=user_id, actor_id=actor_id,
            type='adjustment', amount=0, note=note_str
        )
        db.add(db_transaction)
        
        target_user.personal_balance = balances.personal_balance
        target_user.deposited_balance = balances.deposited_balance
        db.commit()
        return {"status": "success"}
    return {"status": "error", "message": "找不到該使用者"}

# ★ 新增：下載資料庫檔案的 API
@app.get("/api/export_db/")
def export_db(user_id: int, db: Session = Depends(get_db)):
    actor = db.query(models.User).filter(models.User.id == user_id).first()
    if not actor or actor.role != 'parent':
        return {"status": "error", "message": "只有家長可以下載資料庫！"}
    
    file_path = "kid_accounting.db"
    if os.path.exists(file_path):
        # 將 SQLite 資料庫檔案直接回傳給家長下載
        return FileResponse(file_path, media_type="application/octet-stream", filename="kid_accounting_backup.db")
    return {"status": "error", "message": "找不到資料庫檔案"}

@app.get("/api/transactions/")
def get_transactions(user_id: int = 0, skip: int = 0, start_date: str = None, end_date: str = None, db: Session = Depends(get_db)):
    query = db.query(models.Transaction, models.User.name).join(
        models.User, models.Transaction.user_id == models.User.id
    )
    if user_id > 0: query = query.filter(models.Transaction.user_id == user_id)
    if start_date: query = query.filter(models.Transaction.timestamp >= f"{start_date} 00:00:00")
    if end_date: query = query.filter(models.Transaction.timestamp <= f"{end_date} 23:59:59")
        
    records = query.order_by(models.Transaction.timestamp.desc()).offset(skip).limit(15).all()
    return [
        {
            "id": r.Transaction.id, "type": r.Transaction.type, "amount": r.Transaction.amount,
            "note": r.Transaction.note, "timestamp": r.Transaction.timestamp, "user_name": r.name
        } for r in records
    ]

@app.get("/api/user/{user_id}")
def get_user_info(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.User).filter(models.User.id == user_id).first()

@app.get("/api/users/")
def get_all_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()

@app.get("/api/stats/")
def get_stats(user_id: int, start_date: str, end_date: str, db: Session = Depends(get_db)):
    query = db.query(models.Transaction).filter(
        models.Transaction.user_id == user_id,
        models.Transaction.timestamp >= f"{start_date} 00:00:00",
        models.Transaction.timestamp <= f"{end_date} 23:59:59"
    )
    transactions = query.order_by(models.Transaction.timestamp).all()
    
    daily_stats = {}
    total_expense = 0
    total_allowance = 0
    
    for t in transactions:
        date_str = t.timestamp.strftime("%Y-%m-%d")
        if date_str not in daily_stats:
            daily_stats[date_str] = {"income": 0, "expense": 0}
            
        if t.type == 'expense':
            daily_stats[date_str]["expense"] += t.amount
            total_expense += t.amount
        elif t.type in ['allowance', 'withdraw_deposit']:
            daily_stats[date_str]["income"] += t.amount
            total_allowance += t.amount
            
    return {
        "total_allowance": total_allowance,
        "total_expense": total_expense,
        "daily": daily_stats
    }
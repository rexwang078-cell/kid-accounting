from pydantic import BaseModel
from fastapi import FastAPI, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import models
from database import engine, SessionLocal
from datetime import datetime
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

@app.post("/api/system/reset_db/")
def reset_db(db: Session = Depends(get_db)):
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return {"message": "資料表已更新並重置，請緊接著執行 /init_users/ 建立初始帳號。"}

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

@app.get("/api/auth/{line_id}")
def check_auth(line_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.line_id == line_id).first()
    return user if user else {"status": "unbound"}

@app.get("/api/unbound_users/")
def get_unbound(db: Session = Depends(get_db)):
    return db.query(models.User).filter(models.User.line_id.like("test_%")).all()

class BindRequest(BaseModel):
    line_id: str
    user_id: int

@app.post("/api/bind/")
def bind_user(req: BindRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if user:
        user.line_id = req.line_id
        db.commit()
        return {"status": "success", "user": user}
    return {"status": "error"}

@app.get("/api/unbind/{user_id}")
def unbind_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user.line_id = f"test_unbound_{user.id}"
        db.commit()
        return {"status": "success"}
    return {"status": "error"}

class TransactionCreate(BaseModel):
    user_id: int
    actor_id: int
    type: str
    amount: float
    note: str = ""

@app.post("/api/transaction/")
def create_transaction(transaction: TransactionCreate, db: Session = Depends(get_db)):
    actor = db.query(models.User).filter(models.User.id == transaction.actor_id).first()
    if not actor: return {"status": "error", "message": "無效的使用者"}

    if actor.role == 'child' and transaction.type in ['allowance', 'withdraw_deposit']:
        return {"status": "error", "message": "權限不足：小孩無法執行大人的動作！"}
    if actor.role == 'child' and transaction.user_id != actor.id:
        return {"status": "error", "message": "權限不足：你不能更改別人的帳戶！"}

    needs_confirm = False
    if transaction.type in ['deposit', 'withdraw_deposit', 'allowance']: 
        needs_confirm = True

    status_val = "pending" if needs_confirm else "completed"

    db_transaction = models.Transaction(
        user_id=transaction.user_id, actor_id=transaction.actor_id,
        type=transaction.type, amount=transaction.amount, note=transaction.note, status=status_val
    )
    db.add(db_transaction)
    
    target_user = db.query(models.User).filter(models.User.id == transaction.user_id).first()
    if target_user and status_val == "completed":
        if transaction.type == 'expense': target_user.personal_balance -= transaction.amount
            
    db.commit()
    msg = "已送出請求，等待對方點擊確認！" if needs_confirm else "記帳成功！"
    return {"status": "success", "message": msg}

@app.get("/api/pending/{user_id}")
def get_pending(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user: return []
    
    if user.role == 'parent':
        pending = db.query(models.Transaction, models.User.name).join(models.User, models.Transaction.user_id == models.User.id).filter(
            models.Transaction.status == 'pending', models.Transaction.type.in_(['deposit', 'withdraw_deposit'])
        ).all()
    else:
        pending = db.query(models.Transaction, models.User.name).join(models.User, models.Transaction.user_id == models.User.id).filter(
            models.Transaction.status == 'pending', models.Transaction.type == 'allowance', models.Transaction.user_id == user.id
        ).all()
        
    return [{"id": r.Transaction.id, "type": r.Transaction.type, "amount": r.Transaction.amount, "note": r.Transaction.note, "timestamp": r.Transaction.timestamp.isoformat(), "user_name": r.name} for r in pending]

@app.post("/api/confirm/{transaction_id}")
def confirm_transaction(transaction_id: int, action: str, db: Session = Depends(get_db)):
    t = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not t or t.status != 'pending': return {"status": "error"}

    if action == 'reject':
        t.status = 'rejected'
        db.commit()
        return {"status": "success"}

    target_user = db.query(models.User).filter(models.User.id == t.user_id).first()
    if target_user:
        if t.type == 'deposit':
            target_user.personal_balance -= t.amount
            target_user.deposited_balance += t.amount
        elif t.type == 'allowance':
            target_user.personal_balance += t.amount
        elif t.type == 'withdraw_deposit':
            target_user.personal_balance += t.amount
            target_user.deposited_balance -= t.amount
            
    t.status = 'completed'
    db.commit()
    return {"status": "success"}

@app.put("/api/user/{user_id}/balance")
def update_balance(user_id: int, actor_id: int, balances: BalanceUpdate, db: Session = Depends(get_db)):
    actor = db.query(models.User).filter(models.User.id == actor_id).first()
    if not actor or actor.role != 'parent': return {"status": "error", "message": "只有家長可以修改餘額！"}

    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if target_user:
        note_str = f"⚙️ 家長校正餘額：手邊 ${balances.personal_balance}, 寄放 ${balances.deposited_balance}"
        db.add(models.Transaction(user_id=user_id, actor_id=actor_id, type='adjustment', amount=0, note=note_str, status='completed'))
        target_user.personal_balance = balances.personal_balance
        target_user.deposited_balance = balances.deposited_balance
        db.commit()
        return {"status": "success"}
    return {"status": "error", "message": "找不到該使用者"}

@app.get("/api/transactions/")
def get_transactions(user_id: int = 0, skip: int = 0, start_date: str = None, end_date: str = None, db: Session = Depends(get_db)):
    query = db.query(models.Transaction, models.User.name).join(models.User, models.Transaction.user_id == models.User.id)
    if user_id > 0: query = query.filter(models.Transaction.user_id == user_id)
    
    if start_date:
        try:
            dt_start = datetime.strptime(f"{start_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
            query = query.filter(models.Transaction.timestamp >= dt_start)
        except: pass
    if end_date:
        try:
            dt_end = datetime.strptime(f"{end_date} 23:59:59", "%Y-%m-%d %H:%M:%S")
            query = query.filter(models.Transaction.timestamp <= dt_end)
        except: pass
        
    records = query.order_by(models.Transaction.timestamp.desc()).offset(skip).limit(20).all()
    return [{"id": r.Transaction.id, "type": r.Transaction.type, "amount": r.Transaction.amount, "note": r.Transaction.note, "status": r.Transaction.status, "timestamp": r.Transaction.timestamp.isoformat(), "user_name": r.name} for r in records]

@app.get("/api/stats/")
def get_stats(user_id: int, start_date: str, end_date: str, db: Session = Depends(get_db)):
    try:
        dt_start = datetime.strptime(f"{start_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.strptime(f"{end_date} 23:59:59", "%Y-%m-%d %H:%M:%S")
    except:
        return {"total_allowance": 0, "total_expense": 0, "daily": {}}
        
    query = db.query(models.Transaction).filter(
        models.Transaction.user_id == user_id, 
        models.Transaction.status == 'completed', 
        models.Transaction.timestamp >= dt_start, 
        models.Transaction.timestamp <= dt_end
    )
    transactions = query.order_by(models.Transaction.timestamp).all()
    daily_stats = {}
    total_expense, total_allowance = 0, 0
    for t in transactions:
        d = t.timestamp.strftime("%Y-%m-%d")
        if d not in daily_stats: daily_stats[d] = {"income": 0, "expense": 0}
        if t.type == 'expense': daily_stats[d]["expense"] += t.amount; total_expense += t.amount
        elif t.type in ['allowance', 'withdraw_deposit']: daily_stats[d]["income"] += t.amount; total_allowance += t.amount
    return {"total_allowance": total_allowance, "total_expense": total_expense, "daily": daily_stats}

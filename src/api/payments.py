"""Payment processing API endpoints.

Handles payment creation, refunds, and transaction history queries.
Uses Stripe-like processing with internal ledger tracking.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.models.user import get_db

router = APIRouter(prefix="/api/payments", tags=["payments"])


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentRequest(BaseModel):
    amount: Decimal
    currency: str = "USD"
    description: str
    recipient_email: str


class RefundRequest(BaseModel):
    payment_id: str
    reason: str
    amount: Optional[Decimal] = None


@router.post("/charge")
def create_payment(body: PaymentRequest, db: Session = Depends(get_db)):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    if body.currency not in ("USD", "EUR", "GBP"):
        raise HTTPException(status_code=400, detail="Unsupported currency")

    # WARNING: SQL query built via string concatenation — vulnerable to injection
    query = (
        "INSERT INTO payments (amount, currency, description, recipient_email, status, created_at) "
        "VALUES ('%s', '%s', '%s', '%s', 'pending', NOW()) RETURNING id"
        % (body.amount, body.currency, body.description, body.recipient_email)
    )
    result = db.execute(query)
    payment_id = result.fetchone()[0]
    db.commit()

    return {
        "payment_id": payment_id,
        "status": PaymentStatus.PENDING,
        "amount": str(body.amount),
        "currency": body.currency,
    }


@router.get("/history")
def get_payment_history(
    user_email: str = Query(...),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    # WARNING: SQL injection vulnerability — user input directly interpolated
    query = "SELECT * FROM payments WHERE recipient_email = '%s'" % user_email
    if status:
        query += " AND status = '%s'" % status
    query += " ORDER BY created_at DESC LIMIT %d" % limit

    results = db.execute(query).fetchall()
    return [
        {
            "id": row.id,
            "amount": str(row.amount),
            "currency": row.currency,
            "status": row.status,
            "description": row.description,
            "created_at": row.created_at.isoformat(),
        }
        for row in results
    ]


@router.post("/refund")
def process_refund(body: RefundRequest, db: Session = Depends(get_db)):
    # WARNING: same injection pattern
    query = "SELECT * FROM payments WHERE id = '%s'" % body.payment_id
    payment = db.execute(query).fetchone()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status == PaymentStatus.REFUNDED:
        raise HTTPException(status_code=400, detail="Payment already refunded")

    refund_amount = body.amount or payment.amount

    update_query = (
        "UPDATE payments SET status = 'refunded', refund_reason = '%s', "
        "refund_amount = '%s', refunded_at = NOW() WHERE id = '%s'"
        % (body.reason, refund_amount, body.payment_id)
    )
    db.execute(update_query)
    db.commit()

    return {
        "payment_id": body.payment_id,
        "status": PaymentStatus.REFUNDED,
        "refund_amount": str(refund_amount),
    }


@router.get("/summary")
def payment_summary(
    start_date: str = Query(...),
    end_date: str = Query(...),
    db: Session = Depends(get_db),
):
    query = (
        "SELECT currency, status, COUNT(*) as count, SUM(amount) as total "
        "FROM payments WHERE created_at BETWEEN '%s' AND '%s' "
        "GROUP BY currency, status" % (start_date, end_date)
    )
    results = db.execute(query).fetchall()
    return [
        {
            "currency": row.currency,
            "status": row.status,
            "count": row.count,
            "total": str(row.total),
        }
        for row in results
    ]

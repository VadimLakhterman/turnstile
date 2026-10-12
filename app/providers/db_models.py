import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    origin_url: Mapped[str] = mapped_column(String(2048))
    price_per_request: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    pending_balance: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    total_earned: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    payout_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payout_method: Mapped[str] = mapped_column(String(50), default="bank_transfer")
    payout_frequency: Mapped[str] = mapped_column(String(20), default="monthly")
    api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TransactionLedger(Base):
    __tablename__ = "transaction_ledger"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tx_hash: Mapped[str] = mapped_column(String(66), unique=True, index=True)
    amount_usdc: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id"))
    payout_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("payouts.id"), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payout(Base):
    __tablename__ = "payouts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id"))
    amount_usdc: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    amount_fiat: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

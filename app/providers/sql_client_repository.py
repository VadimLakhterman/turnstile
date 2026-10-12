from decimal import Decimal
from uuid import UUID

from sqlalchemy import exists, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.errors import LedgerWriteError, TransactionAlreadyUsedError
from app.domain.models import GatewayClient
from app.providers.db_models import Client, TransactionLedger


class SqlClientRepository:
    """ClientRepository backed by SQLAlchemy (PostgreSQL in production, SQLite in tests)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_active_client(self, client_id: UUID) -> GatewayClient | None:
        async with self._session_factory() as session:
            result = await session.execute(select(Client).where(Client.id == client_id, Client.is_active.is_(True)))
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return GatewayClient(id=row.id, origin_url=row.origin_url, price_per_request=Decimal(str(row.price_per_request)))

    async def is_transaction_used(self, tx_hash: str) -> bool:
        async with self._session_factory() as session:
            used = await session.scalar(select(exists().where(TransactionLedger.tx_hash == tx_hash)))
        return bool(used)

    async def record_payment(self, client_id: UUID, tx_hash: str, amount: Decimal) -> None:
        try:
            async with self._session_factory() as session, session.begin():
                session.add(TransactionLedger(tx_hash=tx_hash, amount_usdc=amount, client_id=client_id))
                # Atomic increment — safe under concurrent payments for the same client.
                await session.execute(
                    update(Client)
                    .where(Client.id == client_id)
                    .values(
                        pending_balance=Client.pending_balance + amount,
                        total_earned=Client.total_earned + amount,
                    )
                )
        except IntegrityError as exc:
            if await self.is_transaction_used(tx_hash):
                raise TransactionAlreadyUsedError(tx_hash) from exc
            raise LedgerWriteError(f"Failed to record payment tx_hash={tx_hash}") from exc
        except SQLAlchemyError as exc:
            raise LedgerWriteError(f"Failed to record payment tx_hash={tx_hash}") from exc

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.errors import LedgerWriteError, TransactionAlreadyUsedError
from app.providers.db_models import Client, TransactionLedger
from app.providers.sql_client_repository import SqlClientRepository
from tests.conftest import CLIENT_ID, INACTIVE_CLIENT_ID, ORIGIN_URL, TX_HASH


async def test_get_active_client_maps_to_domain(client_repository: SqlClientRepository) -> None:
    client = await client_repository.get_active_client(CLIENT_ID)
    assert client is not None
    assert client.id == CLIENT_ID
    assert client.origin_url == ORIGIN_URL
    assert client.price_per_request == Decimal("0.01")


async def test_get_active_client_ignores_inactive_and_unknown(client_repository: SqlClientRepository) -> None:
    assert await client_repository.get_active_client(INACTIVE_CLIENT_ID) is None
    assert await client_repository.get_active_client(uuid4()) is None


async def test_record_payment_writes_ledger_and_credits_client(
    client_repository: SqlClientRepository, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await client_repository.record_payment(CLIENT_ID, TX_HASH, Decimal("0.01"))
    await client_repository.record_payment(CLIENT_ID, "0x" + "ef" * 32, Decimal("0.02"))

    assert await client_repository.is_transaction_used(TX_HASH)
    async with session_factory() as session:
        client = await session.get(Client, CLIENT_ID)
        ledger = (await session.scalars(select(TransactionLedger).where(TransactionLedger.tx_hash == TX_HASH))).one()
    assert client is not None
    assert Decimal(str(client.pending_balance)) == Decimal("0.03")
    assert Decimal(str(client.total_earned)) == Decimal("0.03")
    assert ledger.client_id == CLIENT_ID
    assert Decimal(str(ledger.amount_usdc)) == Decimal("0.01")


async def test_record_payment_duplicate_raises_already_used(client_repository: SqlClientRepository) -> None:
    """Regression: a concurrent duplicate that slips past the pre-check must map to 409, not 500."""
    await client_repository.record_payment(CLIENT_ID, TX_HASH, Decimal("0.01"))
    with pytest.raises(TransactionAlreadyUsedError):
        await client_repository.record_payment(CLIENT_ID, TX_HASH, Decimal("0.01"))


async def test_record_payment_db_failure_raises_ledger_error(client_repository: SqlClientRepository) -> None:
    with patch.object(AsyncSession, "execute", side_effect=OperationalError("UPDATE", {}, Exception("down"))):
        with pytest.raises(LedgerWriteError) as exc_info:
            await client_repository.record_payment(CLIENT_ID, TX_HASH, Decimal("0.01"))
    assert isinstance(exc_info.value.__cause__, OperationalError)

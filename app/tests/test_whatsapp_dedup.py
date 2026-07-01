"""Phase 3A: DB-backed inbound WhatsApp message deduplication (CRUD layer)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.crud import whatsapp as c
from app.models.whatsapp import WhatsAppInboundEvent


async def test_first_claim_succeeds(db_session):
    assert await c.claim_inbound_event(db_session, "m1", "u1", 900) is True


async def test_duplicate_fresh_processing_is_skipped(db_session):
    assert await c.claim_inbound_event(db_session, "m1", "u1", 900) is True
    # Same message, still 'processing' and fresh -> skip.
    assert await c.claim_inbound_event(db_session, "m1", "u1", 900) is False


async def test_processed_message_is_skipped(db_session):
    await c.claim_inbound_event(db_session, "m1", "u1", 900)
    await c.finalize_inbound_event(db_session, "m1", success=True)
    assert await c.claim_inbound_event(db_session, "m1", "u1", 900) is False


async def test_failed_message_can_be_reclaimed(db_session):
    await c.claim_inbound_event(db_session, "m1", "u1", 900)
    await c.finalize_inbound_event(db_session, "m1", success=False, error="boom")
    assert await c.claim_inbound_event(db_session, "m1", "u1", 900) is True
    # attempts incremented on reclaim.
    row = (
        (
            await db_session.execute(
                select(WhatsAppInboundEvent).where(
                    WhatsAppInboundEvent.message_id == "m1"
                )
            )
        )
        .scalars()
        .first()
    )
    assert row.attempts == 2
    assert row.status == "processing"
    assert row.last_error is None


async def test_stale_processing_can_be_reclaimed(db_session):
    await c.claim_inbound_event(db_session, "m1", "u1", 900)
    # stale_seconds=0 makes any existing 'processing' row reclaimable.
    assert await c.claim_inbound_event(db_session, "m1", "u1", 0) is True


async def test_marked_processed_only_after_success(db_session):
    await c.claim_inbound_event(db_session, "m1", "u1", 900)
    row = (
        (
            await db_session.execute(
                select(WhatsAppInboundEvent).where(
                    WhatsAppInboundEvent.message_id == "m1"
                )
            )
        )
        .scalars()
        .first()
    )
    assert row.status == "processing"  # not yet processed
    await c.finalize_inbound_event(db_session, "m1", success=True)
    await db_session.refresh(row)
    assert row.status == "processed"


async def test_marked_failed_after_error(db_session):
    await c.claim_inbound_event(db_session, "m1", "u1", 900)
    await c.finalize_inbound_event(db_session, "m1", success=False, error="kaboom")
    row = (
        (
            await db_session.execute(
                select(WhatsAppInboundEvent).where(
                    WhatsAppInboundEvent.message_id == "m1"
                )
            )
        )
        .scalars()
        .first()
    )
    assert row.status == "failed"
    assert row.last_error == "kaboom"


async def test_two_instances_race_only_one_wins(db_session):
    """Simulate a Meta redelivery: same id claimed twice; second is skipped."""
    first = await c.claim_inbound_event(db_session, "m-race", "u1", 900)
    second = await c.claim_inbound_event(db_session, "m-race", "u1", 900)
    assert first is True
    assert second is False


async def test_fresh_processing_not_reclaimed_with_large_window(db_session):
    await c.claim_inbound_event(db_session, "m1", "u1", 900)
    # Row is fresh; with a 900s window it must NOT be reclaimed.
    assert await c.claim_inbound_event(db_session, "m1", "u1", 900) is False


async def test_is_stale_helper_tz_aware_and_naive():
    old_aware = datetime.now(timezone.utc) - timedelta(seconds=1000)
    old_naive = datetime.utcnow() - timedelta(seconds=1000)
    fresh_aware = datetime.now(timezone.utc)
    assert c._is_stale(old_aware, 900) is True
    assert c._is_stale(old_naive, 900) is True
    assert c._is_stale(fresh_aware, 900) is False
    assert c._is_stale(None, 900) is True

from sqlalchemy import func, select

from app.db.models.faq import Faqs


async def _faq_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(Faqs))


async def _insert_faq(session) -> None:
    session.add(Faqs(question="Is RailMind well tested?", answer="Getting there."))
    await session.flush()


async def test_isolation_round_one(db_session):
    assert await _faq_count(db_session) == 0
    await _insert_faq(db_session)
    assert await _faq_count(db_session) == 1


async def test_isolation_round_two(db_session):
    assert await _faq_count(db_session) == 0
    await _insert_faq(db_session)
    assert await _faq_count(db_session) == 1

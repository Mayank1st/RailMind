import asyncio


def test_pytest_works():
    assert 1 + 1 == 2


async def test_async_works():
    await asyncio.sleep(0.01)
    assert True

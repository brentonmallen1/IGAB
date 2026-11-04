"""The app's own engine opens connections with JIT off (`db/session.py`).

Read back from a real connection, not from the engine's arguments: what
matters is what Postgres does with the statement, and a setting that never
reached the server would pass any test of the Python side. With JIT on, the
pending-review count spent 1.5 s of 1.6 s compiling expressions.
"""

from sqlalchemy import text

from igab.db.session import engine


async def test_the_app_engine_runs_with_jit_off():
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(text("SHOW jit"))).scalar_one() == "off"
    finally:
        # The pool belongs to this test's event loop; leave nothing in it.
        await engine.dispose()

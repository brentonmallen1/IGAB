"""The migration chain has exactly one head.

Two branches that each add a migration off the same parent merge cleanly in
git and leave alembic with two heads: `alembic upgrade head` then refuses to
run, and the API image's CMD runs exactly that before it starts. Nothing else
in the suite notices — the integration tests build their schema from the
models — so the fork surfaces on deploy. This reads the scripts only and needs
no database.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND = Path(__file__).resolve().parents[2]


def test_the_migration_chain_has_one_head():
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, (
        f"alembic has {len(heads)} heads ({', '.join(sorted(heads))}): two branches added a "
        "migration off the same parent. Point the newer one's down_revision at the other."
    )

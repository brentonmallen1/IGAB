"""The client and the server must agree about how large an upload may be.

Irreducible duplication, in the sense CLAUDE.md means: the browser has to
refuse a 40MB file *before* sending it, and the API has to refuse it whatever
the browser did. Neither check can be deleted in favour of the other.

So: one constant per side, and this. What it replaces is worse than two
copies — `20 * 1024 * 1024` was written inline in four components, and the
string "20MB" appeared six times across both languages, including a hint that
promised it to the user in prose. The first sign of drift would have been an
upload the client accepted and the API rejected, with a message quoting a
limit that was no longer the limit.

Follows `test_account_type_mirror.py`: a parser rather than codegen, because
both files are hand-edited and human-read.
"""

import re
from pathlib import Path

import pytest

from igab.api.v1.attachments import MAX_FILE_MB, MAX_FILE_SIZE, TOO_LARGE_DETAIL

MIRROR = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "attachments.ts"

#: The api container mounts only `backend/`, so `just test-backend` cannot see
#: the client. `just ci` — and GitHub CI, which gates merges — runs from the
#: repo root and does.
needs_frontend_tree = pytest.mark.skipif(
    not MIRROR.exists(), reason="frontend tree not mounted (Docker); enforced by `just ci`"
)


def _client_megabytes() -> int:
    source = MIRROR.read_text()
    match = re.search(r"const MAX_ATTACHMENT_MB\s*=\s*(\d+)", source)
    assert match, f"MAX_ATTACHMENT_MB not found in {MIRROR}"
    return int(match.group(1))


@needs_frontend_tree
def test_the_client_pre_check_matches_the_limit_the_server_enforces():
    assert _client_megabytes() == MAX_FILE_MB, (
        "the upload ceiling has drifted between the two sides.\n"
        f"  server: {MAX_FILE_MB}MB ({MAX_FILE_SIZE} bytes), api/v1/attachments.py\n"
        f"  client: {_client_megabytes()}MB, frontend/src/api/attachments.ts"
    )


@needs_frontend_tree
def test_the_client_derives_its_bytes_and_its_label_from_that_one_number():
    """Both sides must keep deriving, not re-typing. A literal
    `20 * 1024 * 1024` or a hard-coded "20MB" reintroduces exactly the copy
    this pair of constants removed."""
    source = MIRROR.read_text()
    assert "MAX_ATTACHMENT_MB * 1024 * 1024" in source
    assert "`${MAX_ATTACHMENT_MB}MB`" in source


def test_the_servers_refusal_quotes_its_own_limit():
    assert TOO_LARGE_DETAIL == f"File too large (max {MAX_FILE_MB}MB)"
    assert MAX_FILE_SIZE == MAX_FILE_MB * 1024 * 1024


@needs_frontend_tree
def test_no_component_still_spells_the_limit_itself():
    """The copies this consolidated. Counting them is the point: the fourth
    was in `AttachmentPanel`, found only because the others were counted
    first."""
    components = (MIRROR.parents[1] / "components").rglob("*.tsx")
    offenders = [
        f"{path.name}:{n}"
        for path in components
        for n, line in enumerate(path.read_text().split("\n"), 1)
        if re.search(r"\b20\s*\*\s*1024\s*\*\s*1024\b", line) or "max 20MB" in line
    ]
    assert not offenders, f"the upload limit is spelled again in: {offenders}"

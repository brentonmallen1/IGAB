"""The system tags the backend seeds, against the list both suites share.

`shared/system_tags.json` is the frontend help's list too
(SystemTagsHelp.test.tsx), so a tag added here and not explained there — or
the reverse — fails one side. The help once pinned a hand-copied list with a
comment pointing here, and the `cost_of_living` tag shipped unexplained while
that test stayed green.
"""

import json
from pathlib import Path

from igab.repositories.tag_repo import SYSTEM_TAGS

_SHARED = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "system_tags.json").read_text()
)


def test_the_seeded_tags_are_the_shared_list_in_order():
    assert [key for key, _name, _color in SYSTEM_TAGS] == _SHARED["keys"]

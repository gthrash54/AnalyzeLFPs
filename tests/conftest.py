"""Shared pytest configuration.

The `realdata` marker guards tests that read real intraoperative recordings from
`data/`. That directory is git-ignored and empty on a fresh checkout, so those
tests are skipped automatically rather than failing. Nothing here reads a
recording; it only decides whether the recordings are present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"


# Bookkeeping entries that do not count as "there is data here".
_IGNORED_NAMES = {".gitkeep", ".DS_Store", ".gitignore", "Icon\r"}


def _data_dir_is_populated(data_dir: Path = DATA_DIR) -> bool:
    """Return True when `data/` exists and has at least one real entry.

    Deliberately a DEPTH-ONE scan that stops at the first hit. `data/` is a
    symlink to cloud-synced storage (Box) holding hundreds of subject folders
    whose contents stream on demand, so a recursive walk here would take minutes
    and pull files down from the network every time pytest starts. A directory
    counts as data; we do not look inside it.
    """
    # iterdir() is lazy: the underlying os.listdir() does not run until the
    # generator is first advanced, so the consuming any() has to sit inside the
    # try too. any() still short-circuits, so this stops at the first real entry
    # rather than enumerating hundreds of cloud-synced subject folders.
    try:
        return any(entry.name not in _IGNORED_NAMES for entry in data_dir.iterdir())
    except (OSError, ValueError):  # missing, dangling symlink, or not a directory
        return False


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """Path to the raw recordings directory, for `realdata` tests."""
    return DATA_DIR


REALDATA_DIR = Path(__file__).resolve().parent / "realdata"


def _needs_real_recordings(item: pytest.Item) -> bool:
    """Return True when an item is `realdata`, by marker or by location.

    Both are checked explicitly. Relying on `"realdata" in item.keywords` alone
    would also match on the directory name, which happens to give the right
    answer here but for the wrong reason.
    """
    if item.get_closest_marker("realdata") is not None:
        return True
    return REALDATA_DIR in Path(item.path).parents


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip every `realdata` test when `data/` is empty or missing."""
    if _data_dir_is_populated():
        return
    skip_realdata = pytest.mark.skip(
        reason="no recordings in data/; realdata tests need real BrainVision exports"
    )
    for item in items:
        if _needs_real_recordings(item):
            item.add_marker(skip_realdata)

"""Stream and channel names to roles, from `DeriveConfig.roles` and nothing else.

A role (`lfp`, `emg`, `mic`, `micro`, `monitor`) is what decides the product a
stream lands in and the rate it is written at. Two naming worlds feed it. A TDT
tank names each stream with a four-character store code (`ecos`, `MonA`), which
is looked up exactly and case-sensitively in `roles.streams`. A BrainVision
recording surfaces one stream whose channels carry the meaning (`ecog_a1`,
`fdi_contra`, `NotConnected`), so each channel name is tested against the
regular expressions in `roles.channel_patterns` with `re.search`, ignoring case.

Two rules keep the mapping honest. The `ignore` pattern list wins over every
role, so a channel the rig reports but nobody wired never becomes an LFP
product. And a name that matches two roles is an error, not a first-match: the
config is wrong and a person fixes it, because a guessed role would silently
put a microphone in the LFP file. Unmapped names raise `Quarantine` with the
complete list, so one triage pass sees every gap in the config instead of the
first one.

Names in a `Quarantine.detail` are written with `repr`, so `'ao_1', 'ao_2'`.
BrainVision allows a comma inside a channel name and an empty name is legal
too; quoting keeps both readable in a ledger row and lets a reader split the
list back into names.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from dbsspeech.derive.config import ROLES, DeriveConfig
from dbsspeech.derive.model import Quarantine

# The `channel_patterns` key that removes a channel from every product.
IGNORE: Final = "ignore"

_UNMAPPED_STREAM: Final = "unmapped_stream"
_UNMAPPED_CHANNEL: Final = "unmapped_channel"
_AMBIGUOUS_CHANNEL: Final = "ambiguous_channel"

# Separator between quoted names in a `Quarantine.detail`.
_DETAIL_SEP: Final = ", "


def classify_stream(name: str, cfg: DeriveConfig) -> str:
    """Role of a TDT store name, by exact case-sensitive lookup in `roles.streams`.

    Returns the role. A name absent from the table raises `Quarantine`
    (`reason="unmapped_stream"`, `detail=repr(name)`) when `roles.on_unmapped`
    is `quarantine`, and returns `""` when it is `skip`, which the caller
    treats as "write nothing for this stream".
    """
    role = cfg.roles.streams.get(name)
    if role is not None:
        return role
    if cfg.roles.on_unmapped == "quarantine":
        raise Quarantine(_UNMAPPED_STREAM, repr(name))
    return ""


def _compiled(cfg: DeriveConfig) -> dict[str, list[re.Pattern[str]]]:
    """Compile `roles.channel_patterns` once per call with `re.compile`, IGNORECASE."""
    return {
        key: [re.compile(p, re.IGNORECASE) for p in patterns]
        for key, patterns in cfg.roles.channel_patterns.items()
    }


def _matching_roles(name: str, compiled: dict[str, list[re.Pattern[str]]]) -> list[str]:
    """Every role whose pattern list has a `re.search` hit on `name`, in ROLES order.

    Two patterns of the same role hitting one name count once: the role is
    unambiguous, the config merely says it twice.
    """
    return [
        role
        for role in ROLES
        if any(p.search(name) for p in compiled.get(role, ()))
    ]


def _is_ignored(name: str, compiled: dict[str, list[re.Pattern[str]]]) -> bool:
    return any(p.search(name) for p in compiled.get(IGNORE, ()))


def _detail(items: Sequence[str]) -> str:
    """Join already-formatted items, first occurrence order, duplicates dropped."""
    return _DETAIL_SEP.join(dict.fromkeys(items))


def _require_sequence_of_names(names: object) -> None:
    """A bare `str` is a `Sequence[str]` of its characters; refuse it loudly.

    Passing one channel name where a list was meant would otherwise classify
    each letter, and under `on_unmapped: skip` drop every channel silently.
    """
    if isinstance(names, str | bytes):
        raise TypeError("names must be a sequence of channel names, not a single str")


def classify_channels(names: Sequence[str], cfg: DeriveConfig) -> list[str]:
    """One role per channel name, from `roles.channel_patterns`.

    Each name is matched with `re.search` against every pattern of every role,
    case-insensitively. The `ignore` list is checked first and yields `""` for
    that channel regardless of what else would match, including a name two
    roles would otherwise fight over. A name matching more than one role
    raises `Quarantine` (`reason="ambiguous_channel"`) naming every such
    channel and the roles it hit, as `'name' -> role/role`; this is checked
    before unmapped names because it means the config itself is wrong. Names
    matching no role raise `Quarantine` (`reason="unmapped_channel"`) with
    EVERY unmapped name in `detail`, each written with `repr`, in input order
    and without repeats, when `roles.on_unmapped` is `quarantine`; when it is
    `skip` those channels get `""`.

    `names` must be a real sequence; a bare `str` raises `TypeError` rather
    than being iterated character by character.
    """
    _require_sequence_of_names(names)
    compiled = _compiled(cfg)
    roles: list[str] = []
    ambiguous: list[str] = []
    unmapped: list[str] = []
    for name in names:
        if _is_ignored(name, compiled):
            roles.append("")
            continue
        hits = _matching_roles(name, compiled)
        if len(hits) > 1:
            ambiguous.append(f"{name!r} -> {'/'.join(hits)}")
            roles.append("")
        elif len(hits) == 1:
            roles.append(hits[0])
        else:
            unmapped.append(repr(name))
            roles.append("")
    if ambiguous:
        raise Quarantine(_AMBIGUOUS_CHANNEL, _detail(ambiguous))
    if unmapped and cfg.roles.on_unmapped == "quarantine":
        raise Quarantine(_UNMAPPED_CHANNEL, _detail(unmapped))
    return roles


def group_by_role(names: Sequence[str], cfg: DeriveConfig) -> dict[str, list[int]]:
    """Channel indices per role, for splitting one stream into per-role products.

    Wraps `classify_channels`, so it raises the same `Quarantine` cases and
    the same `TypeError` for a bare `str`. Ignored and skipped channels (role
    `""`) appear in no group. Keys are in `ROLES` order and only roles with at
    least one channel are present; indices within a role are ascending, so
    channel order in the source is preserved in every product.
    """
    roles = classify_channels(names, cfg)
    out: dict[str, list[int]] = {}
    for role in ROLES:
        idx = [i for i, r in enumerate(roles) if r == role]
        if idx:
            out[role] = idx
    return out

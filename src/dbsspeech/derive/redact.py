"""The scrubber every string passes through on its way out of the build.

Log lines, ledger rows, stdout, and the message of any exception that might be
logged all go through `Scrubber.scrub` first. The rules are applied in order
and each one is cheap, so the cost of scrubbing everything is negligible next
to the cost of a single leaked path.

1. Every configured regex (`DeriveConfig.privacy.redact_patterns`) becomes
   `<redacted>`.
2. Any absolute path under a forbidden root becomes `<path>`. The staging
   archive is the usual root; its folder names carry acquisition dates.
3. Any path that goes through a segment containing `Box` (the rclone remote
   name and the FUSE mount point) becomes `<box>` from that segment on. This
   catches both `/home/user/Box/...` and rclone-style `Box:Lab Raw Data/...`.
4. A TDT tank stem, a subject label (usually the study ID) followed by two
   six-digit groups, is redacted even when the configured patterns miss it.
   This is a hard-coded floor: the first group is the acquisition date.
5. A filename date stamp of the shape `date_YYYYMMDD` (optionally followed by
   `time_HHMM`), which is how the BrainVision stimulus exports in this archive
   are named, is redacted for the same reason. Also part of the floor.

Rules 2 and 3 run after rule 1, so a path may already contain `<redacted>`
where a dated folder or a tank stem used to be. The path tail therefore treats
`<redacted>` as part of the path, and a forbidden or Box path always collapses
to a single token no matter what its segments held.

Study IDs on their own (`ug0002`, `uh0001`) are the sanctioned identifier and
survive. Block names (`increment1_depth1_DNU`) survive.

All matching is done with `re.compile` and `Pattern.sub` from the standard library.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable, Sequence
from pathlib import Path

from dbsspeech.derive.config import DeriveConfig

REDACTED = "<redacted>"
PATH_TOKEN = "<path>"
BOX_TOKEN = "<box>"
TOKENS: tuple[str, ...] = (REDACTED, PATH_TOKEN, BOX_TOKEN)

# The message used when an exception cannot even be turned into a string.
UNPRINTABLE = "<unprintable>"

# Rule names, in the order the rules run. `assert_clean` reports one of these.
RULE_PATTERN = "pattern"
RULE_FORBIDDEN_ROOT = "forbidden_root"
RULE_BOX = "box"
RULE_TANK_STEM = "tank_stem"
RULE_FILENAME_DATE = "filename_date"

# The tail of a path once its start has been recognized. Archive paths contain
# single spaces ("stage1 surgery") and parentheses, so neither ends the path; a
# run of two spaces, a colon followed by a space, a quote, a semicolon, a pipe,
# an angle bracket, or a newline does. The one angle-bracketed thing allowed
# inside the tail is the `<redacted>` token that rule 1 may already have put
# there. Over-consuming into prose is the safe direction: what follows a path
# in a log line is rarely worth more than what a path can leak.
_PATH_TAIL = r"(?:(?!  |: )(?:" + re.escape(REDACTED) + r"|[^\n\r\"'<>|;]))*"

# TDT names every tank `<subject>-<YYMMDD>-<HHMMSS>`, and the subject field is
# whatever the operator typed: a study ID in the usual case, but the archive
# also holds tanks whose subject is a test label. The floor therefore keys on
# the shape, a word then two six-digit groups joined by a hyphen, underscore,
# or space, rather than on the study ID. Not followed by another digit, so a
# longer numeric run is not split in the middle.
_TANK_STEM = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9]*[-_ ]\d{6}[-_ ]\d{6}(?!\d)")

# The BrainVision stimulus exports: `..._date_YYYYMMDD time_HHMM ...`. The time
# is swallowed with the date when present so the stamp goes as one token.
_FILENAME_DATE = re.compile(
    r"(?i)(?<![A-Za-z0-9])date[-_ ]\d{8}(?:[-_ ]time[-_ ]\d{4})?(?![A-Za-z0-9])"
)

# Rule 3, two shapes.
#   (a) rclone remote: `Box:` immediately followed by the remote path.
#   (b) mount point or any folder named with Box: a path separator, then a
#       segment (no separators inside) containing `Box`, then the rest of the
#       path. `Box/` at the start of a token counts too.
# Case-sensitive on purpose: the remote and the mount point are spelled `Box`,
# and the prose word "box" (a box of contacts) is not a path. The prose word
# "Box" with no separator on either side is left alone too.
_BOX_REMOTE = re.compile(r"(?<![A-Za-z0-9])Box:(?=\S)" + _PATH_TAIL)
_BOX_SEGMENT = re.compile(
    r"(?:[/\\][^/\\\n\r\"'<>|;]*?Box[^/\\\n\r\"'<>|;]*|(?<![A-Za-z0-9])Box(?=[/\\]))" + _PATH_TAIL
)


def _root_variants(root: Path) -> list[str]:
    """Every spelling of an absolute root a log line might carry.

    The path as written, with `~` expanded, fully resolved (symlinks followed,
    via `Path.resolve`), and re-abbreviated with `~` when it lies under the
    home directory. Trailing separators are dropped so `root/` and `root`
    match the same way.

    A relative root is refused with `ValueError`: its bare spelling would match
    ordinary prose (`staging` in "staging is done", `.` in any sentence), and
    where it is relative to is not something a scrubber can know.
    """
    expanded = root.expanduser()
    if not expanded.is_absolute():
        raise ValueError(
            f"forbidden path root must be absolute, got a relative path of length {len(str(root))}"
        )
    spellings: list[str] = [str(root), str(expanded)]
    with contextlib.suppress(OSError):
        spellings.append(str(expanded.resolve()))
    home = Path.home()
    for candidate in (expanded, Path(spellings[-1])):
        try:
            rel = candidate.relative_to(home)
        except ValueError:
            continue
        spellings.append("~/" + rel.as_posix() if str(rel) != "." else "~")
    seen: set[str] = set()
    out: list[str] = []
    for s in spellings:
        s = s.rstrip("/\\") or s
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    # Longest first so a root nested inside another is matched whole.
    return sorted(out, key=len, reverse=True)


def _compile_root_rule(roots: Sequence[Path]) -> re.Pattern[str] | None:
    """One regex for rule 2: any spelling of any forbidden root, then the path tail."""
    spellings = [s for root in roots for s in _root_variants(root)]
    if not spellings:
        return None
    alternatives = "|".join(re.escape(s) for s in spellings)
    # The root must end at a separator, a terminator, or the end of the text,
    # so "DBS Data" does not also claim "DBS Data2".
    return re.compile(r"(?:" + alternatives + r")(?![A-Za-z0-9_.-])" + _PATH_TAIL)


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile one configured pattern and refuse the ones that break the contract.

    A pattern that matches the empty string would insert `<redacted>` between
    every character and grow on every pass; a pattern that matches inside one
    of the tokens would make `scrub` non-idempotent and `assert_clean` refuse
    its own output. Both are configuration mistakes, so they fail at
    construction rather than at the first ledger write.
    """
    compiled = re.compile(pattern)
    if compiled.fullmatch("") is not None:
        raise ValueError(f"redact pattern {pattern!r} matches the empty string")
    for token in TOKENS:
        if compiled.search(token) is not None:
            raise ValueError(f"redact pattern {pattern!r} matches the token {token}")
    return compiled


class Scrubber:
    """Applies the redaction rules, in order, to any outgoing string.

    Parameters
    ----------
    patterns
        Regular expressions, as written in `configs/derive.yaml`, each replaced
        with `<redacted>`. Compiled once with `re.compile`; inline flags such
        as `(?i)` are honored. A pattern that can match the empty string or
        one of the output tokens is refused with `ValueError`.
    forbidden_path_roots
        Absolute directories whose contents may never be named. Any path under
        one of them, in any of its spellings, becomes `<path>`. A relative root
        is refused with `ValueError`.
    """

    def __init__(
        self,
        patterns: Sequence[str],
        forbidden_path_roots: Sequence[Path] = (),
    ) -> None:
        self._patterns: tuple[re.Pattern[str], ...] = tuple(_compile_pattern(p) for p in patterns)
        self._roots: tuple[Path, ...] = tuple(Path(r) for r in forbidden_path_roots)
        self._root_rule = _compile_root_rule(self._roots)

    @property
    def forbidden_path_roots(self) -> tuple[Path, ...]:
        """The roots rule 2 forbids, as given."""
        return self._roots

    # ---- the rules, one method each so `violations` can name them ------------

    def _apply_patterns(self, text: str) -> str:
        for pat in self._patterns:
            text = pat.sub(REDACTED, text)
        return text

    def _apply_roots(self, text: str) -> str:
        if self._root_rule is None:
            return text
        return self._root_rule.sub(PATH_TOKEN, text)

    @staticmethod
    def _apply_box(text: str) -> str:
        text = _BOX_REMOTE.sub(BOX_TOKEN, text)
        return _BOX_SEGMENT.sub(BOX_TOKEN, text)

    @staticmethod
    def _apply_tank_stem(text: str) -> str:
        return _TANK_STEM.sub(REDACTED, text)

    @staticmethod
    def _apply_filename_date(text: str) -> str:
        return _FILENAME_DATE.sub(REDACTED, text)

    def _rules(self) -> tuple[tuple[str, Callable[[str], str]], ...]:
        return (
            (RULE_PATTERN, self._apply_patterns),
            (RULE_FORBIDDEN_ROOT, self._apply_roots),
            (RULE_BOX, self._apply_box),
            (RULE_TANK_STEM, self._apply_tank_stem),
            (RULE_FILENAME_DATE, self._apply_filename_date),
        )

    # ---- public API -------------------------------------------------------------

    def scrub(self, text: str) -> str:
        """Return `text` with every rule applied, in order. Idempotent."""
        for _, rule in self._rules():
            text = rule(text)
        return text

    def violations(self, text: str) -> tuple[str, ...]:
        """Names of the rules that would change `text`, in the order they run."""
        fired: list[str] = []
        for name, rule in self._rules():
            scrubbed = rule(text)
            if scrubbed != text:
                fired.append(name)
                text = scrubbed
        return tuple(fired)

    def is_clean(self, text: str) -> bool:
        """True when no rule would change `text`."""
        return self.scrub(text) == text

    def assert_clean(self, text: str) -> str:
        """Return `text` unchanged, or raise `ValueError` naming the rule that fired.

        The exception message carries the length of the offending text and the
        rule names only, never the text itself, because the exception is exactly
        the kind of thing that ends up in a log.
        """
        fired = self.violations(text)
        if fired:
            raise ValueError(
                f"text of length {len(text)} is not clean; rule(s) fired: {', '.join(fired)}"
            )
        return text


def scrubber_from_config(cfg: DeriveConfig, extra_roots: Sequence[Path]) -> Scrubber:
    """Build the scrubber the derive pipeline uses.

    Patterns come from `cfg.privacy.redact_patterns`. `DeriveConfig` does not
    name the staging archive, so the driver passes it (and any other directory
    whose contents must never be named) through `extra_roots`. At least one
    root is required: a pipeline scrubber with rule 2 switched off would let
    every staging path through, and that failure would be silent.
    """
    roots = tuple(extra_roots)
    if not roots:
        raise ValueError(
            "scrubber_from_config needs the staging root (and any other forbidden "
            "directory) in extra_roots; a pipeline scrubber that forbids no path is a leak"
        )
    return Scrubber(cfg.privacy.redact_patterns, roots)


def _exception_message(exc: BaseException, seen: set[int]) -> str:
    """`str(exc)`, made safe and made whole.

    `str` on a broken `__str__` becomes `<unprintable>` rather than a second
    exception inside the failure-recording path. An `ExceptionGroup` lists its
    members after its own message, and a chained `__cause__` is appended, so
    the ledger holds the reason and not just the wrapper. `seen` stops a cycle.
    """
    if id(exc) in seen:
        return "<cycle>"
    seen.add(id(exc))
    try:
        message = str(exc)
    except Exception:
        message = UNPRINTABLE
    # Members and causes are joined with "; ", which also ends a path tail, so
    # a path in one message cannot run into the next.
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            message = f"{message}; member {type(sub).__name__}: {_exception_message(sub, seen)}"
    cause = exc.__cause__
    if cause is not None:
        message = f"{message}; caused by {type(cause).__name__}: {_exception_message(cause, seen)}"
    return message


def redact_exception(exc: BaseException, scrubber: Scrubber) -> tuple[str, str]:
    """`(error_class_name, scrubbed_message)` for recording a failure in the ledger.

    The class name is `type(exc).__name__`; the message is `str(exc)` after
    `scrubber.scrub`, with the members of an `ExceptionGroup` and any explicit
    `__cause__` chain folded in and scrubbed the same way. Tracebacks are never
    used, so frames and file paths never travel. Never raises on account of
    the exception itself.
    """
    return type(exc).__name__, scrubber.scrub(_exception_message(exc, set()))

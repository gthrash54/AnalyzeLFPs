#!/usr/bin/env bash
# Back up everything that is not regenerable.
#
#   scripts/backup.sh /path/to/backups
#
# What is in here and why:
#   runs/         the run records. The provenance of every result. Text, small,
#                 and the one thing that cannot be recomputed from raw data.
#   derivatives/  results, figures, QC decisions, and the run index.
#   var/          accounts, sessions, and config history. Losing this is not
#                 "re-run the pipeline", it is every past decision's attribution
#                 pointing at nothing.
#   configs/      thresholds and bands as they are now, including edits made
#                 from the config admin screen.
#   manifest/     the data contract.
#
# What is deliberately not in here: data/. The recordings are large, read-only,
# and backed up where they live. A backup that takes an hour is a backup nobody
# runs.
#
# Restore is documented in docs/deploy.md. A backup nobody has restored once is
# a hypothesis.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-${DBSSPEECH_BACKUP_DIR:-}}"
KEEP="${DBSSPEECH_BACKUP_KEEP:-30}"

if [[ -z "$DEST" ]]; then
    echo "usage: $0 <destination directory>" >&2
    echo "   or: DBSSPEECH_BACKUP_DIR=/path $0" >&2
    exit 2
fi

mkdir -p "$DEST"
STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="$DEST/dbsspeech_$STAMP.tar.gz"

# The databases are copied through sqlite3 rather than tar'd in place. A plain
# copy of a database being written to is a corrupt database, and this runs from
# cron while a worker may be finishing a run.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SNAPSHOTS=()

copy_db() {
    local src="$1" relpath="$2"
    [[ -f "$src" ]] || return 0
    mkdir -p "$TMP/$(dirname "$relpath")"
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$src" ".backup '$TMP/$relpath'"
    else
        # No sqlite3 on the host. Copy it, and say so: the copy is usable in
        # almost every case and is not guaranteed to be.
        echo "warning: sqlite3 not found; copying $relpath without a consistent snapshot" >&2
        cp "$src" "$TMP/$relpath"
    fi
    SNAPSHOTS+=("$relpath")
}

# Same relative paths as in the tree, so restoring is one untar with no moving
# files around afterwards.
copy_db "$ROOT/var/app.db" "var/app.db"
copy_db "$ROOT/derivatives/runs.db" "derivatives/runs.db"

INCLUDE=()
for d in runs derivatives var configs manifest; do
    [[ -e "$ROOT/$d" ]] && INCLUDE+=("$d")
done

if [[ ${#INCLUDE[@]} -eq 0 ]]; then
    echo "nothing to back up in $ROOT" >&2
    exit 1
fi

# Two passes, because tar applies --exclude to every member no matter which -C
# it came from: excluding the live databases in one command would also exclude
# the snapshots being added back under the same names. The first pass takes the
# tree without them, the second appends the snapshots, and the result restores
# with a single untar. Appending needs an uncompressed archive, so it is written
# beside the destination and compressed at the end.
STAGING="$DEST/.dbsspeech_$STAMP.tar"
trap 'rm -rf "$TMP"; rm -f "$STAGING"' EXIT

tar -cf "$STAGING" \
    --exclude='derivatives/runs.db' \
    --exclude='derivatives/runs.db-wal' \
    --exclude='derivatives/runs.db-shm' \
    --exclude='var/app.db' \
    --exclude='var/app.db-wal' \
    --exclude='var/app.db-shm' \
    -C "$ROOT" "${INCLUDE[@]}"

if [[ ${#SNAPSHOTS[@]} -gt 0 ]]; then
    tar -rf "$STAGING" -C "$TMP" "${SNAPSHOTS[@]}"
fi

gzip -c "$STAGING" > "$ARCHIVE"
rm -f "$STAGING"

echo "$ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

# Keep the last N. Old backups that fill a disk take the app down with them.
if [[ "$KEEP" -gt 0 ]]; then
    while IFS= read -r old; do
        [[ -n "$old" ]] || continue
        rm -f "$old"
        echo "removed $old"
    done < <(ls -1t "$DEST"/dbsspeech_*.tar.gz 2>/dev/null | tail -n "+$((KEEP + 1))")
fi

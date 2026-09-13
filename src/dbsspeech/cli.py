"""Command line interface.

The same package the API calls, so a run started here is indistinguishable from
one started in the browser: same guardrails, same run record, same provenance.
Nothing here reimplements anything.

    python -m dbsspeech status
    python -m dbsspeech ask "beta in the STN during overt speech"
    python -m dbsspeech run psd_by_condition --subject demo01 --claim "..."
    python -m dbsspeech validate
    python -m dbsspeech inspect data/<block>
    python -m dbsspeech serve
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .guardrails import GuardrailBlocked
from .qc import QCNotApproved


def _parse_set(values: list[str] | None) -> dict[str, Any]:
    """Turn `--set fmin=1 --set conditions=overt,metro` into typed parameters.

    Values are parsed as JSON first so numbers, booleans and lists keep their
    type, falling back to a comma-split list and then to a bare string.
    """
    out: dict[str, Any] = {}
    for item in values or []:
        if "=" not in item:
            raise SystemExit(f"--set expects key=value, got {item!r}")
        key, raw = item.split("=", 1)
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            out[key] = [p for p in raw.split(",") if p] if "," in raw else raw
    return out


def cmd_status(args: argparse.Namespace) -> int:
    from .manifest import load_manifest, validate
    from .runs import list_runs, reindex

    manifest = load_manifest()
    report = validate(manifest)
    print(f"manifest: {'valid' if report.ok else 'INVALID'}")
    for err in report.errors:
        print(f"  ERROR   {err}")
    for warn in report.warnings:
        print(f"  warning {warn}")

    # Surface the gate here, because this is the command he runs to orient, and
    # a blocked subject is the thing most likely to be forgotten.
    from .qc import status as qc_status

    derivatives = Path("derivatives")
    blocked = [
        (row["study_id"], qc_status(row["study_id"], derivatives))
        for row in manifest.subjects
        if qc_status(row["study_id"], derivatives) != "approved"
    ]
    if blocked:
        print("\nBLOCKED by the QC gate; no recipe can run on these:")
        for study_id, state in blocked:
            print(f"  {study_id}: {state}")
        print("  review at http://127.0.0.1:5173/qc/<study_id>, "
              "or python -m dbsspeech qc list --subject <study_id>")

    print(f"\nsubjects ({len(manifest.subjects)}):")
    for row in manifest.subjects:
        sid, ses = row["study_id"], row["session"]
        included = [
            c for c in manifest.channels_for(sid, ses)
            if c.get("include", "").lower() == "true"
        ]
        leads = [
            f"{lr['lead_id']}:{lr['target']}"
            for lr in manifest.leads
            if (lr["study_id"], lr["session"]) == (sid, ses)
        ]
        windows = [
            w["condition"] + ("*" if w["status"] == "under_revision" else "")
            for w in manifest.windows
            if (w["study_id"], w["session"]) == (sid, ses)
        ]
        print(f"  {sid}/{ses}  {row['format']:10s} {len(included):3d} channels  "
              f"leads {','.join(leads)}  conditions {','.join(windows)}")
    if any(w["status"] == "under_revision" for w in manifest.windows):
        print("  * window under revision; results using it are flagged")

    # The queue, because "I clicked run and nothing happened" is almost always
    # "no worker is running" and there is otherwise nowhere to see that.
    from .jobs import queue_health

    queue = queue_health()
    if queue["queued"] or queue["running"] or queue["workers"]:
        print(f"\nqueue: {queue['queued']} queued, {queue['running']} running, "
              f"{queue['workers']} worker(s)")
    if queue["note"]:
        print(f"  {queue['note']}")

    try:
        reindex()
        recent = list_runs(limit=args.limit)
    except Exception:
        recent = []
    print(f"\nlast {len(recent)} runs:")
    for row in recent:
        flag = f"  [{row['n_blocking']} blocked, {row['n_overrides']} overridden]" if (
            row["n_blocking"] or row["n_overrides"]) else ""
        dirty = "  DIRTY TREE" if row["git_dirty"] else ""
        print(f"  {row['run_id']}  {row['status']:7s} {row['name']}{flag}{dirty}")
        if row.get("claim"):
            print(f"      {row['claim'][:88]}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from .manifest import load_manifest, validate

    report = validate(load_manifest())
    print(report)
    return 0 if report.ok else 1


def cmd_ask(args: argparse.Namespace) -> int:
    import yaml

    from .agent import propose
    from .io.loader import open_session
    from .manifest import DEFAULT_CONFIG_DIR, load_configs

    configs = load_configs()
    for extra in ("bands", "statistics"):
        path = Path(DEFAULT_CONFIG_DIR) / f"{extra}.yaml"
        if path.exists():
            configs[extra] = yaml.safe_load(path.read_text())

    session = None
    try:
        if args.subject:
            session = open_session(args.subject, args.session)
        proposal = propose(args.question, session=session, configs=configs,
                           recipe=args.recipe)
    finally:
        if session is not None:
            session.close()

    print(f"recipe: {proposal.recipe}")
    print(f"params: {json.dumps(proposal.params)}")
    if proposal.reasoning:
        print("\nwhy:")
        for r in proposal.reasoning:
            print(f"  {r.name} = {r.value}")
            print(f"      {r.reason}")
    if proposal.guardrails:
        print("\nguardrails that would fire:")
        for g in proposal.guardrails:
            print(f"  [{g['severity']}] {g['guardrail']}")
            print(f"      {g['message']}")
            if g["remedy"]:
                print(f"      what to do: {g['remedy']}")
    if proposal.caveats:
        print("\ncaveats:")
        for c in proposal.caveats:
            print(f"  {c}")
    if proposal.questions:
        print("\nit could not determine:")
        for q in proposal.questions:
            print(f"  {q}")
    if proposal.blocked:
        print("\nBLOCKED as proposed. Change a parameter, or run with an override "
              "and a reason.")
    else:
        sets = " ".join(f"--set {k}={json.dumps(v)}" for k, v in proposal.params.items())
        subject = args.subject or "<study_id>"
        print(f"\nto run it:\n  python -m dbsspeech run {proposal.recipe} "
              f"--subject {subject} --claim \"...\" {sets}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from .recipes import run as run_recipe

    overrides = {}
    for item in args.override or []:
        if "=" not in item:
            raise SystemExit(f"--override expects guardrail=reason, got {item!r}")
        name, reason = item.split("=", 1)
        overrides[name] = reason

    try:
        run_id = run_recipe(
            args.recipe, args.subject, args.session, claim=args.claim,
            params=_parse_set(args.set), overrides=overrides or None,
        )
    except QCNotApproved as exc:
        # The gate fires before guardrails, so it needs its own message rather
        # than a traceback. Exit 3 distinguishes it from a guardrail block.
        print(f"{exc}\n\nSee: python -m dbsspeech qc --help", file=sys.stderr)
        return 3
    except GuardrailBlocked as exc:
        print(str(exc), file=sys.stderr)
        return 2

    from .runs import get_run, reindex

    reindex()
    record = get_run(run_id) or {}
    print(f"run_id: {run_id}")
    print(f"status: {record.get('status')}")
    for finding in (record.get("guardrails") or {}).get("findings", []):
        print(f"  [{finding['severity']}] {finding['guardrail']}: {finding['message']}")
    out = Path("derivatives") / "results" / run_id
    for name in sorted(record.get("outputs", [])):
        if name.endswith((".png", ".svg")):
            print(f"figure: {out / name}")
    summary = record.get("summary") or {}
    if summary.get("normalization"):
        print(f"z: {summary['normalization']['sentence']}")
    return 0


def _qc_collect(study_id: str, session: str):
    """Load a recording and run detection over every included contact.

    Monopolar, because QC judges the channels as recorded. Re-referencing is an
    analysis choice; a bad contact is a bad contact under any montage.
    """
    import numpy as np
    import yaml

    from .io.loader import open_session
    from .manifest import DEFAULT_CONFIG_DIR
    from .qc import detect_all

    config_dir = Path(DEFAULT_CONFIG_DIR)
    thresholds = yaml.safe_load((config_dir / "qc_thresholds.yaml").read_text())
    leads_cfg = yaml.safe_load((config_dir / "leads.yaml").read_text())["leads"]

    sfreq = 0.0
    with open_session(study_id, session) as sess:
        names, regions, kinds, chunks = [], [], [], []
        for lead_id, lead in sess.leads().items():
            sig = sess.read_derived(lead_id, "monopolar", sfreq_target_hz=2034.5)
            by_id = {
                str(c["id"]): c.get("kind", "ring")
                for c in leads_cfg[lead.lead_model]["contacts"]
            }
            chunks.append(sig.data)
            names += [f"{lead_id}:{n}" for n in sig.names]
            regions += [lead.target] * len(sig.names)
            kinds += [by_id.get(n, "") for n in sig.names]
            sfreq = sig.sfreq_hz
        data = np.vstack(chunks)
        windows = sess.windows()
    flags = detect_all(data, sfreq, names, regions, thresholds, kinds=kinds)
    return data, sfreq, names, regions, flags, windows


def cmd_qc(args: argparse.Namespace) -> int:
    from collections import Counter

    from .qc import (
        build_model,
        decide_many,
        load_decisions,
        read_history,
        save_decisions,
        select,
        undecided,
        write_report,
    )
    from .qc import propose as qc_propose
    from .qc import reopen as qc_reopen
    from .qc import sign as qc_sign
    from .qc import status as qc_status

    derivatives = Path(args.derivatives)

    if args.qc_command == "propose":
        data, sfreq, names, regions, flags, windows = _qc_collect(args.subject, args.session)
        _, decisions_path, rows = qc_propose(flags, args.subject, derivatives)
        model = build_model(args.subject, args.session, data, sfreq, names, regions,
                            flags, windows)
        report_path = write_report(model, derivatives)
        print(f"{len(flags)} flags")
        for kind, n in Counter(f.flag_type for f in flags).most_common():
            print(f"  {kind:24s} {n}")
        print(f"\nreport:    {report_path}")
        print(f"decisions: {decisions_path}  ({len(undecided(rows))} undecided)")
        return 0

    if args.qc_command == "list":
        rows = select(load_decisions(args.subject, derivatives),
                      flag_type=args.flag_type or None,
                      severity=args.severity or None)
        print(f"{len(rows)} undecided flag(s)")
        for row in rows:
            print(f"  {row['severity']:5s} {row['flag_type']:24s} "
                  f"{row['target']:22s} -> {row['proposed_action'] or '(none proposed)'}")
        return 0

    if args.qc_command == "approve":
        # A bulk decision must state what it covers, so the history shows what a
        # reviewer actually looked at. There is deliberately no --all.
        if not (args.flag_type or args.severity or args.target):
            print("approve needs a scope: --flag-type, --severity or --target.",
                  file=sys.stderr)
            return 1
        if not args.reviewer.strip():
            print("approve needs --reviewer: an anonymous approval is not one",
                  file=sys.stderr)
            return 1
        rows = load_decisions(args.subject, derivatives)
        matched = select(rows, flag_type=args.flag_type or None,
                         severity=args.severity or None, target=args.target or None)
        if not matched:
            print("nothing matched that scope")
            return 0
        print(f"{len(matched)} flag(s) in scope:")
        for kind, n in Counter(r["flag_type"] for r in matched).most_common():
            print(f"  {kind:24s} {n}")
        if args.dry_run:
            print("\ndry run; nothing written")
            return 0
        reason = args.reason or f"bulk approval by scope, {len(matched)} flag(s)"
        rows = decide_many(rows, [r["flag_id"] for r in matched], approved=True,
                           reviewer=args.reviewer, reason=reason)
        save_decisions(args.subject, rows, derivatives)
        print(f"\napproved. {len(undecided(rows))} still undecided.")
        return 0

    if args.qc_command == "status":
        rows = load_decisions(args.subject, derivatives)
        pending = undecided(rows)
        print(f"{args.subject}: {qc_status(args.subject, derivatives)}")
        print(f"  {len(rows)} flags, {len(pending)} undecided")
        for event in read_history(args.subject, derivatives):
            print(f"  {event['at']}  {event['event']:7s} {event['reviewer']}  "
                  f"{event.get('reason', '')}")
        return 0

    if args.qc_command == "sign":
        try:
            approval = qc_sign(args.subject, args.reviewer, derivatives)
        except (QCNotApproved, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"signed {args.subject} by {approval['reviewer']}: "
              f"{approval['n_approved']} of {approval['n_flags']} flags approved")
        return 0

    if args.qc_command == "reopen":
        try:
            qc_reopen(args.subject, args.reviewer, args.reason, derivatives)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"reopened {args.subject}: {args.reason}")
        return 0

    return 1


def cmd_users(args: argparse.Namespace) -> int:
    """Account management. Passwords are prompted for, never taken as arguments.

    A password on a command line ends up in shell history and in `ps` output.
    """
    import getpass

    from .auth import (
        AuthError,
        add_user,
        list_users,
        set_disabled,
        set_password,
        set_role,
    )

    db = Path(args.db) if args.db else None

    try:
        if args.users_command == "list":
            users = list_users(db)
            if not users:
                print("no users yet. Add one with: python -m dbsspeech users add")
                return 0
            for user in users:
                flag = "  DISABLED" if user.disabled else ""
                print(f"  {user.name:24s} {user.email:32s} {user.role:9s}{flag}")
            return 0

        if args.users_command == "add":
            password = getpass.getpass("password (at least 12 characters): ")
            if password != getpass.getpass("repeat: "):
                print("passwords did not match", file=sys.stderr)
                return 1
            user = add_user(args.name, args.email, args.role, password, db)
            print(f"created {user.email} as {user.role}")
            return 0

        if args.users_command == "reset-password":
            password = getpass.getpass("new password (at least 12 characters): ")
            if password != getpass.getpass("repeat: "):
                print("passwords did not match", file=sys.stderr)
                return 1
            set_password(args.email, password, db)
            print(f"password reset for {args.email}")
            return 0

        if args.users_command == "set-role":
            set_role(args.email, args.role, db)
            print(f"{args.email} is now {args.role}")
            return 0

        if args.users_command in {"disable", "enable"}:
            set_disabled(args.email, args.users_command == "disable", db)
            print(f"{args.email} {args.users_command}d")
            return 0
    except AuthError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 1


def cmd_inspect(args: argparse.Namespace) -> int:
    from .io import open_recording

    with open_recording(args.path) as rec:
        print(f"format: {rec.format}")
        print("streams:")
        for name, info in rec.streams.items():
            print(f"  {name:8s} {info.n_channels:3d} ch @ {info.sfreq_hz:>11.3f} Hz  "
                  f"{info.duration_s:8.1f}s  usable to {info.usable_bandwidth_hz:.0f} Hz")
        if rec.epochs:
            print("epochs:", {k: len(v) for k, v in rec.epochs.items()})
        meta = rec.metadata
        withheld = meta.get("restricted_fields_present") or []
        if withheld:
            print(f"withheld metadata fields: {withheld}")
    return 0


def cmd_windows(args: argparse.Namespace) -> int:
    """Propose windows.csv rows from a recording's task markers.

    Prints rows for review and, with --csv, in a form that can be pasted into
    the manifest. It never edits manifest/windows.csv: a window that entered the
    manifest without a person reading it would be indistinguishable from one
    that was reviewed, which is the whole thing the draft status exists to
    prevent.
    """
    import csv as _csv
    import sys as _sys

    from .detect import propose_windows, proposed_rows
    from .detect.windows import WINDOW_COLUMNS
    from .io import open_recording
    from .manifest import load_configs

    config = (load_configs() or {}).get("markers") or {}
    with open_recording(args.path) as rec:
        proposals = propose_windows(rec, args.study_id, args.session, config)

    rows = proposed_rows(proposals)
    if args.csv:
        writer = _csv.DictWriter(_sys.stdout, fieldnames=list(WINDOW_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
        return 0

    print(proposals.report() or "nothing to report")
    print()
    if rows:
        print(f"{len(rows)} draft row(s). Review them, then add with --csv.")
    else:
        print(
            "No windows proposed. Bind the marker labels above to conditions in "
            "configs/markers.yaml, then run this again."
        )
    return 0


def cmd_draft_manifest(args: argparse.Namespace) -> int:
    """Derive subjects.csv and streams.csv rows from a tree of recordings.

    Writes to --out or prints to stdout. Never into manifest/: these are derived
    rows that still need the columns only a person can fill.
    """
    import csv as _csv
    import sys as _sys

    from .detect.manifest_rows import (
        LEFT_TO_REVIEW,
        STREAM_COLUMNS,
        SUBJECT_COLUMNS,
        draft_manifest,
    )

    draft = draft_manifest(Path(args.root), args.study_id or None)

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for name, columns, rows in (
            ("subjects.csv", SUBJECT_COLUMNS, draft.subjects),
            ("streams.csv", STREAM_COLUMNS, draft.streams),
        ):
            with open(out / name, "w", newline="", encoding="utf-8") as fh:
                writer = _csv.DictWriter(fh, fieldnames=list(columns))
                writer.writeheader()
                writer.writerows(rows)
        print(f"wrote {out}/subjects.csv  {len(draft.subjects)} rows")
        print(f"wrote {out}/streams.csv   {len(draft.streams)} rows")
    else:
        writer = _csv.DictWriter(_sys.stdout, fieldnames=list(SUBJECT_COLUMNS))
        writer.writeheader()
        writer.writerows(draft.subjects)

    print(f"\n{len(draft.study_ids)} study id(s): {', '.join(draft.study_ids)}")
    if draft.unreadable:
        print(f"\n{len(draft.unreadable)} block(s) could not be read:")
        for where, why in draft.unreadable[:10]:
            print(f"  {where}: {why}")
    print("\nLeft empty on purpose, because they are the review, not the import:")
    for column, why in LEFT_TO_REVIEW.items():
        print(f"  {column:18s} {why}")
    print("  channels.csv, leads.csv, windows.csv are not derived at all")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Open every recording under a root and report which ones the readers take."""
    from .detect.manifest_rows import verify_readable

    report = verify_readable(Path(args.root), args.study_id or None)
    if not report:
        print(f"no recordings found under {args.root}")
        return 0

    total_ok = total_bad = 0
    for study_id in sorted(report):
        row = report[study_id]
        total_ok += row["opened"]
        total_bad += row["failed"]
        print(
            f"{study_id:<12} blocks={row['blocks']:<4} "
            f"opened={row['opened']:<4} failed={row['failed']}"
        )
        if args.verbose:
            for err in row["errors"]:
                print(f"    {err['block']}: {err['error']}")

    print(f"\ntotal opened={total_ok} failed={total_bad}")
    return 1 if total_bad else 0


def cmd_derive(args: argparse.Namespace) -> int:
    """Build one staged block into the derivative store.

    The site driver does this at scale with a ledger; this is the single-block
    form for a lab without one. Exit 0 when the block is written, 2 when policy
    quarantined it (the reason is printed), 1 when the build failed.
    """
    from .derive.config import load_config
    from .derive.model import BlockJob
    from .derive.pipeline import build_block, default_provenance
    from .derive.redact import scrubber_from_config

    cfg = load_config(args.config) if args.config else load_config()
    block_dir = Path(args.block_dir).expanduser()
    out_root = Path(args.out_root).expanduser() if args.out_root else cfg.store.root_path()
    audio_root = (
        Path(args.audio_root).expanduser() if args.audio_root else cfg.store.audio_root_path()
    )
    job = BlockJob(
        study_id=args.study_id,
        session=args.session,
        block=args.block or block_dir.name,
        source_format=args.format,
        local_dir=block_dir,
        entry=Path(args.entry).expanduser() if args.entry else None,
    )
    scrubber = scrubber_from_config(cfg, extra_roots=[block_dir, out_root, audio_root])
    result = build_block(
        job, cfg, out_root, provenance=default_provenance(), scrubber=scrubber,
        audio_root=audio_root,
    )
    print(f"{result.study_id} {result.session}/{result.block}: {result.status}")
    if result.status == "done":
        print(f"  wrote {result.out_relpath} ({result.out_bytes / 1048576:.0f} MB) "
              f"in {result.seconds:.0f} s; products: "
              + ", ".join(f"{p.stream}/{p.product}@{p.sfreq_out_hz:g}Hz" for p in result.products))
        if result.audio_relpath:
            print(f"  audio: {result.audio_relpath}")
        return 0
    if result.status == "quarantined":
        print(f"  quarantined: {result.quarantine_reason}: {result.error_message}")
        return 2
    print(f"  failed: {result.error_class}: {result.error_message}")
    return 1


def cmd_serve(args: argparse.Namespace) -> int:
    import os

    from .api import serve
    from .jobs import queue_health

    authed = os.environ.get("DBSSPEECH_REQUIRE_AUTH", "").lower() in {"1", "true", "yes"}
    note = "authenticated" if authed else "no auth; localhost only"
    print(f"http://{args.host}:{args.port}/          the app")
    print(f"http://{args.host}:{args.port}/api/docs  the API ({note})")
    # Said at startup rather than only when a run is submitted, because the
    # person starting the API is the one who can start a worker.
    executor = os.environ.get("DBSSPEECH_EXECUTOR", "queue").strip().lower()
    if executor != "background" and not queue_health()["workers_responsive"]:
        print("no worker is running; submitted runs will queue until you start one "
              "with `python -m dbsspeech worker`")
    try:
        serve(host=args.host, port=args.port)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    """Build a demo project so every screen has something real in it."""
    from .seed import seed

    result = seed(root=args.root, overwrite=args.overwrite)
    print()
    print(f"subject {result.study_id}: {result.n_flags} QC flag(s), {result.qc_status}")
    print(f"{len(result.runs)} run(s) in {result.root / 'runs'}")
    if result.failures:
        print("\nthese recipes failed on the demo recording:", file=sys.stderr)
        for name, why in result.failures.items():
            print(f"  {name}: {why}", file=sys.stderr)
        return 1
    print("\nlook at it with:")
    print(f"  DBSSPEECH_MANIFEST={result.root / 'manifest'} "
          f"DBSSPEECH_DATA={result.root / 'data'} \\")
    print(f"  DBSSPEECH_DERIVATIVES={result.root / 'derivatives'} "
          f"DBSSPEECH_RUNS={result.root / 'runs'} ./scripts/dev.sh")
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    """Execute queued runs until stopped.

    The process the deployment actually depends on. Without one, a submitted run
    sits in the queue and the interface says so rather than pretending.
    """
    from .jobs.worker import Worker

    worker = Worker(
        poll_interval_s=args.poll_interval,
        stale_after_s=args.stale_after,
    )
    if args.once:
        job = worker.run_once()
        if job is None:
            print("nothing queued")
            return 0
        print(f"{job['job_id']}: {job['status']}"
              + (f"  run {job['run_id']}" if job["run_id"] else "")
              + (f"\n  {job['error']}" if job["error"] else ""))
        return 0 if job["status"] == "ok" else 1

    worker.install_signal_handlers()
    worker.run_forever(max_jobs=args.max_jobs)
    return 0


def cmd_jobs(args: argparse.Namespace) -> int:
    """What is queued, running, or recently finished."""
    from .jobs import list_jobs, queue_health

    health = queue_health()
    print(f"{health['queued']} queued, {health['running']} running, "
          f"{health['workers']} worker(s)")
    if health["note"]:
        print(f"  {health['note']}")
    rows = list_jobs(status=args.status, limit=args.limit)
    if not rows:
        print("no jobs")
        return 0
    print()
    for row in rows:
        print(f"  {row['job_id']}  {row['status']:8s} {row['recipe']} "
              f"on {row['study_id']}/{row['session']}"
              + (f"  run {row['run_id']}" if row["run_id"] else ""))
        if row["error"]:
            print(f"      {row['error'][:100]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbsspeech",
        description="Analysis for intraoperative DBS and ECoG recordings.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="subjects, manifest health, and recent runs")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("validate", help="check the manifests against the schema")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("ask", help="propose a recipe and parameters from a question")
    p.add_argument("question")
    p.add_argument("--subject")
    p.add_argument("--session", default="ses1")
    p.add_argument("--recipe", default="psd_by_condition")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("run", help="run a recipe with provenance and guardrails")
    p.add_argument("recipe")
    p.add_argument("--subject", required=True)
    p.add_argument("--session", default="ses1")
    p.add_argument("--claim", required=True,
                   help="one sentence: what this run is meant to show")
    p.add_argument("--set", action="append", metavar="KEY=VALUE")
    p.add_argument("--override", action="append", metavar="GUARDRAIL=REASON")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("qc", help="quality-control status, sign-off, and reopening")
    p.add_argument("qc_command",
                   choices=["propose", "list", "approve", "status", "sign", "reopen"])
    p.add_argument("--subject", required=True)
    p.add_argument("--session", default="ses1")
    p.add_argument("--reviewer", default="")
    p.add_argument("--reason", default="")
    p.add_argument("--flag-type", dest="flag_type", default="")
    p.add_argument("--severity", default="", choices=["", "low", "med", "high"])
    p.add_argument("--target", default="")
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    p.add_argument("--derivatives", default="derivatives")
    p.set_defaults(func=cmd_qc)

    p = sub.add_parser("users", help="manage accounts and roles")
    p.add_argument("users_command",
                   choices=["list", "add", "reset-password", "set-role",
                            "disable", "enable"])
    p.add_argument("--name", default="")
    p.add_argument("--email", default="")
    p.add_argument("--role", default="analyst", choices=["reviewer", "analyst", "admin"])
    p.add_argument("--db", default="")
    p.set_defaults(func=cmd_users)

    p = sub.add_parser("inspect", help="report a recording's structure")
    p.add_argument("path")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("seed", help="build a demo project: synthetic subject, QC, runs")
    p.add_argument("--root", type=Path, default=None,
                   help="where to build it; default demo/ in the repository")
    p.add_argument("--overwrite", action="store_true",
                   help="replace an existing demo project")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("worker", help="execute queued runs until stopped")
    p.add_argument("--once", action="store_true",
                   help="take at most one job, then exit")
    p.add_argument("--max-jobs", type=int, default=None,
                   help="stop after this many jobs")
    p.add_argument("--poll-interval", type=float, default=2.0,
                   help="seconds between checks for new work")
    p.add_argument("--stale-after", type=float, default=120.0,
                   help="seconds without a heartbeat before a running job is failed")
    p.set_defaults(func=cmd_worker)

    p = sub.add_parser("jobs", help="what is queued, running, or recently finished")
    p.add_argument("--status", choices=["queued", "running", "ok", "failed", "blocked"])
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_jobs)

    p = sub.add_parser(
        "windows", help="propose condition windows from a recording's task markers"
    )
    p.add_argument("path")
    p.add_argument("study_id")
    p.add_argument("session")
    p.add_argument("--csv", action="store_true",
                   help="emit windows.csv rows instead of the review report")
    p.set_defaults(func=cmd_windows)

    p = sub.add_parser(
        "draft-manifest",
        help="derive subjects.csv and streams.csv rows from a tree of recordings",
    )
    p.add_argument("root", help="directory holding <study_id>/<block>/ recordings")
    p.add_argument("--out", help="write the CSVs here instead of printing")
    p.add_argument("--study-id", action="append", help="limit to these study ids")
    p.set_defaults(func=cmd_draft_manifest)

    p = sub.add_parser(
        "verify", help="check that every recording under a root opens"
    )
    p.add_argument("root")
    p.add_argument("--study-id", action="append", help="limit to these study ids")
    p.add_argument("--verbose", action="store_true", help="show each failure")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser(
        "derive",
        help="build one staged block into the derivative store (configs/derive.yaml)",
    )
    p.add_argument("block_dir", help="the staged block directory")
    p.add_argument("--study-id", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--block", default=None, help="block name; default is the directory name")
    p.add_argument("--format", required=True,
                   help="tdt_mat, tdt_tank, brainvision or edf")
    p.add_argument("--entry", default=None,
                   help="the entry file when the directory holds several (a .vhdr or .mat)")
    p.add_argument("--out-root", default=None, help="store root; default from configs/derive.yaml")
    p.add_argument("--audio-root", default=None, help="microphone store root; default from config")
    p.add_argument("--config", default=None, help="an alternative derive.yaml")
    p.set_defaults(func=cmd_derive)

    p = sub.add_parser("serve", help="start the API on localhost")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

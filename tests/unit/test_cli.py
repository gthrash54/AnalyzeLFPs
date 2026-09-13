"""The command line. Same package the API calls, so a run is indistinguishable."""

from __future__ import annotations

import pytest

from dbsspeech.cli import _parse_set, build_parser, main

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def demo_project(tmp_path_factory):
    """Point the manifest and data directories at a synthetic demo subject.

    These tests used to read `manifest/*.csv` in the repository, which held one
    real subject. The public repository ships header-only manifests, so a test
    that needs rows has to make its own. `build_project` writes the same eight
    contacts and two conditions that `dbsspeech seed` gives a new user, so what
    is exercised here is the path a reader of the README actually walks.

    Module-scoped and using `build_project` rather than `seed`, because seeding
    also runs every recipe and that is a different test's job.
    """
    from dbsspeech import manifest as manifest_mod
    from dbsspeech.io import loader as loader_mod
    from dbsspeech.seed import build_project

    root = tmp_path_factory.mktemp("demo") / "demo"
    build_project(root)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(manifest_mod, "DEFAULT_MANIFEST_DIR", root / "manifest")
        mp.setattr(loader_mod, "DEFAULT_DATA_DIR", root / "data")
        # The API resolves the data directory from its own module-level DATA_DIR,
        # set from the environment at import, so patching the loader default is
        # not enough on this path.
        try:
            from dbsspeech.api import main as api_mod
            mp.setattr(api_mod, "DATA_DIR", root / "data")
        except ImportError:
            pass
        yield root


# ---- parameter parsing -------------------------------------------------------

def test_numbers_keep_their_type():
    assert _parse_set(["fmin=1", "fmax=30.5"]) == {"fmin": 1, "fmax": 30.5}


def test_json_lists_are_parsed():
    assert _parse_set(['conditions=["overt","metro"]'])["conditions"] == ["overt", "metro"]


def test_comma_lists_are_parsed():
    assert _parse_set(["conditions=overt,metro"])["conditions"] == ["overt", "metro"]


def test_booleans_and_bare_strings():
    out = _parse_set(["method=welch", "flag=true"])
    assert out["method"] == "welch"
    assert out["flag"] is True


def test_a_malformed_set_is_rejected_with_the_offender():
    with pytest.raises(SystemExit, match="fmin"):
        _parse_set(["fmin"])


# ---- parser ------------------------------------------------------------------

def test_every_subcommand_is_registered():
    parser = build_parser()
    actions = [a for a in parser._actions if a.dest == "command"]
    assert set(actions[0].choices) == {
        "status", "validate", "ask", "run", "qc", "users", "inspect", "serve",
        "worker", "jobs", "seed", "windows", "draft-manifest", "verify", "derive",
    }


def test_run_requires_a_claim():
    """A result whose purpose was never stated cannot be reviewed."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "psd_by_condition", "--subject", "x"])


def test_run_requires_a_subject():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "psd_by_condition", "--claim", "c"])


# ---- commands ----------------------------------------------------------------

def test_validate_reports_the_project_manifests(capsys):
    """The demo manifest validates clean, which is what a new reader should see.

    This asserted that the output contained a warning, which was true only
    because the repository's one real subject had a lead with no rotation
    recorded. A shipped manifest that warns on the first command anyone runs is
    not the greeting this should give, so the assertion now checks the command
    reports a verdict rather than checking for a specific complaint.
    """
    assert main(["validate"]) == 0
    assert "valid" in capsys.readouterr().out


def test_status_lists_subjects_and_flags_revised_windows(capsys, tmp_path, monkeypatch):
    """A window under revision must be marked, so `status` has to say so.

    Given its own manifest rather than the repository's. This test used to rely
    on a real subject happening to have a window under revision, which made it a
    test of that subject as much as of the command.
    """
    from dbsspeech import manifest as manifest_mod

    d = tmp_path / "manifest"
    d.mkdir()
    (d / "subjects.csv").write_text(
        "study_id,session,hemisphere,format,root_relpath,acquisition,"
        "acquisition_date,notes\n"
        "demo01,ses1,R,tdt_mat,block,demo,,synthetic\n"
    )
    (d / "windows.csv").write_text(
        "study_id,session,condition,t_start_s,t_end_s,derived_from,status,notes\n"
        "demo01,ses1,rest,0.0,2.0,assumed,under_revision,being re-derived\n"
    )
    for name in ("streams", "leads", "channels"):
        (d / f"{name}.csv").write_text("study_id,session\n")
    monkeypatch.setattr(manifest_mod, "DEFAULT_MANIFEST_DIR", d)

    assert main(["status", "--limit", "1"]) == 0
    out = capsys.readouterr().out
    assert "demo01/ses1" in out
    assert "rest*" in out, "a window under revision must be marked"
    assert "under revision" in out


def test_ask_explains_and_offers_the_command(capsys):
    assert main(["ask", "beta in the STN during overt speech", "--subject", "demo01"]) == 0
    out = capsys.readouterr().out
    assert '"fmin": 13.0' in out
    assert "why:" in out
    assert "python -m dbsspeech run" in out


def test_ask_reports_a_block_and_offers_no_command(capsys):
    assert main(["ask", "high gamma at monopolar", "--subject", "demo01"]) == 0
    out = capsys.readouterr().out
    assert "BLOCKED as proposed" in out
    assert "python -m dbsspeech run" not in out


def test_ask_surfaces_what_it_could_not_determine(capsys):
    main(["ask", "what is in here", "--subject", "demo01"])
    assert "it could not determine" in capsys.readouterr().out


def test_ask_works_without_a_subject(capsys):
    assert main(["ask", "show me beta"]) == 0
    assert "recipe: psd_by_condition" in capsys.readouterr().out


def test_inspect_reports_structure_and_withheld_fields(capsys, demo_project):
    """Inspect the synthetic demo recording, not a real tank.

    This read a real subject's `.mat` out of `data/` before, which meant the
    test only passed on a machine with that recording mounted. The demo fixture
    is generated, so it passes anywhere.
    """
    path = str(demo_project / "data" / "block" / "synthetic_block.mat")
    assert main(["inspect", path]) == 0
    out = capsys.readouterr().out
    assert "format: tdt_mat" in out
    assert "neur" in out, "the stream name should be listed"
    assert "withheld metadata fields" in out


@pytest.fixture
def unreviewed(tmp_path):
    """A derivatives directory holding one subject with an undecided flag.

    These three tests are about what the gate does to an unreviewed subject, so
    they build that state instead of borrowing it from the repository's real
    `derivatives/`. They used to rely on a real subject happening to be unreviewed,
    which meant that reviewing it, the entire point of the workflow, turned the
    suite red. A test that a normal day's work breaks is a test nobody trusts.
    """
    from dbsspeech.qc import propose
    from dbsspeech.qc.flags import Flag

    propose(
        [Flag(target_type="channel", target="lead1:1", flag_type="flat_channel",
              evidence={"std_fraction_of_median": 0.001},
              proposed_action="exclude_channel", severity="high",
              detector="flat_channel")],
        "demo01",
        tmp_path,
    )
    return tmp_path


def test_run_refuses_unreviewed_data_with_its_own_exit_code(capsys, monkeypatch, tmp_path):
    """The gate fires before guardrails, so it gets its own message and code."""
    # An empty derivatives directory means nothing has been reviewed, whatever
    # the real project's subjects happen to look like today.
    monkeypatch.setattr("dbsspeech.recipes.registry.DEFAULT_DERIVATIVES", tmp_path)
    code = main([
        "run", "psd_by_condition", "--subject", "demo01",
        "--claim", "should be gated",
        "--set", "primary_reference=monopolar",
    ])
    assert code == 3
    err = capsys.readouterr().err
    assert "cannot be analyzed yet" in err
    assert "dbsspeech qc" in err, "must say how to fix it"


def test_qc_status_reports_the_gate_state(capsys, unreviewed):
    assert main(["qc", "status", "--subject", "demo01",
                 "--derivatives", str(unreviewed)]) == 0
    assert "in_review" in capsys.readouterr().out


def test_qc_sign_refuses_while_flags_are_undecided(capsys, unreviewed):
    assert main(["qc", "sign", "--subject", "demo01", "--reviewer", "g",
                 "--derivatives", str(unreviewed)]) == 1
    assert "undecided" in capsys.readouterr().err


def test_every_subcommand_includes_qc():
    parser = build_parser()
    actions = [a for a in parser._actions if a.dest == "command"]
    assert "qc" in actions[0].choices


def test_override_needs_a_reason():
    with pytest.raises(SystemExit, match="guardrail=reason"):
        main([
            "run", "psd_by_condition", "--subject", "demo01", "--claim", "c",
            "--override", "G1_shared_reference_common_mode",
        ])


# ---- users -------------------------------------------------------------------

def test_users_list_is_empty_and_says_what_to_do(capsys, tmp_path):
    assert main(["users", "list", "--db", str(tmp_path / "app.db")]) == 0
    assert "no users yet" in capsys.readouterr().out


def test_users_add_then_list(capsys, tmp_path, monkeypatch):
    """Passwords are prompted for; a password on a command line reaches ps output."""
    db = str(tmp_path / "app.db")
    monkeypatch.setattr("getpass.getpass", lambda *_: "a-long-enough-passphrase")
    assert main(["users", "add", "--name", "Garrett", "--email", "g@example.org",
                 "--role", "admin", "--db", db]) == 0
    capsys.readouterr()
    assert main(["users", "list", "--db", db]) == 0
    out = capsys.readouterr().out
    assert "g@example.org" in out and "admin" in out


def test_mismatched_passwords_are_refused(capsys, tmp_path, monkeypatch):
    answers = iter(["a-long-enough-passphrase", "something-else-entirely"])
    monkeypatch.setattr("getpass.getpass", lambda *_: next(answers))
    code = main(["users", "add", "--name", "G", "--email", "g@example.org",
                 "--db", str(tmp_path / "app.db")])
    assert code == 1
    assert "did not match" in capsys.readouterr().err


def test_a_short_password_is_refused_with_the_rule(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr("getpass.getpass", lambda *_: "short")
    code = main(["users", "add", "--name", "G", "--email", "g@example.org",
                 "--db", str(tmp_path / "app.db")])
    assert code == 1
    assert "at least 12" in capsys.readouterr().err


def test_disabling_a_user_shows_in_the_listing(capsys, tmp_path, monkeypatch):
    db = str(tmp_path / "app.db")
    monkeypatch.setattr("getpass.getpass", lambda *_: "a-long-enough-passphrase")
    main(["users", "add", "--name", "G", "--email", "g@example.org", "--db", db])
    main(["users", "disable", "--email", "g@example.org", "--db", db])
    capsys.readouterr()
    main(["users", "list", "--db", db])
    assert "DISABLED" in capsys.readouterr().out

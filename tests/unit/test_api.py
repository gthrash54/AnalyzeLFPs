"""The HTTP surface: subjects, recipes, agent, runs, files, uploads."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dbsspeech.api import app
from dbsspeech.api import main as api
from dbsspeech.jobs import queue as jobs

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


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point the app at empty directories so tests never touch real outputs."""
    for name, sub in (("DERIVATIVES_DIR", "derivatives"), ("RUNS_DIR", "runs"),
                      ("UPLOAD_DIR", "uploads")):
        d = tmp_path / sub
        d.mkdir()
        monkeypatch.setattr(api, name, d)
    return tmp_path


def test_health_reports_manifest_validity(client):
    body = client.get("/health").json()
    assert body["manifest_valid"] is True
    assert isinstance(body["manifest_warnings"], list)


def test_subjects_expose_leads_and_conditions(client):
    subject = client.get("/subjects").json()[0]
    assert {"study_id", "leads", "conditions", "n_channels_included"} <= set(subject)
    assert {lead["target"] for lead in subject["leads"]} == {"stn"}


def test_subjects_report_whether_rotation_is_known(client):
    """Whether rotation is known gates anatomical direction claims, so it must be visible.

    The demo lead declares rotation_deg, so this asserts the field is surfaced
    and true. The False case, which blocks a direction claim, is covered
    directly in tests/unit/test_manifest.py rather than by whichever subject
    happens to be in the manifest.
    """
    subject = client.get("/subjects").json()[0]
    assert all(lead["rotation_known"] is True for lead in subject["leads"])


def test_window_status_reaches_the_interface(client):
    conditions = {c["condition"]: c for c in client.get("/subjects").json()[0]["conditions"]}
    assert set(conditions) == {"overt", "metro"}
    assert conditions["overt"]["status"] == "in_use"


def test_recipes_carry_schema_and_explanations(client):
    """The UI builds forms from the schema and shows the caveats beside them."""
    recipe = client.get("/recipes").json()[0]
    assert "primary_reference" in recipe["params_schema"]["properties"]
    scales = recipe["option_explanations"]["scales"]
    assert all(option["caveat"] for option in scales)


def test_configs_are_served_for_display(client):
    body = client.get("/configs/statistics").json()
    assert "centers" in body and "scales" in body


def test_unknown_config_is_404(client):
    assert client.get("/configs/nope").status_code == 404


# ---- agent, as the run flow uses it --------------------------------------------

def test_the_agent_chooses_a_recipe_when_asked_to(client):
    """Step two of a run: a question, not a function name."""
    body = client.post("/agent/propose", json={
        "question": "is beta higher during overt speech than during rest",
        "recipe": None,
    }).json()
    assert body["recipe"] == "bandpower_contrast"
    assert "matched on" in body["understood"]["recipe_reason"]


def test_the_answer_says_what_the_recipe_is_for_and_what_it_produces(client):
    """So the review step can say what you are about to get, in one request."""
    body = client.post("/agent/propose", json={
        "question": "how large is the ringing after each stimulation pulse",
        "recipe": None,
    }).json()
    assert body["recipe"] == "erna"
    assert "resonate" in body["asks"] or "ringing" in body["asks"]
    assert "amplitude" in body["produces"]


def test_values_you_set_are_re_checked_rather_than_replaced(client):
    """The review step is only honest if the dry run uses your values."""
    body = client.post("/agent/propose", json={
        "question": "",
        "recipe": "psd_by_condition",
        "params": {"primary_reference": "monopolar"},
    }).json()
    assert body["params"]["primary_reference"] == "monopolar"
    assert body["blocked"] is True
    assert any("G1" in g["guardrail"] for g in body["guardrails"])
    mine = next(r for r in body["reasoning"] if r["name"] == "primary_reference")
    assert mine["confidence"] == "yours"


def test_a_field_you_cleared_is_not_filled_back_in(client):
    """Emptying a field is a decision, and the agent does not overrule it."""
    kept = client.post("/agent/propose", json={
        "question": "look at beta", "recipe": "psd_by_condition",
    }).json()
    assert kept["params"]["fmax"] == 30.0

    body = client.post("/agent/propose", json={
        "question": "look at beta", "recipe": "psd_by_condition", "cleared": ["fmax"],
    }).json()
    assert "fmax" not in body["params"]
    reason = next(r for r in body["reasoning"] if r["name"] == "fmax")
    assert reason["confidence"] == "cleared"


def test_parameters_the_recipe_would_refuse_are_reported_not_raised(client):
    body = client.post("/agent/propose", json={
        "question": "", "recipe": "psd_by_condition", "params": {"method": "nope"},
    }).json()
    assert any("refused" in q for q in body["questions"])


def test_recipes_carry_the_question_they_answer(client):
    """The run screen offers these instead of function names."""
    recipes = {r["name"]: r for r in client.get("/recipes").json()}
    assert "spectrum" in recipes["psd_by_condition"]["question"]
    assert recipes["erna"]["produces"]


def test_a_recipe_can_say_which_parameters_matter(client):
    """Twenty fields is a wall. ERNA marks the three that decide the answer."""
    erna = next(r for r in client.get("/recipes").json() if r["name"] == "erna")
    props = erna["params_schema"]["properties"]
    essential = [n for n, p in props.items() if p.get("x-group") == "essential"]
    assert set(essential) == {"stim_source", "blanking_ms", "analysis_ms"}
    assert props["blanking_ms"]["title"] == "Discard after each pulse (ms)"


# ---- agent -------------------------------------------------------------------

def test_agent_infers_parameters_from_plain_language(client):
    body = client.post("/agent/propose", json={
        "question": "beta in the STN during overt speech",
        "study_id": "demo01", "session": "ses1"}).json()
    assert body["params"]["fmin"] == 13.0
    assert body["params"]["conditions"] == ["overt"]
    assert body["blocked"] is False


def test_agent_warns_before_you_run_rather_than_after(client):
    body = client.post("/agent/propose", json={
        "question": "beta in the STN during overt speech",
        "study_id": "demo01", "session": "ses1"}).json()
    assert "G11_control_condition_missing" in [g["guardrail"] for g in body["guardrails"]]


def test_agent_reports_a_block_without_running_anything(client):
    body = client.post("/agent/propose", json={
        "question": "high gamma at monopolar during rest",
        "study_id": "demo01", "session": "ses1"}).json()
    assert body["blocked"] is True
    assert any(g["severity"] == "block" for g in body["guardrails"])


def test_agent_surfaces_the_statistics_caveats(client):
    body = client.post("/agent/propose", json={"question": "show me beta"}).json()
    assert body["caveats"]


def test_agent_asks_rather_than_guessing(client):
    body = client.post("/agent/propose", json={
        "question": "what is in this recording",
        "study_id": "demo01", "session": "ses1"}).json()
    assert body["questions"]


def test_agent_rejects_an_unknown_recipe(client):
    assert client.post("/agent/propose",
                       json={"question": "x", "recipe": "nope"}).status_code == 404


# ---- runs --------------------------------------------------------------------

def test_invalid_parameters_are_refused_before_queueing(client):
    r = client.post("/runs", json={
        "recipe": "psd_by_condition", "study_id": "demo01", "session": "ses1",
        "claim": "c", "params": {"method": "not_a_method"}})
    assert r.status_code == 422


def test_a_claim_is_required(client):
    r = client.post("/runs", json={
        "recipe": "psd_by_condition", "study_id": "demo01", "session": "ses1",
        "claim": "", "params": {}})
    assert r.status_code == 422


def test_unknown_recipe_is_404(client):
    r = client.post("/runs", json={
        "recipe": "nope", "study_id": "demo01", "session": "ses1", "claim": "c"})
    assert r.status_code == 404


def test_unknown_run_is_404(client, isolated):
    assert client.get("/runs/nope").status_code == 404


def test_unknown_handle_is_404(client):
    assert client.get("/runs/status/nope").status_code == 404


# ---- the queue ---------------------------------------------------------------

def _submit(client, **kw):
    body = {"recipe": "psd_by_condition", "study_id": "demo01", "session": "ses1",
            "claim": "spectra by condition", "params": {}, **kw}
    return client.post("/runs", json=body)


def test_a_submitted_run_is_queued_rather_than_executed(client, isolated):
    """The API hands the work over. It must not compute anything itself."""
    r = _submit(client)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["executor"] == "queue"

    job = jobs.get_job(body["handle"], isolated / "derivatives" / "runs.db")
    assert job["status"] == "queued"
    assert job["recipe"] == "psd_by_condition"
    assert job["claimed_by"] is None
    assert list((isolated / "runs").glob("*.json")) == []


def test_submitting_says_when_nothing_will_pick_the_job_up(client, isolated):
    """Otherwise a queued run with no worker looks exactly like a busy one."""
    assert "no worker" in _submit(client).json()["worker_note"]


def test_attribution_is_taken_from_the_session_not_the_request(client, isolated):
    """Auth is off in tests, so this is the local user, never the caller's field."""
    r = _submit(client, user="someone-else")
    job = jobs.get_job(r.json()["handle"], isolated / "derivatives" / "runs.db")
    assert job["user"] == "local"


def test_status_of_a_queued_run_is_read_from_the_database(client, isolated):
    handle = _submit(client).json()["handle"]
    body = client.get(f"/runs/status/{handle}").json()
    assert body["status"] == "queued"
    assert body["run_id"] is None
    assert body["recipe"] == "psd_by_condition"


def test_a_finished_job_reports_its_run_id(client, isolated):
    """What the run screen polls for before it navigates to the result."""
    db = isolated / "derivatives" / "runs.db"
    handle = _submit(client).json()["handle"]
    jobs.claim("worker-a", db)
    jobs.finish(handle, "ok", run_id="20260908_120000_psd_by_condition", db_path=db)

    body = client.get(f"/runs/status/{handle}").json()
    assert body["status"] == "ok"
    assert body["run_id"] == "20260908_120000_psd_by_condition"
    assert body["worker"] == "worker-a"


def test_the_queue_is_listed(client, isolated):
    _submit(client)
    _submit(client, claim="a second question")
    rows = client.get("/jobs").json()
    assert len(rows) == 2
    assert {row["status"] for row in rows} == {"queued"}
    assert client.get("/jobs?status=ok").json() == []


def test_the_background_executor_is_still_available(client, isolated, monkeypatch):
    """The dev fallback: in-process, and honest about not surviving a restart."""
    monkeypatch.setattr(api, "EXECUTOR", "background")
    body = _submit(client).json()
    assert body["executor"] == "background"
    assert body["handle"].startswith("pending_")
    assert jobs.get_job(body["handle"], isolated / "derivatives" / "runs.db") is None


# ---- health ------------------------------------------------------------------

def test_health_reports_versions_and_databases(client, isolated):
    body = client.get("/health").json()
    assert body["versions"]["python"]
    assert "numpy" in body["versions"]
    assert body["executor"] in {"queue", "background"}
    assert set(body["databases"]) == {"runs", "accounts"}
    assert body["queue"]["workers"] == 0


def test_health_is_not_ok_when_work_is_queued_and_no_worker_runs(client, isolated):
    """The state where the app looks fine and quietly does nothing."""
    assert client.get("/health").json()["queue"]["healthy"] is True
    _submit(client)
    body = client.get("/health").json()
    assert body["queue"]["healthy"] is False
    assert body["ok"] is False


def test_health_does_not_change_anything(client, isolated):
    """A monitoring endpoint that reaps jobs gives you state that depends on who looked."""
    db = isolated / "derivatives" / "runs.db"
    handle = _submit(client).json()["handle"]
    jobs.claim("worker-a", db)
    client.get("/health")
    assert jobs.get_job(handle, db)["status"] == "running"


# ---- the built front end -----------------------------------------------------

def test_no_build_means_no_mount(tmp_path):
    from fastapi import FastAPI

    assert api.mount_web(FastAPI(), tmp_path / "nothing-here") is False


def test_a_client_side_route_falls_back_to_index_html(tmp_path):
    """Reloading /qc/demo01 has to work; it is a route in one HTML file."""
    from fastapi import FastAPI

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>dbsspeech</title>")
    (dist / "assets" / "app.js").write_text("console.log('hi')")

    app_with_web = FastAPI()

    @app_with_web.get("/health")
    def health():  # noqa: ANN202 - test route
        return {"ok": True}

    assert api.mount_web(app_with_web, dist) is True
    web = TestClient(app_with_web)
    browser = {"accept": "text/html,application/xhtml+xml"}

    assert web.get("/health").json() == {"ok": True}   # API routes still win
    assert "dbsspeech" in web.get("/", headers=browser).text
    assert "dbsspeech" in web.get("/qc/demo01", headers=browser).text
    assert web.get("/assets/app.js").text == "console.log('hi')"
    # A missing asset must not come back as HTML pretending to be JavaScript.
    assert web.get("/assets/missing.js", headers=browser).status_code == 404


def test_the_served_app_does_not_let_the_api_shadow_a_screen(tmp_path):
    """The bug this exists to prevent: reloading /subjects returned JSON.

    With the API's routes at the root of the served application, four of the
    eight screens shared a path with a route: /subjects, /runs, /runs/<id> and
    /qc/<id>. A browser asking for the subjects page got the subjects endpoint,
    which is a wall of JSON. Development never showed it, because Vite serves
    the app there and proxies only /api onward.
    """
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>dbsspeech</title>")

    root = api.build_root(api.app, dist)
    client = TestClient(root)
    browser = {"accept": "text/html,application/xhtml+xml"}

    for path in ("/", "/subjects", "/runs", "/qc/demo01", "/compare"):
        body = client.get(path, headers=browser).text
        assert "dbsspeech" in body and "<title>" in body, f"{path} did not serve the app"

    # And the API is still reachable, one level down.
    assert client.get("/api/subjects").json()[0]["study_id"]
    assert client.get("/api/health").json()["package"]


def test_an_api_call_that_matches_no_route_is_a_404_not_a_page(tmp_path):
    """The mount is last, so it also catches API paths. It must not answer them.

    A fetch that gets index.html with a 200 is a wrong call that looks like a
    working one, and the error surfaces later as unparsable JSON.
    """
    from fastapi import FastAPI

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>dbsspeech</title>")

    app_with_web = FastAPI()
    api.mount_web(app_with_web, dist)
    web = TestClient(app_with_web)

    assert web.get("/runs/r1/tables/nope").status_code == 404
    assert web.get("/no/such/route").status_code == 404


# ---- files -------------------------------------------------------------------

def test_run_files_are_served_from_the_run_directory(client, isolated):
    out = isolated / "derivatives" / "results" / "r1"
    out.mkdir(parents=True)
    (out / "summary.json").write_text('{"ok": true}')
    r = client.get("/runs/r1/files/summary.json")
    assert r.status_code == 200


def test_a_path_escaping_the_run_directory_is_refused(client, isolated):
    """Containment is checked before the filesystem is touched."""
    out = isolated / "derivatives" / "results" / "r1"
    out.mkdir(parents=True)
    (isolated / "secret.txt").write_text("private")
    r = client.get("/runs/r1/files/%2e%2e%2f%2e%2e%2fsecret.txt")
    assert r.status_code in (400, 404)
    assert "private" not in r.text


def test_missing_file_is_404(client, isolated):
    (isolated / "derivatives" / "results" / "r1").mkdir(parents=True)
    assert client.get("/runs/r1/files/nope.csv").status_code == 404


# ---- uploads -----------------------------------------------------------------

def test_upload_stores_the_file_and_names_its_format(client, isolated):
    r = client.post("/uploads?study_id=S02&session=ses1",
                    files={"file": ("block.mat", b"\x89HDF\r\n\x1a\n" + b"0" * 64)})
    assert r.status_code == 201
    body = r.json()
    assert body["format"] == "tdt_mat"
    assert (isolated / "uploads" / "S02" / "ses1" / "block.mat").exists()


def test_upload_does_not_write_a_manifest_row(client, isolated):
    """The manifest is hand-curated; an upload is not a decision about channels."""
    body = client.post("/uploads?study_id=S02&session=ses1",
                       files={"file": ("block.mat", b"x" * 16)}).json()
    assert body["manifest_written"] is False
    assert body["next_steps"]


def test_unsupported_extension_is_refused_with_the_supported_list(client, isolated):
    r = client.post("/uploads?study_id=S02&session=ses1",
                    files={"file": ("notes.txt", b"hello")})
    assert r.status_code == 415
    assert ".mat" in r.json()["detail"]


def test_upload_over_the_size_limit_is_refused_and_cleaned_up(client, isolated, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 16)
    r = client.post("/uploads?study_id=S02&session=ses1",
                    files={"file": ("big.mat", b"x" * 4096)})
    assert r.status_code == 413
    assert not (isolated / "uploads" / "S02" / "ses1" / "big.mat").exists()


def test_uploaded_filename_cannot_contain_a_path(client, isolated):
    """A filename is a name, never a location."""
    client.post("/uploads?study_id=S02&session=ses1",
                files={"file": ("../../escape.mat", b"x" * 16)})
    assert not (isolated / "escape.mat").exists()


def test_listing_uploads(client, isolated):
    client.post("/uploads?study_id=S02&session=ses1",
                files={"file": ("block.mat", b"x" * 16)})
    listed = client.get("/uploads").json()
    assert listed[0]["format"] == "tdt_mat"


def test_openapi_documents_every_route(client):
    paths = client.get("/openapi.json").json()["paths"]
    for route in ("/subjects", "/recipes", "/runs", "/uploads", "/agent/propose", "/health"):
        assert route in paths


# ---- quality control ---------------------------------------------------------

def test_qc_detail_reports_status_and_counts(client):
    body = client.get("/qc/demo01").json()
    assert body["status"] in {"unreviewed", "in_review", "approved", "reopened"}
    assert "decisions" in body and "history" in body


def test_subjects_report_the_real_gate_status(client):
    """Not a placeholder: the page must show what the gate actually says."""
    subject = client.get("/subjects").json()[0]
    assert subject["qc_status"] == client.get("/qc/demo01").json()["status"]


def test_the_review_screen_is_told_what_a_flag_means(client):
    """Detector names are function names. A reviewer reads the lab's words."""
    body = client.get("/qc/vocabulary").json()
    assert body["detectors"]["kurtosis_outlier"]["label"] == "Spiky channel"
    assert "peaked" in body["detectors"]["kurtosis_outlier"]["means"]


def test_the_review_screen_is_told_what_may_be_done(client):
    """Including 'none': the flag is real and nothing should be removed."""
    actions = {a["value"]: a for a in client.get("/qc/vocabulary").json()["actions"]}
    assert "none" in actions
    assert actions["none"]["label"]
    assert "signal of interest" in actions["none"]["description"]
    assert set(actions) >= {"exclude_channel", "notch", "annotate_window", "none"}


def test_the_vocabulary_route_is_not_read_as_a_study_id(client):
    """`/qc/vocabulary` and `/qc/{study_id}` collide unless order is deliberate."""
    body = client.get("/qc/vocabulary").json()
    assert "actions" in body and "status" not in body


def test_a_bulk_decision_without_a_scope_is_refused(client):
    r = client.post("/qc/demo01/decisions/bulk",
                    json={"approved": True, "reviewer": "g"})
    assert r.status_code == 422
    assert "scope" in r.json()["detail"]


def test_a_decision_needs_a_reviewer(client):
    r = client.put("/qc/demo01/decisions",
                   json={"flag_id": "x", "approved": True, "reviewer": ""})
    assert r.status_code == 422


def test_rejecting_without_a_reason_is_refused_over_http(client, isolated):
    """The package rule reaches the API rather than being re-implemented there."""
    from dbsspeech.qc import Flag, propose

    propose([Flag("channel", "c1", "flat_channel", {}, "exclude_channel", "high")],
            "TMP", isolated / "derivatives")
    rows = client.get("/qc/TMP").json()["decisions"]
    r = client.put("/qc/TMP/decisions", json={
        "flag_id": rows[0]["flag_id"], "approved": False, "reviewer": "g", "reason": ""})
    assert r.status_code == 422
    assert "reason" in r.json()["detail"]


def test_signing_with_undecided_flags_is_a_conflict(client, isolated):
    from dbsspeech.qc import Flag, propose

    propose([Flag("channel", "c1", "flat_channel", {}, "exclude_channel", "high")],
            "TMP", isolated / "derivatives")
    r = client.post("/qc/TMP/sign", json={"reviewer": "g"})
    assert r.status_code == 409
    assert "undecided" in r.json()["detail"]


def test_a_full_review_pass_over_http(client, isolated):
    """Decide, sign, and the status becomes approved."""
    from dbsspeech.qc import Flag, propose

    propose([Flag("channel", "c1", "flat_channel", {}, "exclude_channel", "high")],
            "TMP", isolated / "derivatives")
    flag_id = client.get("/qc/TMP").json()["decisions"][0]["flag_id"]
    client.put("/qc/TMP/decisions",
               json={"flag_id": flag_id, "approved": True, "reviewer": "garrett"})
    signed = client.post("/qc/TMP/sign", json={"reviewer": "garrett"})
    assert signed.status_code == 200
    assert signed.json()["status"] == "approved"


def test_reopening_requires_a_reason(client, isolated):
    r = client.post("/qc/TMP/reopen", json={"reviewer": "g", "reason": ""})
    assert r.status_code == 422


def test_missing_report_is_404(client, isolated):
    assert client.get("/qc/NOPE/report").status_code == 404


# ---- compare -----------------------------------------------------------------

def _write_run(isolated, run_id, **overrides):
    import json

    record = {
        "run_id": run_id, "name": "psd_by_condition", "claim": "a claim",
        "status": "ok", "git_commit": "abc123", "git_dirty": False,
        "params": {"fmin": 1.0, "fmax": 200.0, "method": "welch"},
        "outputs": ["psd_db.png", "summary.json"], "summary": {},
        "guardrails": {}, "versions": {},
    }
    record.update(overrides)
    (isolated / "runs" / f"{run_id}.json").write_text(json.dumps(record))
    return record


def test_compare_reports_only_the_changed_parameters(client, isolated):
    _write_run(isolated, "r1")
    _write_run(isolated, "r2", params={"fmin": 1.0, "fmax": 150.0, "method": "welch"})
    body = client.get("/compare?a=r1&b=r2").json()
    changed = [row["param"] for row in body["params"] if row["changed"]]
    assert changed == ["fmax"]
    assert body["n_changed"] == 1


def test_compare_flags_different_recipes(client, isolated):
    """Not a like-for-like comparison, and the page must say so."""
    _write_run(isolated, "r1")
    _write_run(isolated, "r2", name="bandpower_contrast")
    assert client.get("/compare?a=r1&b=r2").json()["same_recipe"] is False


def test_compare_flags_different_code_versions(client, isolated):
    """The difference may be the code rather than the parameters."""
    _write_run(isolated, "r1")
    _write_run(isolated, "r2", git_commit="def456")
    assert client.get("/compare?a=r1&b=r2").json()["same_code"] is False


def test_compare_matches_figures_by_filename(client, isolated):
    _write_run(isolated, "r1", outputs=["psd_db.png", "only_in_a.png"])
    _write_run(isolated, "r2", outputs=["psd_db.png", "only_in_b.png"])
    assert client.get("/compare?a=r1&b=r2").json()["shared_figures"] == ["psd_db.png"]


def test_compare_with_an_unknown_run_is_404(client, isolated):
    _write_run(isolated, "r1")
    assert client.get("/compare?a=r1&b=nope").status_code == 404


def test_a_parameter_present_in_only_one_run_is_shown(client, isolated):
    _write_run(isolated, "r1", params={"fmin": 1.0})
    _write_run(isolated, "r2", params={"fmin": 1.0, "unit": "pseudo_epoch"})
    row = next(r for r in client.get("/compare?a=r1&b=r2").json()["params"]
               if r["param"] == "unit")
    assert row["a"] is None and row["b"] == "pseudo_epoch" and row["changed"]


def test_table_paging_returns_a_slice(client, isolated):
    out = isolated / "derivatives" / "results" / "r1"
    out.mkdir(parents=True)
    (out / "stats.csv").write_text("a,b\n" + "\n".join(f"{i},{i*2}" for i in range(50)))
    body = client.get("/runs/r1/tables/stats?limit=10&offset=5").json()
    assert body["n_rows"] == 50
    assert len(body["rows"]) == 10
    assert body["rows"][0] == {"a": 5, "b": 10}


def test_table_path_cannot_escape_the_run_directory(client, isolated):
    out = isolated / "derivatives" / "results" / "r1"
    out.mkdir(parents=True)
    (isolated / "secret.csv").write_text("x\n1")
    assert client.get("/runs/r1/tables/..%2F..%2Fsecret").status_code == 404


def test_unknown_table_is_404(client, isolated):
    (isolated / "derivatives" / "results" / "r1").mkdir(parents=True)
    assert client.get("/runs/r1/tables/nope").status_code == 404


# ---- authentication ----------------------------------------------------------

def test_auth_is_off_by_default_so_local_work_is_unchanged(client):
    body = client.get("/auth/me").json()
    assert body["auth_required"] is False
    assert body["user"]["role"] == "admin"


def test_serve_refuses_a_public_bind_without_auth():
    """The failure mode worth preventing: an unauthenticated app on a network."""
    from dbsspeech.api.main import serve

    with pytest.raises(RuntimeError, match="refusing to bind"):
        serve(host="0.0.0.0", port=8000)


def test_serve_permits_localhost_without_auth(monkeypatch):
    import sys
    import types

    from dbsspeech.api import main as api_main

    called: dict = {}
    stub = types.ModuleType("uvicorn")
    stub.run = lambda app, **kwargs: called.update(kwargs)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", stub)

    api_main.serve(host="127.0.0.1", port=8123)
    assert called == {"host": "127.0.0.1", "port": 8123}


def test_role_checks_say_what_is_needed_and_what_you_have(monkeypatch, client):
    from dbsspeech.api import main as api_main
    from dbsspeech.auth import User

    monkeypatch.setattr(api_main, "REQUIRE_AUTH", True)
    monkeypatch.setattr(api_main, "LOCAL_USER", User(0, "r", "r@x.org", "reviewer"))
    api_main.app.dependency_overrides[api_main.current_user] = lambda: User(
        0, "r", "r@x.org", "reviewer"
    )
    try:
        r = client.post("/runs", json={
            "recipe": "psd_by_condition", "study_id": "demo01",
            "session": "ses1", "claim": "c"})
        assert r.status_code == 403
        assert "analyst" in r.json()["detail"]
        assert "reviewer" in r.json()["detail"]
    finally:
        api_main.app.dependency_overrides.clear()


def test_an_unauthenticated_request_is_401_when_auth_is_on(monkeypatch, client):
    from dbsspeech.api import main as api_main

    monkeypatch.setattr(api_main, "REQUIRE_AUTH", True)
    assert client.get("/auth/me").status_code == 401


def test_a_bad_login_does_not_reveal_whether_the_email_exists(monkeypatch, client, tmp_path):
    from dbsspeech.api import main as api_main

    monkeypatch.setattr(api_main, "REQUIRE_AUTH", True)
    r = client.post("/auth/login", json={"email": "nobody@x.org", "password": "x" * 12})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid email or password"


# ---- endpoints that write, and the roles they require ------------------------
#
# Two writes had no role at all. Both were found by a security pass, not by a
# test, so each gets one here: the failure mode is silent and the fix is a single
# decorator argument that a later refactor can drop again.

def _auth_on(monkeypatch):
    from dbsspeech.api import main as api_main

    monkeypatch.setattr(api_main, "REQUIRE_AUTH", True)


def test_bulk_qc_decisions_require_a_reviewer(monkeypatch, client):
    """R1. Every other QC write required a reviewer. This one required nothing,
    and it is the write that decides many flags at once."""
    _auth_on(monkeypatch)
    r = client.post(
        "/qc/demo01/decisions/bulk",
        json={"approved": True, "severity": "low", "reviewer": "anon"},
    )
    assert r.status_code == 401, r.text


def test_uploading_requires_a_role(monkeypatch, client, isolated):
    """R2. An anonymous write into data/, which is the synced folder."""
    _auth_on(monkeypatch)
    r = client.post(
        "/uploads",
        params={"study_id": "demo01", "session": "ses1"},
        files={"file": ("block.vhdr", b"x", "application/octet-stream")},
    )
    assert r.status_code == 401, r.text


def test_listing_uploads_requires_a_role(monkeypatch, client, isolated):
    _auth_on(monkeypatch)
    assert client.get("/uploads").status_code == 401


@pytest.mark.parametrize(
    "study_id",
    ["../../etc", "..", "a/b", ".", "", "x" * 65, "with space", "dot.dot"],
)
def test_an_upload_path_cannot_leave_the_upload_area(client, isolated, study_id):
    """The filename was reduced to its basename; the directory components were
    not. `study_id='../../..'` resolved out of the upload area entirely."""
    before = {p for p in isolated.rglob("*") if p.is_file()}
    r = client.post(
        "/uploads",
        params={"study_id": study_id, "session": "ses1"},
        files={"file": ("block.vhdr", b"x", "application/octet-stream")},
    )
    assert r.status_code == 422, f"{study_id!r} gave {r.status_code}: {r.text}"
    after = {p for p in isolated.rglob("*") if p.is_file()}
    assert before == after, "a rejected upload still wrote something"


def test_a_legitimate_upload_still_works(client, isolated):
    r = client.post(
        "/uploads",
        params={"study_id": "demo01", "session": "ses1"},
        files={"file": ("block.vhdr", b"x" * 32, "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["manifest_written"] is False
    assert body["bytes"] == 32

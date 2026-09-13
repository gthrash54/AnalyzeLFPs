"""Test the educational curriculum notebooks and mathematical claims in CI.

Ensures that:
1. Notebook files in curriculum/ and web/public/notebooks/ are in sync.
2. The solutions notebook executes end-to-end with verified mathematical assertions.
3. The non-circular duality proof, matched filter, and DC trap behave as claimed.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path

import matplotlib
import numpy as np
import pytest

# The notebooks call plt.show(). The default backend on a workstation is
# interactive (qtagg here), so plt.show() blocks until a human closes a window
# and the suite hangs forever instead of failing. Force a non-interactive
# backend before any exec'd cell imports pyplot.
matplotlib.use("Agg")

REPO_ROOT = Path(__file__).resolve().parents[2]
CURRICULUM_ROOT = REPO_ROOT / "curriculum"
CURRICULUM_DIR = CURRICULUM_ROOT / "01_linear_algebra"
DSP_DIR = CURRICULUM_ROOT / "02_dsp"
PREPROC_DIR = CURRICULUM_ROOT / "03_preprocessing"
LINALG_DIR = CURRICULUM_DIR

ALL_SOLUTIONS = sorted(CURRICULUM_ROOT.rglob("*_solutions.ipynb"))
GUARDRAILS_DIR = CURRICULUM_ROOT / "07_guardrails"
INFERENCE_DIR = CURRICULUM_ROOT / "08_inference"
DECODING_DIR = CURRICULUM_ROOT / "09_decoding"
STOCHASTIC_DIR = CURRICULUM_ROOT / "10_stochastic"
SPATIAL_DIR = CURRICULUM_ROOT / "03_spatial"
PUBLIC_DIR = REPO_ROOT / "web" / "public" / "notebooks"


# Executing 46 solutions notebooks once each is already a few minutes. Several
# tests want the namespace of the same notebook, so cache it: without this the
# suite re-runs notebooks a dozen times and people stop running it.
_NOTEBOOK_CACHE: dict[str, tuple[dict, str]] = {}


def _execute_notebook(path: Path) -> tuple[dict, str]:
    """Run every code cell once, returning (namespace, everything it printed).

    Cached per session, and the printed text is cached with the namespace. Two
    tests want the same notebook for different reasons: the assertion tests want
    its variables, and test_ui_numbers_still_match_what_the_notebooks_print wants
    its stdout. Caching only the namespace made the second one re-execute every
    stemmed notebook, which doubled the cost of the slowest lessons.
    """
    key = str(path)
    if key not in _NOTEBOOK_CACHE:
        nb_data = json.loads(path.read_text())
        namespace: dict = {}
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            for idx, cell in enumerate(nb_data["cells"]):
                if cell["cell_type"] != "code":
                    continue
                code = "".join(cell["source"])
                try:
                    exec(code, namespace)
                except Exception as exc:
                    pytest.fail(f"{path.name} cell {idx} failed: {exc}\nCode:\n{code[:300]}")
        _NOTEBOOK_CACHE[key] = (namespace, buffer.getvalue())
    return _NOTEBOOK_CACHE[key]


def run_notebook(path: Path) -> dict:
    """Execute every code cell of a notebook and return the resulting namespace.

    Cached per session. The returned dict is a shallow copy, so a test that
    rebinds a name cannot affect another test.
    """
    return dict(_execute_notebook(path)[0])


def notebook_stdout(path: Path) -> str:
    """Everything a notebook printed, from the same cached execution."""
    return _execute_notebook(path)[1]


# The eleven courses, and how many lessons each one has. This is the only place the
# shape of the curriculum is written down as data, and the tests below read it.
COURSES = {
    "STO": ("Probability and Stochastic Processes for Neural Data", 4),
    "LIN": ("Applied Linear Algebra for Neural Arrays", 6),
    "SIG": ("Signal Processing for Neural Time Series", 6),
    "REC": ("Recording Physics and Electrode Geometry", 5),
    "PRE": ("The Preprocessing Contract", 1),
    "SPK": ("Spike Trains and Single-Unit Activity", 4),
    "POP": ("Population Dynamics and Latent Structure", 3),
    "CON": ("Connectivity and Spectral Coupling", 4),
    "GRL": ("Closed-Loop Neuromodulation and Scientific Guardrails", 5),
    "INF": ("Statistical Inference for Neural Recordings", 3),
    "DEC": ("Machine Learning and Neural Decoding", 5),
}
VALID_LESSONS = {f"{c} {n}" for c, (_, k) in COURSES.items() for n in range(1, k + 1)}
CITATION = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(COURSES) + r")\s?(\d+)")


@pytest.mark.unit
def test_every_lesson_citation_points_at_a_lesson_that_exists():
    """A citation to a lesson that does not exist is a dead reference in prose.

    The lessons cite each other constantly: "SIG 3 established that", "what LIN 4
    measured". Nothing checked that those pointed anywhere real, so a renumbering
    or a deleted lesson would leave the claim sitting there reading perfectly
    well. This is the check that makes the cross-references load-bearing.
    """
    broken: list[str] = []
    for path in sorted(CURRICULUM_ROOT.rglob("*.ipynb")):
        nb = json.loads(path.read_text())
        for i, cell in enumerate(nb["cells"]):
            source = "".join(cell["source"])
            for match in CITATION.finditer(source):
                cite = f"{match.group(1)} {match.group(2)}"
                if cite not in VALID_LESSONS:
                    context = source[max(0, match.start() - 40):match.end() + 40]
                    broken.append(f"{path.name} cell {i}: {cite!r} in ...{context.strip()}...")

    assert not broken, "citations pointing at lessons that do not exist:\n" + "\n".join(
        broken[:20]
    )


@pytest.mark.unit
def test_no_lesson_has_both_a_bespoke_page_and_a_registry_entry():
    """A lesson is rendered one way or the other, never both.

    Learn.tsx checks for a bespoke page first, so a registry entry for the same
    lesson is unreachable. CON 1 had both, and the dead entry was still being
    validated by the numeric-drift test: its numbers were kept honest while never
    being shown to anyone. Dead content that looks live is worse than no content,
    because it reads as covered.
    """
    learn = (REPO_ROOT / "web" / "src" / "pages" / "Learn.tsx").read_text()
    registry = (REPO_ROOT / "web" / "src" / "pages" / "learn" / "registry.ts").read_text()

    bespoke = set(re.findall(r'selectedLesson === "([A-Z]{3} \d+)"', learn))
    in_registry = set(re.findall(r'^\s{2}"([A-Z]{3} \d+)":', registry, re.M))
    both = bespoke & in_registry
    assert not both, (
        f"these lessons have a bespoke page AND a registry entry, so the entry is "
        f"dead code: {sorted(both)}"
    )
    assert bespoke | in_registry == VALID_LESSONS, (
        f"unrendered: {sorted(VALID_LESSONS - bespoke - in_registry)}; "
        f"rendered but not a lesson: {sorted(bespoke | in_registry - VALID_LESSONS)}"
    )


@pytest.mark.unit
def test_no_lesson_uses_a_retired_citation_style():
    """The citation check above can only see citations it recognises.

    When lessons were renamed to course tags, a second and older citation style
    survived untouched: LIN 1 to LIN 3 were also cited as "Module 01", "Module
    02" and "Module 03", and 82 of those were left pointing at a naming scheme
    that no longer existed. One sentence ended up reading "the conclusion Module
    02, LIN 4 and PRE 1 reached", mixing both styles in a single list.

    test_every_lesson_citation_points_at_a_lesson_that_exists could not catch it,
    because it matches the course tags and "Module 02" contains none. A checker
    that only recognises the current syntax is blind to exactly the references a
    rename strands, so this test bans the retired spellings outright.
    """
    retired = {
        "Module 0": "lessons are cited by course tag, as in LIN 3",
        "Track 0": "the curriculum has courses and groups, not numbered tracks",
    }
    # The notebooks are not the only place a citation lives. The Learn page and
    # the notebook-module registry cite lessons too, in prose a reader sees
    # without opening a notebook, and scanning only curriculum/ left four "Track
    # 0N" references alive there for a full audit cycle. A rename guard that
    # skips the interface is the same blind spot this test exists to close.
    learn_dir = REPO_ROOT / "web" / "src" / "pages" / "learn"
    scanned = sorted(CURRICULUM_ROOT.rglob("*.ipynb"))
    scanned += [REPO_ROOT / "web" / "src" / "pages" / "Learn.tsx"]
    scanned += sorted(learn_dir.glob("*.ts*"))

    found: list[str] = []
    for path in scanned:
        text = path.read_text()
        for token, why in retired.items():
            if token in text:
                found.append(f"{path.name}: {token!r} ({why})")
    assert not found, "retired citation styles still in use:\n" + "\n".join(found[:20])


@pytest.mark.unit
def test_the_learn_ui_and_the_tests_agree_on_which_lessons_exist():
    """One definition of the curriculum's shape, checked against the interface.

    COURSES above is the test suite's idea of what exists; Learn.tsx is the
    interface's. If they disagree, one of them is shipping a lesson the other has
    never heard of.
    """
    page = (REPO_ROOT / "web" / "src" / "pages" / "Learn.tsx").read_text()
    in_ui = set(re.findall(r'id: "([A-Z]{3} \d+)"', page))
    assert in_ui == VALID_LESSONS, (
        f"only in the UI: {sorted(in_ui - VALID_LESSONS)}; "
        f"only in the tests: {sorted(VALID_LESSONS - in_ui)}"
    )


@pytest.mark.unit
def test_curriculum_notebook_filenames_are_unique_across_tracks():
    """The public mirror is flat, so two tracks may not share a filename.

    `web/public/notebooks/` keys every notebook by bare filename. Nothing about
    that layout announces itself, and a collision would silently overwrite one
    module with another rather than failing, so the constraint is asserted here
    instead of being left to whoever next adds a track.
    """
    names: dict[str, list[str]] = {}
    for path in CURRICULUM_ROOT.rglob("*.ipynb"):
        names.setdefault(path.name, []).append(str(path.relative_to(CURRICULUM_ROOT)))
    collisions = {n: v for n, v in names.items() if len(v) > 1}
    assert not collisions, f"the flat public mirror needs unique filenames: {collisions}"


@pytest.mark.unit
def test_notebook_sync_between_curriculum_and_public():
    """Every curriculum notebook must be mirrored byte for byte into web/public.

    Discovered by walking `curriculum/`, so adding a track or a module needs no
    edit here. The two trees are copied by hand with no build step, which is
    exactly why this has to be enforced rather than assumed.
    """
    notebooks = sorted(CURRICULUM_ROOT.rglob("*.ipynb"))
    assert notebooks, "no curriculum notebooks found at all"
    for curr_file in notebooks:
        filename = curr_file.name
        pub_file = PUBLIC_DIR / filename
        assert pub_file.exists(), f"Missing {pub_file}"
        assert curr_file.read_bytes() == pub_file.read_bytes(), f"Desynchronized: {filename}"


@pytest.mark.unit
def test_module_01_solutions_notebook_execution():
    """Execute the Module 01 solutions notebook and verify its mathematical
    assertions."""
    solutions_path = CURRICULUM_DIR / "01_vectors_and_dot_products_solutions.ipynb"
    assert solutions_path.exists()

    nb_data = json.loads(solutions_path.read_text())
    namespace: dict = {}

    for idx, cell in enumerate(nb_data["cells"]):
        if cell["cell_type"] == "code":
            code = "".join(cell["source"])
            try:
                exec(code, namespace)
            except Exception as exc:
                pytest.fail(
                    f"Cell {idx} failed during execution: {exc}\n"
                    f"Code snippet:\n{code[:200]}"
                )

    # Verify namespace contains key tested symbols
    assert "compute_vector_norm" in namespace
    assert "compute_dot_product" in namespace
    assert "compute_cosine_similarity" in namespace
    assert "compute_pearson_correlation" in namespace

    # Verify honest non-circular duality
    vec_a = np.array([30.0, 40.0])
    vec_b = np.array([50.0, 10.0])
    alg_dot = namespace["compute_dot_product"](vec_a, vec_b)
    theta_a = np.arctan2(vec_a[1], vec_a[0])
    theta_b = np.arctan2(vec_b[1], vec_b[0])
    theta_trig = np.abs(theta_b - theta_a)
    geom_dot = (
        namespace["compute_vector_norm"](vec_a)
        * namespace["compute_vector_norm"](vec_b)
        * np.cos(theta_trig)
    )
    assert np.isclose(alg_dot, geom_dot)

    # Verify zero-norm handling
    zero_vec = np.array([0.0, 0.0])
    assert np.isnan(namespace["compute_cosine_similarity"](vec_a, zero_vec))

    # Verify matched filter spike detection count
    matched_trace = namespace.get("matched_filter_trace")
    assert matched_trace is not None
    assert len(matched_trace) == 956  # 1000 - 45 + 1
    assert np.sum(matched_trace > 15.0) >= 3

    # Verify DC offset trap numbers
    false_sim = namespace.get("false_sim")
    true_r = namespace.get("true_r")
    assert false_sim > 0.95
    assert abs(true_r) < 0.15


@pytest.mark.unit
def test_module_02_solutions_notebook_execution():
    """Execute the Module 02 solutions notebook and verify its montage linear
    algebra."""
    solutions_path = CURRICULUM_DIR / "02_matrices_and_montages_solutions.ipynb"
    assert solutions_path.exists()

    nb_data = json.loads(solutions_path.read_text())
    namespace: dict = {}

    for idx, cell in enumerate(nb_data["cells"]):
        if cell["cell_type"] == "code":
            code = "".join(cell["source"])
            try:
                exec(code, namespace)
            except Exception as exc:
                pytest.fail(
                    f"Cell {idx} failed during execution: {exc}\n"
                    f"Code snippet:\n{code[:200]}"
                )

    # Verify linear algebraic operators exist
    assert "build_vertical_bipolar_matrix" in namespace
    assert "build_car_matrix" in namespace

    # Test directional DBS bipolar montage matrix (1-3-3-1 lead)
    M_vert = namespace["build_vertical_bipolar_matrix"]()
    assert M_vert.shape == (7, 8)
    assert np.all(np.sum(M_vert, axis=1) == 0)  # Each bipolar derivation must sum to 0

    # Test CAR projection matrix
    for C in [4, 8, 64, 128]:
        M_car = namespace["build_car_matrix"](C)
        assert M_car.shape == (C, C)
        # Idempotence: M^2 = M
        assert np.allclose(M_car @ M_car, M_car)
        # Symmetry: M^T = M
        assert np.allclose(M_car.T, M_car)
        # Row sums are zero: M @ 1 = 0
        assert np.allclose(np.sum(M_car, axis=1), 0)
        # Rank deficiency: rank(M_car) = C - 1
        assert np.linalg.matrix_rank(M_car) == C - 1


@pytest.mark.unit
def test_module_03_solutions_notebook_execution():
    """Execute the Module 03 solutions notebook and verify its condition number
    and inversion math."""
    solutions_path = CURRICULUM_DIR / "03_matrix_inverses_conditioning_solutions.ipynb"
    assert solutions_path.exists()

    nb_data = json.loads(solutions_path.read_text())
    namespace: dict = {}

    for idx, cell in enumerate(nb_data["cells"]):
        if cell["cell_type"] == "code":
            code = "".join(cell["source"])
            try:
                exec(code, namespace)
            except Exception as exc:
                pytest.fail(
                    f"Cell {idx} failed during execution: {exc}\n"
                    f"Code snippet:\n{code[:200]}"
                )

    # Verify operators exist in namespace
    assert "compute_condition_number" in namespace
    assert "build_leadfield_matrix" in namespace
    assert "solve_inverse_tikhonov" in namespace

    # Verify condition number behavior
    k_wide = namespace.get("k_wide")
    k_dense = namespace.get("k_dense")
    assert k_wide is not None and k_dense is not None
    assert k_wide < 100.0
    assert k_dense > 1000.0

    # Verify noise catastrophe and Tikhonov stabilization
    err_ols = namespace.get("err_ols")
    err_ridge = namespace.get("err_ridge")
    assert err_ols is not None and err_ridge is not None
    assert err_ols > 2.0  # >200% error due to multicollinearity
    assert err_ridge < 1.0  # <100% error after ridge regularization
    assert err_ridge < (err_ols / 3.0)  # >3x error reduction


@pytest.mark.unit
def test_module_s1_solutions_notebook_execution():
    """Execute Module SIG 1 and verify its sampling, quantization and folding claims."""
    ns = run_notebook(DSP_DIR / "01_sampling_nyquist_aliasing_solutions.ipynb")

    for symbol in ("alias_frequency", "effective_bits", "fold_harmonics", "usable_bandwidth_hz"):
        assert symbol in ns, f"Module SIG 1 must define {symbol}"

    alias_frequency = ns["alias_frequency"]

    # Folding is checked against the samples, never against the formula itself:
    # a cosine at f and a cosine at its alias must be sample-for-sample equal.
    fs = 1000.0
    t = np.arange(2000) / fs
    for f_true in (1300.0, 1700.0, 990.0, 4321.0):
        f_alias = alias_frequency(f_true, fs)
        assert 0.0 <= f_alias <= fs / 2.0
        assert np.allclose(
            np.cos(2 * np.pi * f_true * t), np.cos(2 * np.pi * f_alias * t), atol=1e-9
        ), f"{f_true} Hz and its alias {f_alias} Hz do not share samples"
    assert alias_frequency(20.0, 1000.0) == 20.0

    # A 50 uV LFP inside a +/-1 V range is starved of bits.
    assert ns["effective_bits"](50e-6, 1.0, 16) < 6.0
    assert ns["effective_bits"](1.0, 1.0, 16) == 16.0

    # The worked clinical example: 135 Hz stimulation sampled at 250 Hz puts its
    # second harmonic at 20 Hz, in the middle of beta.
    assert ns["fold_harmonics"](135.0, 250.0)[2] == 20.0


@pytest.mark.unit
def test_module_s1_matches_the_package_and_the_configs():
    """SIG 1 is standalone by design, so its constants are checked against their sources.

    The notebook restates the beta band and reimplements usable bandwidth so a
    downloaded copy runs with no repository. That is only safe while the restated
    values still agree with `configs/bands.yaml` and with the function guardrail
    G6 actually reads.
    """
    import yaml

    from dbsspeech.preprocess.resample import usable_bandwidth_hz as package_impl

    ns = run_notebook(DSP_DIR / "01_sampling_nyquist_aliasing_solutions.ipynb")

    notebook_beta = tuple(float(x) for x in ns["BETA_BAND_HZ"])
    bands = yaml.safe_load((REPO_ROOT / "configs" / "bands.yaml").read_text())["bands"]
    config_beta = tuple(float(x) for x in bands["beta"])
    assert notebook_beta == config_beta, (
        f"SIG 1 teaches beta as {notebook_beta} but configs/bands.yaml says {config_beta}"
    )

    for sfreq in (250.0, 500.0, 1000.0, 2000.0):
        assert ns["usable_bandwidth_hz"](sfreq) == package_impl(sfreq), (
            "SIG 1 must agree with dbsspeech.preprocess.resample.usable_bandwidth_hz"
        )


@pytest.mark.unit
def test_module_s2_solutions_notebook_execution():
    """Execute Module SIG 2 and verify its filtering claims independently."""
    ns = run_notebook(DSP_DIR / "02_filtering_zero_phase_solutions.ipynb")

    for symbol in ("apply_fir", "apply_iir", "measured_delay_samples", "zero_phase_filter"):
        assert symbol in ns, f"Module SIG 2 must define {symbol}"

    from scipy.signal import butter, lfilter

    apply_fir = ns["apply_fir"]
    apply_iir = ns["apply_iir"]
    zero_phase_filter = ns["zero_phase_filter"]

    rng = np.random.default_rng(11)
    x = rng.standard_normal(300)

    # FIR against convolution, which is the definition rather than a restatement.
    b = np.array([0.3, -0.4, 0.15, 0.05])
    assert np.allclose(apply_fir(x, b), np.convolve(x, b)[: len(x)])

    # IIR against scipy. Direct-form arithmetic on a narrow band drifts, so this is
    # a relative tolerance rather than machine precision; see the notebook.
    b_bp, a_bp = butter(4, [13.0, 30.0], btype="band", fs=1000.0)
    ref = lfilter(b_bp, a_bp, x)
    rel = np.max(np.abs(apply_iir(x, b_bp, a_bp) - ref)) / np.max(np.abs(ref))
    assert rel < 1e-5, f"apply_iir drifted from scipy.signal.lfilter by {rel:.2e}"

    # Forward-backward filtering has zero phase, which is the entire claim.
    tone = np.sin(2 * np.pi * 25.0 * np.arange(2000) / 1000.0)
    assert ns["measured_delay_samples"](tone, zero_phase_filter(tone, b_bp, a_bp)) == 0
    assert ns["measured_delay_samples"](tone, apply_iir(tone, b_bp, a_bp)) > 0

    # ... and it squares the magnitude response.
    mid = slice(500, 1500)
    single = np.sqrt(2 * np.mean(apply_iir(tone, b_bp, a_bp)[mid] ** 2))
    double = np.sqrt(2 * np.mean(zero_phase_filter(tone, b_bp, a_bp)[mid] ** 2))
    assert np.isclose(double, single**2, rtol=0.05)

    # The clinical point: a causal filter reports a late onset, and a narrower
    # band reports a later one.
    assert ns["causal_errors"]["beta 13-30"] > 30.0
    assert ns["causal_errors"]["narrow 18-22"] > ns["causal_errors"]["beta 13-30"]

    # The counterpart: zero-phase filtering can place an onset before the event.
    assert ns["zp_errors"]["theta 4-8"] < -50.0


@pytest.mark.unit
def test_module_p1_solutions_notebook_execution():
    """Execute the preprocessing capstone and verify its claims independently."""
    ns = run_notebook(PREPROC_DIR / "01_preprocessing_contract_solutions.ipynb")

    for symbol in ("apply_montage", "flag_artifacts", "plan_decimation"):
        assert symbol in ns, f"Module PRE 1 must define {symbol}"

    apply_montage = ns["apply_montage"]
    flag_artifacts = ns["flag_artifacts"]
    m_vert = ns["M_VERT"]

    # The commutation claim, re-derived here rather than read off the notebook.
    from scipy.signal import decimate

    rng = np.random.default_rng(21)
    data = rng.standard_normal((8, 4800)) + 500.0 * np.sin(
        2 * np.pi * 130.0 * np.arange(4800) / 2400.0
    )
    kw = {"ftype": "iir", "zero_phase": True, "axis": 1}
    a = decimate(apply_montage(data, m_vert), 6, **kw)
    b = apply_montage(decimate(data, 6, **kw), m_vert)
    assert np.max(np.abs(a - b)) / np.max(np.abs(a)) < 1e-9, "these must commute"

    # A montage that cancels common mode must hide a common-mode artifact entirely,
    # and must spread an artifact sitting on the contact four derivations reference.
    base = rng.standard_normal((8, 4000))
    common = base.copy()
    common[:, 1000:1100] += 30.0
    assert flag_artifacts(common)[1000:1100].mean() > 0.9
    assert apply_montage(common, m_vert)[:, 1000:1100].std() < 5.0

    ring = base.copy()
    ring[0, 2000:2100] += 30.0
    affected = np.sum(np.abs(apply_montage(ring, m_vert)[:, 2000:2100]).max(axis=1) > 15.0)
    assert affected == 4, f"contact 0 references four derivations, got {affected}"

    # Preprocessing never deletes samples. This is a CLAUDE.md hard rule.
    assert ns["record"]["n_samples_deleted"] == 0


@pytest.mark.unit
def test_module_p1_matches_the_package():
    """PRE 1 restates resample.py so it runs standalone; the two must not drift."""
    from dbsspeech.preprocess.resample import (
        suggest_factor,
    )
    from dbsspeech.preprocess.resample import (
        usable_bandwidth_hz as package_usable,
    )

    ns = run_notebook(PREPROC_DIR / "01_preprocessing_contract_solutions.ipynb")
    plan_decimation = ns["plan_decimation"]

    for sfreq, target in ((24000.0, 1000.0), (24414.0, 500.0), (24000.0, 250.0), (2000.0, 700.0)):
        plan = plan_decimation(sfreq, target, (13.0, 30.0))
        assert plan["factor"] == suggest_factor(sfreq, target), (
            f"PRE 1 disagrees with resample.suggest_factor at {sfreq}/{target}"
        )
        assert plan["usable_bandwidth_hz"] == package_usable(plan["new_sfreq_hz"]), (
            "PRE 1 must agree with resample.usable_bandwidth_hz"
        )

    # The G6 refusal must fire exactly when the band tops the usable bandwidth.
    assert plan_decimation(24000.0, 250.0, (70.0, 150.0))["refusal"] is not None
    assert plan_decimation(24000.0, 1000.0, (70.0, 150.0))["refusal"] is None


@pytest.mark.unit
@pytest.mark.parametrize("path", ALL_SOLUTIONS, ids=lambda p: p.stem)
def test_every_solutions_notebook_executes(path):
    """Discovered, not enumerated, so a new module is covered the moment it lands.

    Each notebook's own test cells do the asserting; this only guarantees they run.
    """
    run_notebook(path)


@pytest.mark.unit
def test_module_l4_covariance_claims():
    """LIN 4's volume-conduction and common-mode results, re-derived here."""
    ns = run_notebook(LINALG_DIR / "04_covariance_volume_conduction_solutions.ipynb")
    for sym in ("sample_covariance", "predicted_covariance", "common_mode_fraction",
                "shrink_covariance"):
        assert sym in ns, f"LIN 4 must define {sym}"

    sample_covariance = ns["sample_covariance"]
    rng = np.random.default_rng(31)

    # Bessel's correction, checked against numpy rather than against the notebook.
    X = rng.standard_normal((5, 2000))
    assert np.allclose(sample_covariance(X), np.cov(X))

    # The headline: uncorrelated sources, correlated contacts. Rebuilt from scratch.
    contact = np.linspace(0, 7.0, 8)
    source = np.array([1.0, 3.5, 6.0])
    A = 1.0 / (1.0 + np.abs(contact[:, None] - source[None, :]) ** 2)
    S = rng.standard_normal((3, 80000)) * np.array([[2.0], [1.0], [1.5]])
    Xm = A @ S
    src_corr = np.abs(np.corrcoef(S)[~np.eye(3, dtype=bool)]).max()
    ch_corr = np.abs(np.corrcoef(Xm)[~np.eye(8, dtype=bool)])
    assert src_corr < 0.02, "sources must be uncorrelated for the claim to mean anything"
    assert np.median(ch_corr) > 0.3, "geometry alone correlates the contacts"

    # A shared reference drives the common-mode fraction toward 1.
    ref = 10.0 * rng.standard_normal(80000)
    assert ns["common_mode_fraction"](sample_covariance(Xm + ref)) > 0.9
    assert ns["common_mode_fraction"](sample_covariance(Xm)) < 0.9

    # Shrinkage preserves total variance and fixes conditioning.
    C_bad = sample_covariance(rng.standard_normal((32, 16)))
    C_fix = ns["shrink_covariance"](C_bad, 0.1)
    assert np.isclose(np.trace(C_fix), np.trace(C_bad))
    assert np.linalg.cond(C_fix) < 1e-6 * np.linalg.cond(C_bad)


@pytest.mark.unit
def test_module_l5_pca_recovers_a_subspace_not_sources():
    """The rotation ambiguity is LIN 5's point; verify it independently of the notebook."""
    ns = run_notebook(LINALG_DIR / "05_eigendecomposition_pca_solutions.ipynb")
    jacobi_eigh = ns["jacobi_eigh"]

    rng = np.random.default_rng(33)
    M = rng.standard_normal((6, 6))
    C = M @ M.T
    vals, vecs = jacobi_eigh(C)

    # Defining property first, library second.
    for i in range(6):
        assert np.max(np.abs(C @ vecs[:, i] - vals[i] * vecs[:, i])) < 1e-8
    assert np.allclose(vecs.T @ vecs, np.eye(6), atol=1e-9)
    assert np.allclose(np.sort(vals)[::-1], np.sort(np.linalg.eigvalsh(C))[::-1], atol=1e-8)
    assert np.isclose(np.sum(vals), np.trace(C))

    # PC1 locks onto the all-ones direction once a reference dominates.
    contact = np.linspace(0, 7.0, 8)
    A = 1.0 / (1.0 + np.abs(contact[:, None] - np.array([1.0, 3.5, 6.0])[None, :]) ** 2)
    X = A @ (rng.standard_normal((3, 40000)) * 2.0)
    Xr = X + 8.0 * rng.standard_normal(40000)
    _, V = jacobi_eigh(ns["sample_covariance"](Xr))
    ones = np.ones(8) / np.sqrt(8)
    angle = np.degrees(np.arccos(min(1.0, abs(float(V[:, 0] @ ones)))))
    assert angle < 5.0, f"PC1 must be the reference, got {angle:.1f} deg off"


@pytest.mark.unit
def test_module_l6_ged_beats_pca_on_a_contrast():
    """GED's whole claim is that it beats PCA when the biggest signal is not the point."""
    ns = run_notebook(LINALG_DIR / "06_generalized_eigendecomposition_solutions.ipynb")
    ged, rq = ns["ged"], ns["rayleigh_quotient"]

    rng = np.random.default_rng(37)
    contact = np.linspace(0, 7.0, 8)
    A = 1.0 / (1.0 + np.abs(contact[:, None] - np.array([1.0, 3.5, 6.0])[None, :]) ** 2)

    def rec(var):
        S = rng.standard_normal((3, 50000)) * np.sqrt(var)[:, None]
        return A @ S + 6.0 * rng.standard_normal(50000) + 0.2 * rng.standard_normal((8, 50000))

    C_s = ns["sample_covariance"](rec(np.array([4.0, 3.0, 2.0])))
    C_n = ns["sample_covariance"](rec(np.array([1.0, 3.0, 2.0])))

    ratios, filters, C_used = ged(C_s, C_n, alpha=0.0)
    # Each eigenvalue is the Rayleigh quotient of its own eigenvector.
    for i in range(8):
        assert np.isclose(rq(filters[:, i], C_s, C_used), ratios[i], rtol=1e-6)

    def angle(v, t):
        c = abs(float(v @ t) / (np.linalg.norm(v) * np.linalg.norm(t)))
        return float(np.degrees(np.arccos(min(1.0, c))))

    true_pattern = A[:, 0]
    _, pca_vecs = ns["jacobi_eigh"](C_s)
    assert angle(C_used @ filters[:, 0], true_pattern) < angle(pca_vecs[:, 0], true_pattern), (
        "GED must beat PCA at finding the source that changed"
    )
    assert angle(pca_vecs[:, 0], np.ones(8)) < 10.0, "PCA should lock onto the reference"


@pytest.mark.unit
def test_guardrail_notebooks_restate_their_config_values_correctly():
    """GRL 3 and GRL 4 restate thresholds from configs/guardrails.yaml, and say a test checks it.

    Both notebooks carry a comment promising that this suite asserts the restated
    values still match the config. Until this test existed the promise was false,
    which is worse than not making it: a reader who trusts the comment has no
    reason to re-derive the number, and an edit to either file would drift in
    silence. The audit that caught it is the reason the comment now has to be
    earned rather than asserted.
    """
    import yaml

    rules = yaml.safe_load((REPO_ROOT / "configs" / "guardrails.yaml").read_text())["guardrails"]

    n3 = run_notebook(GUARDRAILS_DIR / "03_emg_contamination_in_speech_solutions.ipynb")
    g7 = rules["G7_emg_contamination_in_high_band"]
    assert tuple(float(x) for x in n3["EMG_BAND_HZ"]) == tuple(
        float(x) for x in g7["emg_band_hz"]
    ), f"GRL 3 teaches emg_band_hz as {n3['EMG_BAND_HZ']} but the config says {g7['emg_band_hz']}"
    # The escalation frequency and the bipolar requirement left the config on
    # 2026-09-09 (nothing enforced them, so they were not keys); the lesson
    # still teaches them as the remedy, which is prose, not a config value.
    assert list(n3["ESCALATE_ONLY_FOR"]) == list(g7["escalate_only_for_conditions"]), (
        "GRL 3's escalation conditions must match G7, since Section 4 is built on them"
    )

    n4 = run_notebook(GUARDRAILS_DIR / "04_nonstationarity_and_drift_solutions.ipynb")
    g9 = rules["G9_nonstationarity_exceeds_effect"]
    assert float(n4["EXCURSION_TO_EFFECT_RATIO"]) == float(g9["excursion_to_effect_ratio"]), (
        f"GRL 4 teaches the ratio as {n4['EXCURSION_TO_EFFECT_RATIO']} "
        f"but the config says {g9['excursion_to_effect_ratio']}"
    )


@pytest.mark.unit
def test_rec5_restates_the_lead_spacings_from_the_config():
    """REC 5 computes distances from contact pitch, so its numbers must be the shipped ones.

    The lesson restates the two spacings to run standalone. They live in
    configs/leads.yaml as `row_spacing_mm`, a field REC 5 is the reason for: the
    only spacing in that file used to be inside model name strings like
    "3389 (1.5 mm spacing)", which no program can read.
    """
    import yaml

    leads = yaml.safe_load((REPO_ROOT / "configs" / "leads.yaml").read_text())["leads"]
    rec5 = run_notebook(SPATIAL_DIR / "05_localization_and_contact_labels_solutions.ipynb")

    configured = tuple(leads[name]["row_spacing_mm"] for name in rec5["PITCH_SOURCE"])
    assert tuple(rec5["PITCHES_MM"]) == configured, (
        f"REC 5 teaches pitches {tuple(rec5['PITCHES_MM'])} but configs/leads.yaml "
        f"says {configured} for {rec5['PITCH_SOURCE']}"
    )
    # The lesson reasons with these numbers and must not imply they are verified.
    for name in rec5["PITCH_SOURCE"]:
        assert leads[name]["spacing_confirmed"] is False, (
            f"{name} is now confirmed; REC 5's caveat about transcribed spacings "
            "needs revisiting rather than silently becoming wrong"
        )


@pytest.mark.unit
def test_inference_notebook_restates_the_normalization_options_correctly():
    """INF 3 derives configs/statistics.yaml, so its option names must be the shipped ones.

    The lesson proves three of the config's caveats as arithmetic: the
    whole_recording shrinkage of 1-f, the across_conditions ceiling of
    (k-1)/sqrt(k), and the own_condition noise penalty. Those proofs are about
    named options, so a renamed or added option silently leaves the lesson
    deriving something the app no longer offers. Check the names against both
    the config and the package, since either could be edited alone, and check one
    of the derivations against its closed form rather than against the lesson.
    """
    import yaml

    from dbsspeech.stats.normalize import CENTERS, SCALES

    inf3 = run_notebook(INFERENCE_DIR / "03_what_a_z_score_means_solutions.ipynb")
    assert tuple(inf3["CENTERS"]) == CENTERS, (
        f"INF 3 teaches centres {tuple(inf3['CENTERS'])} but the package offers {CENTERS}"
    )
    assert tuple(inf3["SCALES"]) == SCALES, (
        f"INF 3 teaches scales {tuple(inf3['SCALES'])} but the package offers {SCALES}"
    )

    config = yaml.safe_load((REPO_ROOT / "configs" / "statistics.yaml").read_text())
    assert set(inf3["CENTERS"]) == set(config["centers"]), (
        "INF 3's centres must match the options configs/statistics.yaml explains"
    )
    assert set(inf3["SCALES"]) == set(config["scales"]), (
        "INF 3's scales must match the options configs/statistics.yaml explains"
    )

    # INF 3 Section 3 proves that the across_conditions scale caps |z| at
    # (k-1)/sqrt(k), and Section 2 that the whole_recording centre shrinks an
    # effect by exactly 1-f. Both are derived in the notebook against the
    # notebook's own implementation, so restate them here against the formula:
    # if the lesson's arithmetic drifted, its internal check would drift with it.
    ceiling = inf3["z_of"](
        np.array([[0.0, 0.0, 30.0]]),
        np.ones((1, 3)),
        "grand_mean",
        "across_conditions",
        np.ones(3),
    )
    assert abs(np.abs(ceiling).max() - 2 / np.sqrt(3)) < 1e-9, (
        "three conditions cap |z| at (k-1)/sqrt(k) = 1.1547, whatever the effect"
    )


@pytest.mark.unit
def test_module_g3_table_matches_the_guardrail_config():
    """G3 restates the guardrails so it runs standalone; it must not drift.

    Every id and severity in the notebook's table is checked against
    `configs/guardrails.yaml`, which is the authority.
    """
    import yaml

    ns = run_notebook(CURRICULUM_ROOT / "07_guardrails" /
                      "05_the_thirteen_guardrails_solutions.ipynb")
    table = ns["GUARDRAILS"]

    config = yaml.safe_load((REPO_ROOT / "configs" / "guardrails.yaml").read_text())
    rules = {k: v for k, v in config["guardrails"].items() if k.startswith("G")}

    assert len(table) == len(rules), (
        f"G3 lists {len(table)} guardrails, the config has {len(rules)}"
    )

    # Titles come from docs/guardrails.md, which is the prose authority. Checking
    # the NAME as well as the id is what catches a guardrail described as
    # something it is not, which is a defect an id check cannot see.
    doc = (REPO_ROOT / "docs" / "guardrails.md").read_text()
    titles = dict(re.findall(r"^## (G\d+)\. (.+)$", doc, flags=re.MULTILINE))
    assert len(titles) == len(rules), f"docs/guardrails.md has {len(titles)} headings"

    for gid, entry in table.items():
        key = entry["key"]
        assert key in rules, f"G3 names {key}, which is not in configs/guardrails.yaml"
        assert entry["severity"] == rules[key]["severity"], (
            f"{gid}: G3 says {entry['severity']}, the config says {rules[key]['severity']}"
        )
        assert gid in titles, f"{gid} has no heading in docs/guardrails.md"
        assert entry["name"].lower() == titles[gid].lower().rstrip("."), (
            f"{gid}: G3 calls it {entry['name']!r}, docs/guardrails.md calls it "
            f"{titles[gid]!r}. A guardrail described as something it is not teaches "
            f"the wrong rule."
        )
    assert {e["key"] for e in table.values()} == set(rules), "every configured rule must appear"


@pytest.mark.unit
def test_notebooks_do_not_invent_frequency_bands():
    """Any band a notebook names must be one configs/bands.yaml actually defines.

    configs/bands.yaml leaves a gap between low_gamma and high_gamma because
    line_noise.fundamental sits at 60 Hz. A notebook that spans the gap is
    measuring across the notch.
    """
    import yaml

    cfg = yaml.safe_load((REPO_ROOT / "configs" / "bands.yaml").read_text())
    known = {tuple(float(x) for x in v) for v in cfg["bands"].values()}
    line_hz = float(cfg.get("line_noise", {}).get("fundamental", 60.0))

    offenders = []
    for path in sorted(CURRICULUM_ROOT.rglob("*.ipynb")):
        # Read the CELL SOURCES, not the raw file: quotes are escaped in the JSON.
        nb = json.loads(path.read_text())
        text = "\n".join("".join(c["source"]) for c in nb["cells"])
        # Named band literals of the form "<name> lo-hi": (lo, hi)
        for name, lo, hi in re.findall(
                r'"([a-z ]*(?:theta|alpha|beta|gamma)[a-z0-9 -]*)":\s*\(([\d.]+),\s*([\d.]+)\)',
                text):
            pair = (float(lo), float(hi))
            if pair in known:
                continue
            if pair[0] < line_hz < pair[1]:
                offenders.append(f"{path.name}: {name!r} = {pair} spans the "
                                 f"{line_hz:.0f} Hz line-noise notch")
    assert not offenders, "bands that cross line noise:\n  " + "\n  ".join(offenders)


@pytest.mark.unit
def test_every_module_is_reachable_in_the_learn_ui():
    """A notebook nobody can open is not curriculum.

    Each stem on disk must be referenced by the Learn UI, either by a bespoke
    page or through the notebook-module registry, and be marked active.
    """
    learn = (REPO_ROOT / "web" / "src" / "pages" / "Learn.tsx").read_text()
    learn_dir = REPO_ROOT / "web" / "src" / "pages" / "learn"
    # .ts as well as .tsx: the notebook-module registry is a plain .ts file.
    ui_text = learn + "".join(f.read_text()
                              for f in sorted(learn_dir.glob("*.ts*")))

    stems = sorted({p.name.replace("_solutions.ipynb", "").replace("_student.ipynb", "")
                    for p in CURRICULUM_ROOT.rglob("*.ipynb")})
    assert stems, "no curriculum notebooks found"

    missing = [s for s in stems if s not in ui_text]
    assert not missing, f"notebooks on disk that the UI never references: {missing}"

    inactive = re.findall(r'\{ id: "([^"]+)", title: "[^"]*", active: false \}', learn)
    assert not inactive, f"modules still switched off in Learn.tsx: {inactive}"


@pytest.mark.unit
def test_student_notebooks_withhold_their_answers():
    """A student workbook identical to its solutions is not a workbook.

    Two withholding styles are in use: `raise NotImplementedError` in the
    generated modules, and `### YOUR CODE HERE ###` in LIN 1 and LIN 2, which predate
    the generator. Either is fine; neither being present is not.
    """
    for student in sorted(CURRICULUM_ROOT.rglob("*_student.ipynb")):
        solutions = student.with_name(student.name.replace("_student", "_solutions"))
        assert solutions.exists(), f"{student.name} has no solutions counterpart"

        def code_of(path):
            nb = json.loads(path.read_text())
            return "".join("".join(c["source"]) for c in nb["cells"]
                           if c["cell_type"] == "code")

        st, sol = code_of(student), code_of(solutions)
        assert st != sol, (
            f"{student.name} is byte-identical to its solutions, so the split is a lie"
        )
        withholds = "raise NotImplementedError" in st or "YOUR CODE HERE" in st
        assert withholds, f"{student.name} does not withhold any answer"
        assert "raise NotImplementedError" not in sol, (
            f"{solutions.name} still raises NotImplementedError somewhere"
        )


@pytest.mark.unit
def test_the_learn_tablist_follows_the_aria_tab_pattern():
    """Tab semantics without the tab relationships announce the wrong thing.

    The page had `role="tab"` and `aria-selected` but no `aria-controls`, and the
    panel had no id, so a screen reader was told these were tabs and then given
    no way to say which region a tab governed. Native buttons made it operable by
    Tab and Enter, which is why the gap survived: it degrades the announcement,
    not the clicking.
    """
    page = (REPO_ROOT / "web" / "src" / "pages" / "Learn.tsx").read_text()

    assert 'id="lesson-panel"' in page, "the tabpanel needs an id for aria-controls to reference"
    assert 'role="tabpanel"' in page and "aria-labelledby=" in page, (
        "the panel must name the tab that governs it"
    )

    # Every tab points at the panel, and carries an id the panel can point back to.
    # Count JSX attributes only: the querySelector in the key handler also contains
    # the string role="tab" and is not itself a tab.
    tabs = sum(1 for line in page.split("\n") if line.strip() == 'role="tab"')
    assert tabs >= 2, "both the course bar and the lesson bar are tablists"
    assert page.count('aria-controls="lesson-panel"') == tabs, (
        "every tab must declare the panel it controls"
    )
    assert page.count("id={`course-tab-") == 1 and page.count("id={`lesson-tab-") == 1, (
        "each tab needs a stable id, since aria-labelledby resolves against it"
    )

    # One tab stop per tablist, with the arrows moving inside it.
    assert page.count("tabIndex={selected") == 2, "tablists use a roving tabindex"
    assert page.count("onKeyDown={moveTabFocus}") == 2, "both tablists take arrow keys"
    for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
        assert key in page, f"the tab pattern expects {key}"


@pytest.mark.unit
def test_learn_pages_meet_basic_accessibility_requirements():
    """A widget nobody can operate with a keyboard is not curriculum either.

    These are the checks that can be made statically. Colour contrast and
    screen-reader behaviour need a browser and are not asserted here.
    """
    learn_dir = REPO_ROOT / "web" / "src" / "pages" / "learn"
    pages = sorted(learn_dir.glob("*.tsx")) + [REPO_ROOT / "web" / "src" / "pages" / "Learn.tsx"]

    unnamed_sliders, unlabelled_svgs, unreachable = [], [], []
    for p in pages:
        lines = p.read_text().split("\n")
        for i, ln in enumerate(lines):
            window = "\n".join(lines[i:i + 12])
            if 'type="range"' in ln and "aria-label" not in window:
                unnamed_sliders.append(f"{p.name}:{i + 1}")
            if ln.strip().startswith("<svg") and "aria-label" not in window:
                unlabelled_svgs.append(f"{p.name}:{i + 1}")
            # A click or drag handler on something that is not a button needs a
            # keyboard path of its own.
            if ("onClick=" in ln or "onPointerDown=" in ln):
                back = "\n".join(lines[max(0, i - 14):i + 14])
                is_button = "<button" in back
                has_keys = "onKeyDown" in back or "tabIndex" in back
                if not is_button and not has_keys:
                    unreachable.append(f"{p.name}:{i + 1}")

    assert not unnamed_sliders, f"range inputs with no accessible name: {unnamed_sliders}"
    assert not unlabelled_svgs, f"figures invisible to a screen reader: {unlabelled_svgs}"
    assert not unreachable, f"pointer-only interactions with no keyboard path: {unreachable}"


ALL_STUDENT = sorted(CURRICULUM_ROOT.rglob("*_student.ipynb"))


@pytest.mark.unit
@pytest.mark.parametrize("path", ALL_STUDENT, ids=lambda p: p.stem)
def test_student_notebooks_fail_only_where_they_mean_to(path):
    """A student workbook must run until it reaches a task, and no further.

    It cannot be executed to the end, because the tasks raise. What it must not
    do is fail for any OTHER reason: a bad import, a cell out of order, a name
    used before it is defined. Those ship undetected otherwise, and they land on
    the student rather than on us.
    """
    nb = json.loads(path.read_text())
    ns: dict = {}
    for idx, cell in enumerate(nb["cells"]):
        if cell["cell_type"] != "code":
            continue
        code = "".join(cell["source"])
        try:
            exec(code, ns)
        except NotImplementedError:
            return                      # reached the first task, as intended
        except Exception as exc:        # noqa: BLE001 - reporting is the point
            # LIN 1 and LIN 2 predate the `raise NotImplementedError` convention and
            # withhold with `= ...` placeholders instead. Those stop in one of two
            # ways: an Ellipsis reaching arithmetic, or the module's own test cell
            # failing on the empty result. Both are intended.
            if "ellipsis" in str(exc).lower():
                return
            if isinstance(exc, AssertionError) and "TEST CELL" in code:
                return
            pytest.fail(
                f"{path.name} cell {idx} failed before reaching any task, with "
                f"{type(exc).__name__}: {exc}\nCode:\n{code[:300]}"
            )
    # LIN 1 and LIN 2 use `...` placeholders rather than raising, so reaching the end
    # without a NotImplementedError is only acceptable for those.
    src = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    assert "YOUR CODE HERE" in src, (
        f"{path.name} ran to completion without hitting a task; it withholds nothing"
    )


@pytest.mark.unit
def test_every_generated_module_still_has_its_generator():
    """The notebooks are artifacts; the generators in curriculum/tools are the source.

    LIN 1 to LIN 3 predate the generator pattern and are hand-maintained, which is why
    LIN 3 lost its variant tag once. Everything since is generated, and a module
    whose generator went missing has quietly become hand-maintained too.
    """
    tools = CURRICULUM_ROOT / "tools"
    assert tools.is_dir(), "curriculum/tools is where the generators live"

    hand_written = {
        "01_vectors_and_dot_products",
        "02_matrices_and_montages",
        "03_matrix_inverses_conditioning",
    }
    stems = {p.name.replace("_solutions.ipynb", "")
             for p in CURRICULUM_ROOT.rglob("*_solutions.ipynb")}
    generated = stems - hand_written

    # Each generator names the stem it emits, so match on that rather than on a
    # filename convention.
    emitted = set()
    for gen in tools.glob("make_*.py"):
        text = gen.read_text()
        for stem in generated:
            if stem in text:
                emitted.add(stem)

    missing = sorted(generated - emitted)
    assert not missing, f"modules with no generator in curriculum/tools: {missing}"
    assert not any(g.read_text().count("/home/") for g in tools.glob("*.py")), (
        "a generator hard-codes an absolute path, so it only runs on one machine"
    )


def _registry_entries():
    """Parse the module registry into {module_id: [(claim, value), ...]}."""
    text = (REPO_ROOT / "web" / "src" / "pages" / "learn" / "registry.ts").read_text()
    entries: dict[str, list[tuple[str, str]]] = {}
    current = None
    for line in text.split("\n"):
        header = re.match(r'\s{2}"([A-Z]{3} \d+)": \{', line)
        if header:
            current = header.group(1)
            entries[current] = []
            continue
        stem = re.search(r'stem: "([^"]+)"', line)
        if stem and current:
            entries[current].append(("__stem__", stem.group(1)))
            continue
        row = re.search(r'\{ claim: "(.*?)", value: "(.*?)" \}', line)
        if row and current:
            entries[current].append(row.groups())
    return entries


@pytest.mark.unit
def test_ui_numbers_still_match_what_the_notebooks_print():
    """The Learn page quotes numbers from the notebooks. They must not drift.

    Every numeric token in a registry value has to appear in the output the
    module actually produces. Without this, changing a band or a sample count
    leaves the app quoting a figure the code no longer produces, and nothing
    fails.
    """
    entries = _registry_entries()
    assert entries, "no registry entries parsed; the format may have changed"

    def numbers_in(text: str) -> list[float]:
        out = []
        for tok in re.findall(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?", text):
            with contextlib.suppress(ValueError):
                out.append(float(tok))
        return out

    # A tolerance or a qualifier is not a quoted measurement.
    QUALIFIER = re.compile(r"\b(within|under|over|about|roughly|at least|up to|"
                           r"exactly k|verified|opposite|both|nothing|none|larger|"
                           r"smaller|below|above)\b", re.I)

    def quoted_numbers(value: str) -> list[tuple[float, int]]:
        """Numbers a claim quotes, with the decimal places they were quoted to."""
        if QUALIFIER.search(value):
            return []
        out = []
        # A comma-separated run of single digits is a sequence, not a number.
        if re.fullmatch(r"[\d,]+", value) and value.count(",") >= 2:
            return []
        # Scientific notation and thousands separators, so 2.3e18 and 66,667 are
        # single numbers rather than several.
        for tok in re.findall(r"-?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?", value):
            clean = tok.replace(",", "")
            try:
                v = float(clean)
            except ValueError:
                continue
            # Small integers are counts and labels; they appear everywhere and
            # carry no drift signal.
            if abs(v) < 10 and "." not in clean and "e" not in clean.lower():
                continue
            places = len(clean.split(".")[1].split("e")[0]) if "." in clean else 0
            out.append((v, places))
        return out

    drifted = []
    for module_id, rows in sorted(entries.items()):
        stem = dict(rows).get("__stem__")
        if not stem:
            continue
        matches = list(CURRICULUM_ROOT.rglob(f"{stem}_solutions.ipynb"))
        assert matches, f"{module_id} cites stem {stem!r}, which has no notebook"
        produced = numbers_in(notebook_stdout(matches[0]).replace(",", " "))

        for claim, value in rows:
            if claim == "__stem__":
                continue
            for wanted, places in quoted_numbers(value):
                # The module prints at its own precision; accept any printed
                # number that rounds to what the page quotes.
                tol = max(0.5 * 10 ** (-places), abs(wanted) * 0.02)
                if not any(abs(p - wanted) <= tol for p in produced):
                    drifted.append(
                        f"{module_id}: {claim!r} quotes {wanted:g} ({value!r}), "
                        f"and the module prints no number within {tol:g} of it"
                    )

    assert not drifted, ("the Learn page quotes numbers the notebooks no longer "
                         "produce:\n  " + "\n  ".join(drifted))


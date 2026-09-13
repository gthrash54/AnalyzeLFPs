"""Errors a person can act on.

`QCNotApproved: demo01 is in_review` teaches nobody anything. Each of these
checks that the answer says what happened and what to do next, and that the
technical text survives beside it for whoever gets asked about it.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dbsspeech.api import errors

pytestmark = pytest.mark.unit


def test_a_known_exception_has_a_message_and_a_next_step():
    found = errors.explain("QCNotApproved")
    assert found is not None
    assert "QC review" in found.message
    assert "sign" in found.next_step
    assert found.status == 409


def test_an_unknown_exception_gets_no_invented_advice():
    """Better a bare error than confident guidance about something unrecognized."""
    assert errors.explain("SomethingNobodyHasSeen", "who knows") is None


def test_a_recorded_failure_is_explained_from_its_text():
    """What a worker writes into a job row: 'ExceptionName: message'."""
    explained = errors.explain_text("QCNotApproved: demo01 is in_review")
    assert explained is not None
    assert "next_step" in explained


def test_a_recipe_failure_is_matched_on_its_message():
    """Not every failure is a distinct exception class; some are a phrase."""
    explained = errors.explain_text(
        "RuntimeError: no measurable ERNA epochs. Check stim_source and blanking_ms"
    )
    assert explained is not None
    assert "stim_source" in explained["next_step"]


def test_the_friendly_message_does_not_carry_the_exception_class():
    """A sentence for a person does not begin with RuntimeError."""
    explained = errors.explain_text(
        "RuntimeError: no measurable ERNA epochs. Check stim_source and blanking_ms"
    )
    assert explained is not None
    assert "RuntimeError" not in explained["message"]
    assert explained["message"].startswith("no measurable ERNA epochs")


def test_a_failure_with_no_class_prefix_is_still_matched():
    explained = errors.explain_text("no measurable ERNA epochs. Check the source")
    assert explained is not None
    assert "RuntimeError" not in explained["message"]


def test_an_unrecognized_failure_explains_nothing():
    assert errors.explain_text("RuntimeError: something else entirely") is None


def _app_that_raises(exc: Exception) -> TestClient:
    app = FastAPI()
    errors.install(app)

    @app.get("/boom")
    def boom():  # noqa: ANN202 - test route
        raise exc

    return TestClient(app, raise_server_exceptions=False)


def test_the_gate_answers_with_a_status_and_an_explanation():
    from dbsspeech.qc import QCNotApproved

    client = _app_that_raises(QCNotApproved("demo01", "in_review", "nothing signed"))
    response = client.get("/boom")

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "QCNotApproved"
    assert "QC review" in body["detail"]
    assert body["next_step"]
    # The raw text is kept: somebody will paste it into a message asking for help.
    assert "demo01" in body["technical"]


def test_a_guardrail_block_carries_its_findings():
    from dbsspeech.guardrails.base import Finding, GuardrailBlocked, Severity

    finding = Finding(guardrail="G6_decimation_removes_claimed_band",
                      severity=Severity.BLOCK,
                      message="the band asked for is above the anti-alias cutoff",
                      remedy="raise sfreq_target_hz", overridable=False)
    client = _app_that_raises(GuardrailBlocked([finding]))
    body = client.get("/boom").json()

    assert body["error"] == "GuardrailBlocked"
    assert body["findings"][0]["guardrail"] == "G6_decimation_removes_claimed_band"
    assert body["findings"][0]["overridable"] is False

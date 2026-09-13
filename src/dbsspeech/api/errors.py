"""Turning the package's exceptions into messages a person can act on.

The package raises precise exceptions, which is right, and a browser showing
`QCNotApproved: demo01 is in_review` teaches nobody anything. Every mapping here
answers two questions: what happened, and what to do next.

The technical text is kept alongside, never replaced. Someone will paste it into
a message to whoever maintains this, and a friendly message with the detail
thrown away wastes that.

One place, so the API, the run screen, and the worker's recorded failures all say
the same thing about the same error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Explanation:
    status: int
    message: str
    next_step: str


# Keyed by exception class name rather than by the class, because a job failure
# arrives as text from another process and all we have is the name.
EXPLANATIONS: dict[str, Explanation] = {
    "QCNotApproved": Explanation(
        409,
        "This subject has not completed QC review, so no analysis can run on it.",
        "Open its QC page, decide the flags, and sign.",
    ),
    "GuardrailBlocked": Explanation(
        422,
        "A guardrail stopped this run before anything was computed, because the "
        "result would not answer the question it claims to.",
        "Read what fired. Change the parameter it names, or run again with an "
        "override and a reason, which is recorded.",
    ),
    "ConfigError": Explanation(
        422,
        "That config change was refused, and nothing was written.",
        "The message says which value is wrong. Fix it and save again.",
    ),
    "AuthError": Explanation(
        401,
        "That sign-in did not work.",
        "Check the email and password. There is no self-service reset; an admin "
        "resets a password with `python -m dbsspeech users password`.",
    ),
    "FileNotFoundError": Explanation(
        404,
        "A file this needs is not where the manifest says it is.",
        "Check that the recordings are mounted, and that root_relpath in "
        "subjects.csv points at the right directory.",
    ),
    "ValidationError": Explanation(
        422,
        "One of the parameters is not valid for this recipe.",
        "The message names the field. docs/recipes.md lists every parameter and "
        "what it accepts.",
    ),
}

# What a run failure looks like when the recipe found nothing to work with. Not
# an exception type, so matched on the text the recipe wrote.
_PHRASES: tuple[tuple[str, str], ...] = (
    ("no measurable ERNA epochs",
     "Check stim_source and blanking_ms on the Run screen. Nothing was detected, "
     "which usually means the events are not where the recipe looked."),
    ("no time-frequency maps computed",
     "The windows in the manifest are too short or too close to the ends of the "
     "recording for the tmin and tmax asked for."),
    ("database is locked",
     "Two processes are writing at once. If this repeats, check whether more than "
     "one worker is running against the same database."),
)


def explain(name: str, message: str = "") -> Explanation | None:
    """The explanation for an exception name, or a phrase in its message.

    `message` is the message alone. Passing the whole `ExceptionName: message`
    string puts the class name into the sentence shown to a person, which is the
    thing this module exists to avoid.
    """
    known = EXPLANATIONS.get(name)
    if known is not None:
        return known
    for phrase, next_step in _PHRASES:
        if phrase in message:
            first_sentence = message.split(".")[0].strip()
            return Explanation(422, f"{first_sentence}.", next_step)
    return None


def explain_text(error: str) -> dict[str, Any] | None:
    """Explain a recorded failure of the form `ExceptionName: message`.

    What a worker writes into a job row, read back by the run screen.
    """
    name, separator, message = error.partition(": ")
    # No separator means the whole string is the message, not a class name.
    found = explain(name.strip() if separator else "", message if separator else error)
    if found is None:
        return None
    return {"message": found.message, "next_step": found.next_step}


def install(app: Any) -> None:
    """Register a handler per known exception, so every route answers alike."""
    from fastapi.responses import JSONResponse

    from ..auth import AuthError
    from ..configs_admin import ConfigError
    from ..guardrails import GuardrailBlocked
    from ..qc import QCNotApproved

    def handler(exc_class: type[Exception]):
        async def handle(_request: Any, exc: Exception) -> JSONResponse:
            found = explain(exc_class.__name__, str(exc))
            assert found is not None  # every registered class has an entry
            body: dict[str, Any] = {
                # `detail` is what an HTTP client already looks at, so the
                # friendly message goes there and the raw text goes beside it.
                "detail": found.message,
                "error": exc_class.__name__,
                "next_step": found.next_step,
                "technical": str(exc),
            }
            if isinstance(exc, GuardrailBlocked):
                body["findings"] = [
                    {"guardrail": f.guardrail, "severity": f.severity.value,
                     "message": f.message, "remedy": f.remedy,
                     "overridable": f.overridable}
                    for f in exc.findings
                ]
            return JSONResponse(status_code=found.status, content=body)

        return handle

    for exc_class in (QCNotApproved, GuardrailBlocked, ConfigError, AuthError):
        app.add_exception_handler(exc_class, handler(exc_class))

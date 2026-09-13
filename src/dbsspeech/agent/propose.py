"""Turn a plain-language request into a recipe proposal, with its reasoning shown.

Deliberately rule-based. A proposal states what it inferred, what it guessed, and
what it could not determine, because a confident wrong parameter is worse than an
admitted gap. Anything it could not decide comes back as a question rather than a
default quietly applied.

The most useful thing it does is dry-run the guardrails against the parameters it
is about to suggest, so you learn that a run would be blocked before you start it
rather than after.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from typing import Any

from ..guardrails import CheckContext, GuardrailBlocked, run_checks
from ..stats import options_for_schema

# Band words to frequency ranges, read from configs/bands.yaml when available and
# falling back to these. Matching is on whole words so "beta" does not fire on
# "alphabetical".
_FALLBACK_BANDS = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "low beta": (13.0, 20.0),
    "high beta": (20.0, 30.0),
    "gamma": (30.0, 150.0),
    "low gamma": (30.0, 60.0),
    "high gamma": (70.0, 150.0),
    "hfo": (250.0, 350.0),
    "mua": (500.0, 3000.0),
}

_MONTAGE_WORDS = {
    "monopolar": "monopolar",
    "bipolar": "bipolar_vertical",
    "vertical": "bipolar_vertical",
    "horizontal": "bipolar_horizontal",
    "adjacent": "bipolar_adjacent",
    "car": "car",
    "common average": "car",
}

_UNIT_WORDS = {
    "epoch": "pseudo_epoch",
    "trial": "pseudo_epoch",
    "segment": "pseudo_epoch",
    "whole window": "window",
}


@dataclass
class ProposedParameter:
    """One parameter, with why it was set and how sure that is."""

    name: str
    value: Any
    reason: str
    confidence: str = "inferred"  # inferred | default | guess | yours | cleared

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass
class Proposal:
    """What the agent suggests, and everything it wants you to know first."""

    recipe: str
    params: dict[str, Any] = field(default_factory=dict)
    reasoning: list[ProposedParameter] = field(default_factory=list)
    guardrails: list[dict[str, str]] = field(default_factory=list)
    blocked: bool = False
    caveats: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    understood: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe": self.recipe,
            "params": self.params,
            "reasoning": [r.to_dict() for r in self.reasoning],
            "guardrails": self.guardrails,
            "blocked": self.blocked,
            "caveats": self.caveats,
            "questions": self.questions,
            "understood": self.understood,
        }


def _words(text: str) -> str:
    return f" {re.sub(r'[^a-z0-9 ]+', ' ', text.lower())} "


def _condition_specs(configs: dict[str, Any]) -> dict[str, Any]:
    """Condition entries from the vocabulary, tolerating the terse form.

    An entry may be a mapping with `aliases`, or the older
    ``{label, description}`` shape, or absent entirely. All three are valid
    config, so this returns something dict-shaped either way rather than making
    the caller guard.
    """
    conditions = (configs.get("vocabularies") or {}).get("conditions") or {}
    return {
        name: (spec if isinstance(spec, dict) else {})
        for name, spec in conditions.items()
    }


def _find_phrases(text: str, table: dict[str, Any]) -> list[tuple[str, Any]]:
    """Longest phrases first, so 'high gamma' beats 'gamma'."""
    padded = _words(text)
    hits = []
    for phrase in sorted(table, key=len, reverse=True):
        if f" {phrase} " in padded and not any(phrase in seen for seen, _ in hits):
            hits.append((phrase, table[phrase]))
    return hits


# Words long enough to pass the length filter and common enough to mean nothing.
# Without these, "please do the thing with the wibble" matches a recipe on "with"
# and reports that as its reason, which is worse than admitting it did not
# understand: it looks like understanding.
_STOPWORDS = frozenset({
    "about", "after", "also", "another", "anything", "back", "been", "before",
    "being", "between", "both", "came", "come", "does", "doing", "done", "down",
    "during", "each", "else", "even", "every", "from", "give", "given", "goes",
    "going", "have", "here", "into", "just", "like", "look", "looking", "make",
    "many", "more", "most", "much", "must", "need", "needs", "only", "other",
    "over", "please", "same", "show", "shows", "some", "such", "take", "than",
    "that", "them", "then", "there", "these", "they", "thing", "things", "this",
    "those", "through", "time", "using", "very", "want", "what", "when", "where",
    "which", "while", "will", "with", "within", "without", "would", "your",
})


def _content_words(text: str) -> set[str]:
    """Content words of `text`, with plurals folded onto their singular.

    Applied to both sides, so "conditions" in a question reaches "condition" in a
    recipe's own sentence. Without it the chooser matched nothing at all on "is
    high gamma different between conditions", which is not a hard question.

    A trailing "s" is not a stemmer and is not meant to be. It is the one English
    inflection that separates the words people actually use to describe an
    analysis from the words a recipe author wrote, and folding it consistently on
    both sides cannot make two genuinely different words collide any more often
    than they already would.
    """
    out = set()
    for w in _words(text).split():
        if len(w) > 3 and w not in _STOPWORDS:
            out.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)
    return out


def _recipe_vocabularies() -> list[tuple[str, set[str]]]:
    """Each recipe's name, question and description, as a bag of content words.

    The words a recipe author already wrote for a reader, which is what makes
    this work for a recipe registered tomorrow without touching this file.
    """
    from ..recipes import describe_all

    out = []
    for spec in describe_all():
        text = " ".join(
            [spec["name"].replace("_", " "), spec.get("question", ""),
             spec.get("description", "")]
        )
        out.append((spec["name"], _content_words(text)))
    return out


def _weights(vocabularies: list[tuple[str, set[str]]]) -> dict[str, float]:
    """How much a shared word is worth: rarer across recipes means more.

    Length was the first answer and it is wrong, because length measures nothing.
    "change" is six letters and appears in one recipe, "beta" is four and appears
    in one; scored by length, "does beta power change during speech" chose the
    time-frequency recipe over the band-contrast one, 11 to 9. A person who names
    a frequency band is telling you which analysis they want, and the chooser
    threw that away in favour of a verb.

    Inverse document frequency asks the right question instead: how much does
    this word narrow the field. "power" appears in three of five recipes and is
    worth almost nothing. "beta" appears in one and is nearly decisive. Nothing
    is hard-coded per recipe; the weights fall out of whatever recipes exist.
    """
    total = len(vocabularies) or 1
    counts: dict[str, int] = {}
    for _, vocabulary in vocabularies:
        for word in vocabulary:
            counts[word] = counts.get(word, 0) + 1
    # log(total / df), floored above zero so a word every recipe shares still
    # breaks a tie rather than being discarded outright.
    return {w: max(math.log(total / c), 0.05) for w, c in counts.items()}


def choose_recipe(question: str, default: str = "psd_by_condition") -> tuple[str, str]:
    """Pick the recipe whose own question best matches what was asked.

    Scored on words shared with each recipe's `question`, `description` and name,
    weighted by how rare each word is across the registered recipes. No model, no
    embedding, and nothing hard-coded per recipe.

    Returns the name and the reason, because a choice a person cannot see the
    basis of is one they cannot correct. The reason names the words that decided
    it, most informative first, so "matched on beta" reads as an explanation
    rather than a coincidence.
    """
    asked = _content_words(question)
    if not asked:
        return default, "nothing was asked, so this is the usual starting point"

    vocabularies = _recipe_vocabularies()
    weight = _weights(vocabularies)

    best, best_score, best_overlap = default, 0.0, set()
    for name, vocabulary in vocabularies:
        overlap = asked & vocabulary
        if not overlap:
            continue
        score = sum(weight[w] for w in overlap)
        if score > best_score:
            best, best_score, best_overlap = name, score, overlap

    if not best_overlap:
        return default, (
            "nothing in the question matched a recipe, so this is the usual "
            "starting point"
        )
    ranked = sorted(best_overlap, key=lambda w: (-weight[w], w))
    return best, f"matched on {', '.join(ranked[:4])}"


def propose(
    question: str,
    session: Any | None = None,
    configs: dict[str, Any] | None = None,
    recipe: str | None = "psd_by_condition",
    params: dict[str, Any] | None = None,
    cleared: Sequence[str] | None = None,
) -> Proposal:
    """Propose parameters for `recipe` from a plain-language request.

    `recipe` of None means choose one from the question.

    `params` are values a person has already set. They win over anything inferred
    and are re-explained as theirs, so the same call serves both "what should I
    run" and "check what I changed". That second use is the one that matters: the
    guardrail dry-run below then describes the run about to happen rather than
    the one the agent would have suggested.

    `cleared` are fields a person emptied on purpose. Nothing is inferred for
    them and nothing is sent for them, so the recipe's own default applies.
    Emptying a field is a decision, and an agent that helpfully fills it back in
    has overruled it, which is the one thing this whole module is built not to
    do.
    """
    configs = configs or {}
    text = question or ""
    if recipe is None:
        recipe, why = choose_recipe(text)
        chosen_reason: str | None = why
    else:
        chosen_reason = None
    prop = Proposal(recipe=recipe)
    if chosen_reason:
        prop.understood["recipe_reason"] = chosen_reason

    bands = {
        name.replace("_", " "): tuple(edges)
        for name, edges in ((configs.get("bands") or {}).get("bands") or {}).items()
    } or _FALLBACK_BANDS

    known_conditions = list(session.conditions()) if session is not None else []
    targets = (
        {lid: lead.target for lid, lead in session.leads().items()}
        if session is not None
        else {}
    )

    # ---- frequency range ----------------------------------------------------
    band_hits = _find_phrases(text, bands)
    if band_hits:
        lo = min(edges[0] for _, edges in band_hits)
        hi = max(edges[1] for _, edges in band_hits)
        prop.params["fmin"], prop.params["fmax"] = float(lo), float(hi)
        named = ", ".join(name for name, _ in band_hits)
        prop.reasoning.append(
            ProposedParameter(
                "fmin/fmax", [lo, hi],
                f"you named {named}, so the range covers it", "inferred",
            )
        )
        prop.understood["bands"] = named

    # ---- conditions ---------------------------------------------------------
    named_conditions = [c for c in known_conditions if f" {c} " in _words(text)]

    # A question usually describes a condition rather than naming it: "during
    # speech" rather than "overt". The alias table comes from
    # configs/vocabularies.yaml, so a lab running a motor or cognitive paradigm
    # extends it with a config line instead of editing this module. Only
    # conditions the session actually has windows for are eligible, so an alias
    # can never propose a condition that cannot be analyzed.
    alias_table = {
        str(alias): name
        for name, spec in _condition_specs(configs).items()
        if name in known_conditions
        for alias in ((spec or {}).get("aliases") or [])
    }
    # Longest phrase first, so "imagined speech" resolves to inner speech rather
    # than being swallowed by the "speech" alias of overt.
    aliased = [name for _, name in _find_phrases(text, alias_table)]
    matched_by = {
        name: phrase for phrase, name in _find_phrases(text, alias_table)
    }
    named_conditions = list(dict.fromkeys([*named_conditions, *aliased]))

    if named_conditions:
        prop.params["conditions"] = named_conditions
        described = [c for c in named_conditions if c in matched_by]
        why = "matched against the windows in the manifest"
        if described:
            phrases = ", ".join(f"{matched_by[c]!r} -> {c}" for c in described)
            why = f"{why}; {phrases} came from the condition vocabulary"
        prop.reasoning.append(
            ProposedParameter("conditions", named_conditions, why, "inferred")
        )
        prop.understood["conditions"] = named_conditions

    # ---- leads --------------------------------------------------------------
    named_leads = [
        lid for lid, target in targets.items()
        if f" {target} " in _words(text) or f" {lid} " in _words(text)
    ]
    if named_leads:
        prop.params["leads"] = named_leads
        prop.reasoning.append(
            ProposedParameter(
                "leads", named_leads,
                "you named a target that maps to these leads", "inferred",
            )
        )
        prop.understood["leads"] = named_leads

    # ---- montage ------------------------------------------------------------
    montage_hits = _find_phrases(text, _MONTAGE_WORDS)
    comparing = any(w in _words(text) for w in (" compare ", " comparison ", " versus ", " vs "))
    if montage_hits and not comparing:
        scheme = montage_hits[0][1]
        prop.params["primary_reference"] = scheme
        prop.reasoning.append(
            ProposedParameter("primary_reference", scheme, "you named this montage", "inferred")
        )
    elif comparing and montage_hits:
        prop.reasoning.append(
            ProposedParameter(
                "references", "all",
                "you asked for a comparison, and every montage is computed each run "
                "anyway, so the comparison is already in the output",
                "default",
            )
        )

    # ---- unit ---------------------------------------------------------------
    unit_hits = _find_phrases(text, _UNIT_WORDS)
    if unit_hits:
        prop.params["unit"] = unit_hits[0][1]
        prop.reasoning.append(
            ProposedParameter(
                "unit", unit_hits[0][1],
                f"you said '{unit_hits[0][0]}'. Pseudo-epochs give an n, but they "
                "are not independent, so any p-value must account for that",
                "inferred",
            )
        )

    # ---- what it could not decide -------------------------------------------
    if session is not None and not named_conditions and known_conditions:
        prop.questions.append(
            f"Which conditions? The manifest has {known_conditions}. "
            "Leaving it unset runs all of them."
        )
    if not band_hits:
        prop.questions.append(
            "Which frequency range? No band was named, so the recipe default of "
            "1 to 200 Hz applies."
        )

    # ---- statistics caveats -------------------------------------------------
    stats = options_for_schema()
    center = prop.params.get("baseline_center", "grand_mean")
    scale = prop.params.get("baseline_scale", "pooled_within_condition")
    for group, chosen in (("centers", center), ("scales", scale)):
        for option in stats[group]:
            if option["value"] == chosen and option["caveat"]:
                prop.caveats.append(f"{option['label']}: {option['caveat']}")

    # ---- window provenance --------------------------------------------------
    if session is not None:
        used = prop.params.get("conditions") or known_conditions
        suspect = [
            w for w in session.windows()
            if w["condition"] in used and w.get("status") in {"draft", "under_revision"}
        ]
        for w in suspect:
            prop.caveats.append(
                f"The {w['condition']} window is marked {w['status']}, so any result "
                "using it inherits that."
            )

    # ---- what the person actually set ----------------------------------------
    # Applied last so nothing inferred can quietly overwrite a decision somebody
    # made, and recorded as theirs so the review screen does not present their
    # own value back to them as a suggestion.
    for name, value in (params or {}).items():
        if value is None:
            continue
        prop.params[name] = value
        prop.reasoning = [r for r in prop.reasoning if r.name != name]
        prop.reasoning.append(
            ProposedParameter(name, value, "you set this", confidence="yours")
        )

    # ---- what the person emptied ----------------------------------------------
    # Last, so nothing above can put a value back. A cleared field is not an
    # absent one: it was there, somebody removed it, and the recipe's own default
    # is what they asked for.
    for name in cleared or ():
        prop.params.pop(name, None)
        prop.reasoning = [r for r in prop.reasoning if r.name != name]
        prop.reasoning.append(
            ProposedParameter(
                name, None,
                "you cleared this, so the recipe's own default applies",
                confidence="cleared",
            )
        )

    # ---- does it even validate ------------------------------------------------
    invalid = _validation_error(prop)
    if invalid:
        prop.questions.append(invalid)

    # ---- dry-run the guardrails ---------------------------------------------
    prop.guardrails, prop.blocked = _dry_run(prop, session)
    return prop


def _validation_error(prop: Proposal) -> str | None:
    """The recipe's own parameter model, asked whether this would be accepted.

    Better here than at submission: the point of the review step is that nothing
    surprising happens after the button.
    """
    try:
        from ..recipes import get as get_recipe

        get_recipe(prop.recipe).params_model(**prop.params)
    except KeyError:
        return f"{prop.recipe!r} is not a registered recipe."
    except Exception as exc:  # noqa: BLE001 - shown to a person, not re-raised
        return f"These parameters would be refused: {exc}"
    return None


def _dry_run(prop: Proposal, session: Any | None) -> tuple[list[dict[str, str]], bool]:
    """Evaluate the guardrails against the proposal without running anything.

    Where the recipe supplies its own guardrail context, that is used, because
    then the dry run is checking the same description of the run that
    `registry.run` will check. A dry run that reassures you about a different
    analysis than the one you are about to start is worse than none.
    """
    from_recipe = _recipe_context(prop, session)
    if from_recipe is not None:
        return from_recipe
    return _heuristic_dry_run(prop, session)


def _recipe_context(
    prop: Proposal, session: Any | None
) -> tuple[list[dict[str, str]], bool] | None:
    """The recipe's own account of itself, if it has one and a session to read."""
    if session is None:
        return None
    try:
        from ..recipes import get as get_recipe

        spec = get_recipe(prop.recipe)
        hook = getattr(spec.fn, "guardrail_context", None)
        if hook is None:
            return None
        model = spec.params_model(**prop.params)
        extra = dict(hook(session, model))
    except Exception:  # noqa: BLE001 - fall back rather than fail a preview
        return None

    conditions = tuple(extra.pop("conditions", ()) or ())
    rows = extra.pop("window_rows", None)
    if rows is None:
        rows = [w for w in session.windows() if w["condition"] in conditions]
    known = {f.name for f in fields(CheckContext)}
    context = CheckContext(
        recipe=prop.recipe,
        params=model.model_dump(),
        conditions=conditions,
        window_rows=rows,
        **{k: v for k, v in extra.items() if k in known},
    )
    return _evaluate(context)


def _heuristic_dry_run(
    prop: Proposal, session: Any | None
) -> tuple[list[dict[str, str]], bool]:
    """For a recipe with no context hook, or no session to read one from."""
    fmax = float(prop.params.get("fmax", 200.0))
    sfreq = float(prop.params.get("sfreq_target_hz", 8138.0))
    conditions = tuple(
        prop.params.get("conditions")
        or (session.conditions() if session is not None else ())
    )
    windows = (
        [w for w in session.windows() if w["condition"] in conditions]
        if session is not None
        else []
    )
    context = CheckContext(
        recipe=prop.recipe,
        params=prop.params,
        reference_scheme=prop.params.get("primary_reference", "bipolar_vertical"),
        reference_is_shared=True,
        sfreq_hz=sfreq,
        usable_bandwidth_hz=sfreq * 0.4,
        requested_bands={"requested_range": (float(prop.params.get("fmin", 1.0)), fmax)},
        window_s=float(prop.params.get("window_s", 1.0)),
        conditions=conditions,
        window_rows=windows,
        reports_db=True,
        reports_z=True,
        baseline_is_smoothed=False,
        per_contact_baseline_subtracted=True,
    )
    return _evaluate(context)


def _evaluate(context: CheckContext) -> tuple[list[dict[str, str]], bool]:
    """Run the checks and render the findings for a screen."""
    try:
        findings, _ = run_checks(context)
        blocked = False
    except GuardrailBlocked as exc:
        findings, blocked = exc.findings, True
    return (
        [
            {
                "guardrail": f.guardrail,
                "severity": f.severity.value,
                "message": f.message,
                "remedy": f.remedy,
                "overridable": str(f.overridable),
            }
            for f in findings
        ],
        blocked,
    )

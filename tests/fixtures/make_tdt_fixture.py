"""Kept as an import path. The generator itself moved into the package.

It moved because `python -m dbsspeech seed` builds the demo project from it, and
a shipped command cannot depend on the test suite: an installed package, or the
container image, has no `tests/` directory. It is still the same file, and still
generates the same synthetic recording.

Import `dbsspeech.demo_data` in new code. This shim exists so the recipe tests
that already import from here did not all have to change in the same commit that
moved it.
"""

from __future__ import annotations

from dbsspeech.demo_data import (  # noqa: F401
    BETA_CHANNELS,
    BETA_HZ,
    DURATION_S,
    ERNA_AMPLITUDE_V,
    ERNA_ARTIFACT_MS,
    ERNA_ARTIFACT_V,
    ERNA_CHANNELS,
    ERNA_FREQ_HZ,
    ERNA_ONSETS_S,
    ERNA_RESPONSE_DELAY_MS,
    ERNA_TAU_S,
    N_AUDIO_CH,
    N_NEURAL_CH,
    SEED,
    SFREQ_AUDIO,
    SFREQ_NEURAL,
    make_fixture,
)

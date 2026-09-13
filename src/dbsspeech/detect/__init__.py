"""Layout detection: propose, never decide.

Detectors inspect a recording and produce `Proposal` objects carrying a value,
the evidence behind it, and a confidence. A person confirms; the manifest records
the decision. Detection never writes a manifest, for the same reason QC flags
never write decisions: a proposal with evidence that a human accepted is
auditable, and a silent guess is not.

Configured by `configs/layout_detection.yaml`.
"""

from __future__ import annotations

from .base import Proposal, ProposalSet
from .geometry import (
    assess_contact_quality,
    classify_contacts,
    propose_lead_models,
)
from .manifest_rows import DraftManifest, draft_manifest, verify_readable
from .windows import propose_windows, proposed_rows

__all__ = [
    "DraftManifest",
    "Proposal",
    "ProposalSet",
    "assess_contact_quality",
    "classify_contacts",
    "propose_lead_models",
    "draft_manifest",
    "propose_windows",
    "proposed_rows",
    "verify_readable",
]

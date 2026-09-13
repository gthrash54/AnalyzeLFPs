// Types mirroring the FastAPI surface. Hand-written and strict: no `any`.
// If these drift from the server, a page fails to compile rather than
// rendering something wrong.

export interface Lead {
  lead_id: string;
  target: string;
  lead_model: string;
  rotation_known: boolean;
}

export interface ConditionWindow {
  condition: string;
  status: string;
  derived_from: string;
  duration_s: number;
}

export interface Subject {
  study_id: string;
  session: string;
  hemisphere: string;
  format: string;
  acquisition: string;
  n_channels: number;
  n_channels_included: number;
  leads: Lead[];
  conditions: ConditionWindow[];
  qc_status: string;
}

export interface SchemaProperty {
  type?: string;
  title?: string;
  /** "essential" or "advanced", set by the recipe. Absent means it did not say,
      and the form then shows everything rather than guessing. */
  "x-group"?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  anyOf?: { type?: string; enum?: string[]; items?: { type?: string } }[];
  items?: { type?: string };
  minimum?: number;
  exclusiveMinimum?: number;
}

export interface OptionExplanation {
  value: string;
  label: string;
  description: string;
  when_to_use: string;
  caveat: string;
}

export interface Recipe {
  name: string;
  description: string;
  version: string;
  params_schema: {
    properties: Record<string, SchemaProperty>;
    required?: string[];
  };
  option_explanations?: Record<string, OptionExplanation[]>;
  /** The question this recipe answers, in a person's words. */
  question?: string;
  /** What lands in the run directory, in words. */
  produces?: string;
}

export interface GuardrailHit {
  guardrail: string;
  severity: string;
  message: string;
  remedy: string;
  overridable: string;
}

export interface ProposedParameter {
  name: string;
  value: unknown;
  reason: string;
  confidence: string;
}

export interface Proposal {
  recipe: string;
  params: Record<string, unknown>;
  reasoning: ProposedParameter[];
  guardrails: GuardrailHit[];
  blocked: boolean;
  caveats: string[];
  questions: string[];
  understood: Record<string, unknown>;
  /** Filled by the API from the chosen recipe, so a review step needs one call. */
  asks?: string;
  produces?: string;
}

export interface RunSummaryRow {
  run_id: string;
  name: string;
  claim: string | null;
  status: string;
  started_at: string | null;
  git_dirty: number;
  n_blocking: number;
  n_overrides: number;
}

export interface RunRecord {
  run_id: string;
  name: string;
  claim: string;
  user: string;
  status: string;
  error: string | null;
  git_commit: string | null;
  git_dirty: boolean;
  params: Record<string, unknown>;
  outputs: string[];
  guardrails: {
    findings?: { guardrail: string; severity: string; message: string }[];
    overrides?: { guardrail: string; reason: string }[];
    // Rules that could only be decided once the recipe had produced a result,
    // so they were evaluated in a second pass afterwards. G9 is the first: it
    // compares a baseline excursion to the effect the run reports, and neither
    // number exists beforehand. Kept separate from the pre-run findings above
    // because a reader should be able to tell what was knowable before the data
    // was touched.
    after?: {
      findings?: { guardrail: string; severity: string; message: string }[];
      overrides?: { guardrail: string; reason: string }[];
    };
  };
  summary: Record<string, unknown>;
  versions: Record<string, string>;
}

export interface RunHandle {
  handle: string;
  status: string;
  run_id?: string | null;
  error?: string | null;
  findings?: GuardrailHit[];
}

export interface DecisionRow {
  flag_id: string;
  target_type: string;
  target: string;
  flag_type: string;
  evidence_summary: string;
  proposed_action: string;
  severity: string;
  status: string;
  approved: string;
  action_taken: string;
  reviewer: string;
  reviewed_at: string;
  reason: string;
}

export interface HistoryEvent {
  event: string;
  reviewer: string;
  at: string;
  reason?: string;
}

export interface QcState {
  study_id: string;
  status: string;
  n_flags: number;
  n_undecided: number;
  decisions: DecisionRow[];
  history: HistoryEvent[];
  report_available: boolean;
}

export interface ParamDiffRow {
  param: string;
  a: unknown;
  b: unknown;
  changed: boolean;
}

export interface CompareSide {
  run_id: string;
  claim: string | null;
  recipe: string;
  status: string;
  git_commit: string | null;
  git_dirty: boolean;
  summary: Record<string, unknown>;
  figures: string[];
}

export interface Comparison {
  a: CompareSide;
  b: CompareSide;
  params: ParamDiffRow[];
  n_changed: number;
  shared_figures: string[];
  same_recipe: boolean;
  same_code: boolean;
}

export interface DatabaseHealth {
  path: string;
  present: boolean;
  ok: boolean;
  note: string;
}

export interface QueueHealth {
  jobs: Record<string, number>;
  queued: number;
  running: number;
  workers: number;
  workers_responsive: boolean;
  seconds_since_worker_seen: number | null;
  stale_after_s: number;
  healthy: boolean;
  note: string;
}

export interface Health {
  package: string;
  ok: boolean;
  versions: Record<string, string>;
  manifest_valid: boolean;
  manifest_errors: string[];
  manifest_warnings: string[];
  data_dir_present: boolean;
  auth_required: boolean;
  executor: string;
  databases: Record<string, DatabaseHealth>;
  queue: QueueHealth;
}

export interface JobRow {
  job_id: string;
  recipe: string;
  study_id: string;
  session: string;
  claim: string;
  status: string;
  run_id: string | null;
  error: string | null;
  claimed_by: string | null;
  enqueued_at: string;
  started_at: string | null;
  finished_at: string | null;
}

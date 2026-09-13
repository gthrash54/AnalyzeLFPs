// The only place that talks to the server. Every call goes through `request`,
// so an error surfaces with the server's own message rather than a bare status.

import type {
  Comparison,
  Health,
  JobRow,
  Proposal,
  QcState,
  Recipe,
  RunHandle,
  RunRecord,
  RunSummaryRow,
  Subject,
} from "./types";

// The API answers under /api in both modes, so this is constant. In development
// Vite proxies /api to the API process; in a deployment the API is mounted at
// /api under the same server that serves this app.
//
// It was empty in a production build until the API moved under /api, because
// the API's routes sat at the root there. That also made /subjects an API
// route, so reloading the subjects page returned JSON rather than the app.
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  // Declared explicitly rather than as a constructor parameter property, which
  // TypeScript's erasableSyntaxOnly mode disallows.
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* a non-JSON error body is not worth failing over */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  jobs: (limit = 20) => request<JobRow[]>(`/jobs?limit=${limit}`),
  subjects: () => request<Subject[]>("/subjects"),
  recipes: () => request<Recipe[]>("/recipes"),
  runs: () => request<RunSummaryRow[]>("/runs"),
  run: (id: string) => request<RunRecord>(`/runs/${id}`),
  runStatus: (handle: string) => request<RunHandle>(`/runs/status/${handle}`),

  /** Ask the agent to choose, to explain, or to re-check what you edited.
   *
   *  `recipe` null means let it choose from the question. `params` are values
   *  already set: they win over anything inferred, and the guardrail dry-run in
   *  the answer then describes the run you would actually start. */
  propose: (body: {
    question: string;
    study_id?: string;
    session?: string;
    recipe?: string | null;
    params?: Record<string, unknown>;
    cleared?: string[];
  }) => request<Proposal>("/agent/propose", {
    method: "POST",
    body: JSON.stringify(body),
  }),

  createRun: (body: {
    recipe: string;
    study_id: string;
    session: string;
    claim: string;
    params: Record<string, unknown>;
    overrides?: Record<string, string>;
  }) => request<RunHandle>("/runs", { method: "POST", body: JSON.stringify(body) }),

  fileUrl: (runId: string, path: string) => `${BASE}/runs/${runId}/files/${path}`,

  // Quality control
  qc: (studyId: string) => request<QcState>(`/qc/${studyId}`),
  qcPropose: (studyId: string) =>
    request<QcState>(`/qc/${studyId}/propose`, { method: "POST" }),
  qcDecide: (studyId: string, body: {
    flag_id: string; approved: boolean; reviewer: string; reason?: string;
    action_taken?: string | null;
  }) => request<QcState>(`/qc/${studyId}/decisions`, { method: "PUT", body: JSON.stringify(body) }),
  qcDecideBulk: (studyId: string, body: {
    approved: boolean; reviewer: string; reason?: string;
    flag_type?: string; severity?: string; target?: string;
  }) => request<QcState & { n_decided: number }>(`/qc/${studyId}/decisions/bulk`, {
    method: "POST", body: JSON.stringify(body),
  }),
  qcSign: (studyId: string, reviewer: string) =>
    request<QcState>(`/qc/${studyId}/sign`, {
      method: "POST", body: JSON.stringify({ reviewer }),
    }),
  qcReopen: (studyId: string, reviewer: string, reason: string) =>
    request<QcState>(`/qc/${studyId}/reopen`, {
      method: "POST", body: JSON.stringify({ reviewer, reason }),
    }),
  qcReportUrl: (studyId: string) => `${BASE}/qc/${studyId}/report`,

  /** What a flag means and what may be done about it, from the QC config.
   *
   *  Fetched rather than hard-coded so the review screen shows the lab's own
   *  words, and so a lab that handles an artifact differently changes a config
   *  file rather than a component. */
  qcVocabulary: () => request<{
    actions: { value: string; label: string; description: string }[];
    detectors: Record<string, { label: string; means: string }>;
  }>("/qc/vocabulary"),

  compare: (a: string, b: string) =>
    request<Comparison>(`/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
};

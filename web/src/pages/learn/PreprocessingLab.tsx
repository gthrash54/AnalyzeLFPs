import { useMemo, useState } from "react";

const FS_RAW = 24000;
const CONTACTS = ["1", "2A", "2B", "2C", "3A", "3B", "3C", "4"];
const DERIVATIONS: Array<[number, number]> = [
  [1, 0],
  [2, 0],
  [3, 0],
  [4, 7],
  [5, 7],
  [6, 7],
  [7, 0],
];
const CUTOFF_FRACTION = 0.8;

type ArtifactKind = "common" | "ring1" | "segment";

const ARTIFACTS: Record<ArtifactKind, { label: string; blurb: string; amps: number[] }> = {
  common: {
    label: "Reference moves (common mode)",
    blurb:
      "The shared reference electrode shifts, so every contact sees the same thing. This is the case guardrail G1 exists for.",
    amps: Array(8).fill(30),
  },
  ring1: {
    label: "Artifact on ring 1 only",
    blurb:
      "Ring 1 is the reference for four of the seven derivations, so a montage does not remove this. It copies it.",
    amps: [30, 0, 0, 0, 0, 0, 0, 0],
  },
  segment: {
    label: "Artifact on segment 3B only",
    blurb: "A single segment contact feeds exactly one derivation, so the montage neither hides nor spreads it.",
    amps: [0, 0, 0, 0, 0, 30, 0, 0],
  },
};

const BANDS: Record<string, [number, number]> = {
  "beta 13-30": [13, 30],
  "high gamma 70-150": [70, 150],
  "broadband to 400": [1, 400],
};

function Bars({
  values,
  labels,
  color,
  caption,
}: {
  values: number[];
  labels: string[];
  color: string;
  caption: string;
}) {
  const peak = Math.max(...values.map(Math.abs), 1);
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
      <div className="text-[11px] font-medium text-stone-600">{caption}</div>
      <div className="mt-2 flex items-end gap-1" style={{ height: 76 }}>
        {values.map((v, i) => (
          <div key={labels[i]} className="flex flex-1 flex-col items-center justify-end">
            <span className="text-[9px] text-stone-500">{Math.abs(v) < 0.05 ? "" : Math.abs(v).toFixed(0)}</span>
            <div
              className="w-full rounded-sm"
              style={{
                height: `${Math.max(1, (Math.abs(v) / peak) * 54)}px`,
                backgroundColor: Math.abs(v) < 0.05 ? "#d6d3d1" : color,
              }}
            />
            <span className="mt-1 text-[9px] text-stone-500">{labels[i]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PreprocessingLab() {
  const [kind, setKind] = useState<ArtifactKind>("common");
  const [targetHz, setTargetHz] = useState<number>(1000);
  const [bandName, setBandName] = useState<string>("high gamma 70-150");

  const raw = ARTIFACTS[kind].amps;
  const derived = useMemo(
    () => DERIVATIONS.map(([plus, minus]) => raw[plus] - raw[minus]),
    [raw],
  );
  const derivationLabels = DERIVATIONS.map(([p, m]) => `${CONTACTS[p]}-${CONTACTS[m]}`);

  const survivingRaw = raw.filter((v) => Math.abs(v) > 0.05).length;
  const survivingDer = derived.filter((v) => Math.abs(v) > 0.05).length;

  const plan = useMemo(() => {
    const factor = targetHz <= 0 || targetHz >= FS_RAW ? 1 : Math.max(1, Math.floor(FS_RAW / targetHz));
    const achieved = FS_RAW / factor;
    const usable = (achieved / 2) * CUTOFF_FRACTION;
    const band = BANDS[bandName];
    const refusal =
      band[1] > usable
        ? `requested band reaches ${band[1]} Hz but decimating to ${achieved.toFixed(1)} Hz leaves only ${usable.toFixed(1)} Hz usable`
        : null;
    return { factor, achieved, usable, refusal, stages: factor <= 13 ? 1 : 2 };
  }, [targetHz, bandName]);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-stone-200 bg-stone-900 p-6 text-white shadow-sm">
        <div className="inline-flex items-center gap-2 rounded-md border border-cyan-800/60 bg-cyan-950 px-2.5 py-1 text-xs font-medium text-cyan-400">
          Acquisition · The Preprocessing Contract · draws on Linear Algebra and Signal Processing
        </div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">The Preprocessing Contract</h1>
        <p className="mt-1 max-w-3xl text-sm text-stone-300">
          Re-referencing and decimation commute exactly, so their order is a convention. Artifact
          detection does not commute with either, so its position changes the answer. Everything
          below mirrors <span className="font-mono text-stone-200">src/dbsspeech/preprocess/</span>.
        </p>
        <a
          href="/notebooks/01_preprocessing_contract_student.ipynb"
          download="01_preprocessing_contract_student.ipynb"
          className="mt-4 inline-block rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-stone-950 shadow-sm transition-colors hover:bg-cyan-400"
        >
          Download Workbook (.ipynb)
        </a>
        <a
          href="/notebooks/01_preprocessing_contract_solutions.ipynb"
          download="01_preprocessing_contract_solutions.ipynb"
          className="mt-4 ml-2 inline-block rounded-lg border border-stone-600 px-4 py-2 text-sm font-semibold text-stone-200 transition-colors hover:bg-stone-800"
        >
          Solutions
        </a>
      </div>

      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-stone-900">
          1. What a montage does to an artifact depends on its shape, not its size
        </h2>
        <p className="text-xs text-stone-500">
          All three artifacts below are 30 µV. Only their spatial distribution differs.
        </p>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {(Object.keys(ARTIFACTS) as ArtifactKind[]).map((k) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                kind === k
                  ? "bg-stone-900 text-white"
                  : "border border-stone-300 bg-white text-stone-700 hover:bg-stone-100"
              }`}
            >
              {ARTIFACTS[k].label}
            </button>
          ))}
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <Bars values={raw} labels={CONTACTS} color="#ef4444" caption="Recorded contacts (µV)" />
          <Bars
            values={derived}
            labels={derivationLabels}
            color="#06b6d4"
            caption="After bipolar_vertical (µV)"
          />
        </div>

        <div
          className={`mt-3 rounded-lg border p-3 text-xs leading-relaxed ${
            survivingDer === 0
              ? "border-emerald-200 bg-emerald-50 text-emerald-900"
              : survivingDer > survivingRaw
              ? "border-rose-200 bg-rose-50 text-rose-900"
              : "border-stone-200 bg-stone-50 text-stone-600"
          }`}
        >
          <b>
            {survivingRaw} contact{survivingRaw === 1 ? "" : "s"} affected → {survivingDer} derivation
            {survivingDer === 1 ? "" : "s"} affected.
          </b>{" "}
          {ARTIFACTS[kind].blurb}{" "}
          {survivingDer === 0
            ? "An amplitude-threshold detector run after this montage will not see it at all."
            : survivingDer > survivingRaw
            ? "An amplitude-threshold detector run after this montage sees it on more channels than actually recorded it."
            : ""}
        </div>

        <p className="mt-3 text-xs leading-relaxed text-stone-600">
          Thresholding is nonlinear, so it does not commute with the montage. Detect on contacts and
          detect on derivations are two different procedures that disagree about which samples are
          artifact. Neither is wrong, and a run record that says only "artifact rejection was
          applied" has not said which question was asked.
        </p>
      </div>

      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-stone-900">2. The decimation gate, which is guardrail G6</h2>
        <p className="text-xs text-stone-500">
          Usable bandwidth after decimation is 0.4 × the new rate, not half of it.
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="flex justify-between text-xs font-medium text-stone-700">
              <span>Target rate: {targetHz} Hz</span>
              <span className="text-stone-600">from {FS_RAW} Hz</span>
            </div>
            <input
              type="range"
              aria-label="Decimation target rate in hertz"
              min={50}
              max={2000}
              step={10}
              value={targetHz}
              onChange={(e) => setTargetHz(Number(e.target.value))}
              className="mt-1 w-full accent-cyan-600"
            />
          </div>
          <div>
            <div className="text-xs font-medium text-stone-700">Requested band</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {Object.keys(BANDS).map((b) => (
                <button
                  key={b}
                  onClick={() => setBandName(b)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    bandName === b
                      ? "bg-stone-900 text-white"
                      : "border border-stone-300 bg-white text-stone-700 hover:bg-stone-100"
                  }`}
                >
                  {b}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
          {[
            ["Factor", `${plan.factor}`, `${plan.stages} stage${plan.stages > 1 ? "s" : ""}`],
            ["Achieved rate", `${plan.achieved.toFixed(1)} Hz`, "integer factors only"],
            ["Nyquist", `${(plan.achieved / 2).toFixed(1)} Hz`, "what you might assume"],
            ["Usable bandwidth", `${plan.usable.toFixed(1)} Hz`, "what you actually have"],
          ].map(([label, value, sub]) => (
            <div key={label} className="rounded-lg border border-stone-200 bg-stone-50 p-2.5">
              <span className="text-[11px] uppercase tracking-wider text-stone-500">{label}</span>
              <p className="text-base font-bold text-stone-900">{value}</p>
              <span className="text-[10px] text-stone-600">{sub}</span>
            </div>
          ))}
        </div>

        <div
          className={`mt-3 rounded-lg border p-3 text-xs leading-relaxed ${
            plan.refusal
              ? "border-rose-200 bg-rose-50 text-rose-900"
              : "border-emerald-200 bg-emerald-50 text-emerald-900"
          }`}
        >
          {plan.refusal ? (
            <>
              <b>G6 refuses this run.</b> {plan.refusal}. Severity is <span className="font-mono">block</span>,
              and unlike most guardrails there is nothing a reviewer can reason past: the content is
              gone, and a spectrum will still happily plot values where it used to be.
            </>
          ) : (
            <>
              <b>G6 allows this run.</b> The requested band tops out at {BANDS[bandName][1]} Hz, under
              the {plan.usable.toFixed(1)} Hz the data supports after anti-alias filtering. Note that
              the achieved rate is {plan.achieved.toFixed(1)} Hz rather than the {targetHz} Hz you
              asked for, because the decimation factor is an integer. That number, not the target, is
              what belongs in the run record.
            </>
          )}
        </div>
      </div>
    </div>
  );
}

import { useMemo, useState } from "react";

/** Frequency in [0, fs/2] that is indistinguishable from `f` when sampled at `fs`. */
function aliasFrequency(f: number, fs: number): number {
  const folded = ((f % fs) + fs) % fs;
  return folded > fs / 2 ? fs - folded : folded;
}

const WINDOW_S = 0.1;
const RENDER_POINTS = 1000; // ~10 kHz render rate, far above any slider maximum
const SENSE_RATES = [200, 250, 422, 500, 1000] as const;
const BETA_LO = 13;
const BETA_HI = 30;

interface PlotGeom {
  w: number;
  h: number;
  mid: number;
  amp: number;
}

const GEOM: PlotGeom = { w: 640, h: 180, mid: 90, amp: 62 };

function toPath(values: number[], geom: PlotGeom): string {
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * geom.w;
      const y = geom.mid - v * geom.amp;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function SamplingLab() {
  const [trueFreq, setTrueFreq] = useState<number>(30);
  const [sampleRate, setSampleRate] = useState<number>(40);
  const [stimFreq, setStimFreq] = useState<number>(135);
  const [senseRate, setSenseRate] = useState<number>(250);

  const nyquist = sampleRate / 2;
  const alias = useMemo(() => aliasFrequency(trueFreq, sampleRate), [trueFreq, sampleRate]);
  const isAliased = trueFreq > nyquist;

  // Densely rendered "continuous" signal and its aliased twin.
  const trueCurve = useMemo(
    () =>
      Array.from({ length: RENDER_POINTS }, (_, i) =>
        Math.cos(2 * Math.PI * trueFreq * ((i / (RENDER_POINTS - 1)) * WINDOW_S)),
      ),
    [trueFreq],
  );
  const aliasCurve = useMemo(
    () =>
      Array.from({ length: RENDER_POINTS }, (_, i) =>
        Math.cos(2 * Math.PI * alias * ((i / (RENDER_POINTS - 1)) * WINDOW_S)),
      ),
    [alias],
  );

  // The samples the converter actually keeps.
  const samples = useMemo(() => {
    const n = Math.floor(WINDOW_S * sampleRate) + 1;
    return Array.from({ length: n }, (_, i) => {
      const t = i / sampleRate;
      return { t, v: Math.cos(2 * Math.PI * trueFreq * t) };
    });
  }, [trueFreq, sampleRate]);

  // Largest disagreement between the two curves at any sampling instant.
  const maxResidual = useMemo(
    () =>
      samples.reduce(
        (acc, s) => Math.max(acc, Math.abs(s.v - Math.cos(2 * Math.PI * alias * s.t))),
        0,
      ),
    [samples, alias],
  );

  const harmonics = useMemo(
    () =>
      Array.from({ length: 6 }, (_, i) => {
        const k = i + 1;
        const landed = aliasFrequency(k * stimFreq, senseRate);
        return { k, trueHz: k * stimFreq, landed, inBeta: landed >= BETA_LO && landed <= BETA_HI };
      }),
    [stimFreq, senseRate],
  );
  const betaHits = harmonics.filter((h) => h.inBeta);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-stone-200 bg-stone-900 p-6 text-white shadow-sm">
        <div className="inline-flex items-center gap-2 rounded-md bg-cyan-950 px-2.5 py-1 text-xs font-medium text-cyan-400 border border-cyan-800/60">
          Foundations · Signal Processing for Neural Time Series
        </div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">Sampling, Nyquist, and Aliasing</h1>
        <p className="mt-1 max-w-3xl text-sm text-stone-300">
          Aliasing is not noise and not an approximation. It is a deterministic relabelling that
          no later filter can undo. Below, the true signal and its alias pass through identical
          samples, which is the whole of the problem.
        </p>
        <a
          href="/notebooks/01_sampling_nyquist_aliasing_student.ipynb"
          download="01_sampling_nyquist_aliasing_student.ipynb"
          className="mt-4 inline-block rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-stone-950 shadow-sm transition-colors hover:bg-cyan-400"
        >
          Download Workbook (.ipynb)
        </a>
        <a
          href="/notebooks/01_sampling_nyquist_aliasing_solutions.ipynb"
          download="01_sampling_nyquist_aliasing_solutions.ipynb"
          className="mt-4 ml-2 inline-block rounded-lg border border-stone-600 px-4 py-2 text-sm font-semibold text-stone-200 transition-colors hover:bg-stone-800"
        >
          Solutions
        </a>
      </div>

      {/* Panel 1: the folding map, shown on the samples themselves */}
      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-stone-900">
          1. Two frequencies, one set of samples
        </h2>
        <p className="text-xs text-stone-500">
          Raise the signal above the Nyquist frequency and watch the alias lock onto every sample.
        </p>

        <div className="mt-4 rounded-lg border border-stone-800 bg-stone-950 p-3">
          <svg viewBox={`0 0 ${GEOM.w} ${GEOM.h}`} width="100%" height={GEOM.h}>
            role="img"
            aria-label="A cosine at the chosen frequency, the samples kept at the chosen rate, and, when aliased, the lower-frequency curve that passes through the identical samples."
            <line x1={0} y1={GEOM.mid} x2={GEOM.w} y2={GEOM.mid} stroke="#404040" strokeWidth={1} />
            <path d={toPath(trueCurve, GEOM)} fill="none" stroke="#06b6d4" strokeWidth={2} />
            {isAliased && (
              <path
                d={toPath(aliasCurve, GEOM)}
                fill="none"
                stroke="#f59e0b"
                strokeWidth={2}
                strokeDasharray="5 4"
              />
            )}
            {samples.map((s) => (
              <circle
                key={s.t}
                cx={(s.t / WINDOW_S) * GEOM.w}
                cy={GEOM.mid - s.v * GEOM.amp}
                r={4}
                fill="#fafaf9"
                stroke="#171717"
                strokeWidth={1.5}
              />
            ))}
          </svg>
          <div className="mt-1 flex flex-wrap gap-x-4 text-[11px] text-stone-600">
            <span>
              <b className="text-cyan-400">Solid line</b> true signal, {trueFreq} Hz
            </span>
            {isAliased && (
              <span>
                <b className="text-amber-500">Dashed line</b> alias, {alias.toFixed(1)} Hz
              </span>
            )}
            <span>
              <b className="text-stone-200">Dots</b> samples kept at {sampleRate} Hz
            </span>
          </div>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="flex justify-between text-xs font-medium text-stone-700">
              <span>Signal frequency: {trueFreq} Hz</span>
            </div>
            <input
              type="range"
              aria-label="Signal frequency in hertz"
              min={5}
              max={200}
              step={1}
              value={trueFreq}
              onChange={(e) => setTrueFreq(Number(e.target.value))}
              className="mt-1 w-full accent-cyan-600"
            />
          </div>
          <div>
            <div className="flex justify-between text-xs font-medium text-stone-700">
              <span>Sampling rate: {sampleRate} Hz</span>
              <span className="text-stone-600">Nyquist {nyquist.toFixed(1)} Hz</span>
            </div>
            <input
              type="range"
              aria-label="Sampling rate in hertz"
              min={20}
              max={500}
              step={1}
              value={sampleRate}
              onChange={(e) => setSampleRate(Number(e.target.value))}
              className="mt-1 w-full accent-purple-600"
            />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2.5">
            <span className="text-[11px] uppercase tracking-wider text-stone-500">Nyquist</span>
            <p className="text-base font-bold text-stone-900">{nyquist.toFixed(1)} Hz</p>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2.5">
            <span className="text-[11px] uppercase tracking-wider text-stone-500">Recorded as</span>
            <p className={`text-base font-bold ${isAliased ? "text-amber-700" : "text-stone-900"}`}>
              {alias.toFixed(1)} Hz
            </p>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2.5">
            <span className="text-[11px] uppercase tracking-wider text-stone-500">Status</span>
            <p
              className={`text-base font-bold ${isAliased ? "text-rose-700" : "text-emerald-700"}`}
            >
              {isAliased ? "Aliased" : "Faithful"}
            </p>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2.5">
            <span className="text-[11px] uppercase tracking-wider text-stone-500">
              Max sample disagreement
            </span>
            <p className="text-base font-bold text-stone-900">{maxResidual.toExponential(1)}</p>
          </div>
        </div>

        <p className="mt-3 rounded-lg border border-stone-200 bg-stone-50 p-3 text-xs leading-relaxed text-stone-600">
          {isAliased ? (
            <>
              At {sampleRate} Hz the converter cannot represent {trueFreq} Hz, so it records{" "}
              {alias.toFixed(1)} Hz instead. The two curves differ by at most{" "}
              {maxResidual.toExponential(1)} at any sampling instant, which is floating-point
              noise. The recording is not a degraded copy of {trueFreq} Hz. It is an exact copy of{" "}
              {alias.toFixed(1)} Hz.
            </>
          ) : (
            <>
              {trueFreq} Hz sits below the {nyquist.toFixed(1)} Hz Nyquist frequency, so the samples
              determine it uniquely and reconstruction is exact. Raise the signal above Nyquist, or
              lower the sampling rate, to break that.
            </>
          )}
        </p>
      </div>

      {/* Panel 2: stimulation harmonics folding into beta */}
      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-stone-900">
          2. Where a stimulation artifact lands
        </h2>
        <p className="text-xs text-stone-500">
          A stimulation pulse train carries energy at every integer multiple of its rate. Each
          harmonic folds independently.
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="text-xs font-medium text-stone-700">
              Stimulation frequency: {stimFreq} Hz
            </div>
            <input
              type="range"
              aria-label="Stimulation frequency in hertz"
              min={100}
              max={200}
              step={1}
              value={stimFreq}
              onChange={(e) => setStimFreq(Number(e.target.value))}
              className="mt-1 w-full accent-rose-600"
            />
          </div>
          <div>
            <div className="text-xs font-medium text-stone-700">Sensing rate</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {SENSE_RATES.map((r) => (
                <button
                  key={r}
                  onClick={() => setSenseRate(r)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    senseRate === r
                      ? "bg-stone-900 text-white"
                      : "border border-stone-300 bg-white text-stone-700 hover:bg-stone-100"
                  }`}
                >
                  {r} Hz
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-stone-200 text-left text-stone-500">
                <th className="py-1.5 font-medium">Harmonic</th>
                <th className="py-1.5 font-medium">True frequency</th>
                <th className="py-1.5 font-medium">Recorded as</th>
                <th className="py-1.5 font-medium">Lands in beta ({BETA_LO} to {BETA_HI} Hz)</th>
              </tr>
            </thead>
            <tbody>
              {harmonics.map((h) => (
                <tr
                  key={h.k}
                  className={`border-b border-stone-100 ${h.inBeta ? "bg-rose-50" : ""}`}
                >
                  <td className="py-1.5 font-mono text-stone-700">h{h.k}</td>
                  <td className="py-1.5 font-mono text-stone-600">{h.trueHz.toFixed(0)} Hz</td>
                  <td
                    className={`py-1.5 font-mono font-semibold ${
                      h.inBeta ? "text-rose-700" : "text-stone-900"
                    }`}
                  >
                    {h.landed.toFixed(1)} Hz
                  </td>
                  <td className="py-1.5">
                    {h.inBeta ? (
                      <span className="font-semibold text-rose-700">yes</span>
                    ) : (
                      <span className="text-stone-600">no</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div
          className={`mt-4 rounded-lg border p-3 text-xs leading-relaxed ${
            betaHits.length > 0
              ? "border-rose-200 bg-rose-50 text-rose-900"
              : "border-emerald-200 bg-emerald-50 text-emerald-900"
          }`}
        >
          {betaHits.length > 0 ? (
            <>
              <b>
                Contaminated: harmonic{betaHits.length > 1 ? "s" : ""}{" "}
                {betaHits.map((h) => `h${h.k}`).join(", ")} land inside beta
              </b>{" "}
              at {betaHits.map((h) => `${h.landed.toFixed(1)} Hz`).join(", ")}. This is narrowband,
              it sits where the physiology is expected, and it scales with stimulation amplitude,
              which is the covariation an experimenter is hoping to see. Sampling at {senseRate} Hz
              cannot separate it from real beta, and neither can anything applied afterwards.
            </>
          ) : (
            <>
              <b>Clear:</b> no harmonic up to the sixth lands inside beta at {senseRate} Hz with{" "}
              {stimFreq} Hz stimulation. Sweep the stimulation slider across the clinical range to
              see how narrow this window is. Band edges mirror{" "}
              <span className="font-mono">configs/bands.yaml</span>.
            </>
          )}
        </div>
      </div>
    </div>
  );
}

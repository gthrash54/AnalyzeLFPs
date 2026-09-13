import { useMemo, useState } from "react";

const FS = 500;
const N = 1000;
const ONSET_S = 1.0;
const SMOOTH_M = 25;

interface Biquad {
  b0: number;
  b1: number;
  b2: number;
  a1: number;
  a2: number;
}

/** RBJ cookbook bandpass, constant 0 dB peak gain. */
function designBandpass(centerHz: number, bandwidthHz: number, fs: number): Biquad {
  const w0 = (2 * Math.PI * centerHz) / fs;
  const q = centerHz / bandwidthHz;
  const alpha = Math.sin(w0) / (2 * q);
  const a0 = 1 + alpha;
  return {
    b0: alpha / a0,
    b1: 0,
    b2: -alpha / a0,
    a1: (-2 * Math.cos(w0)) / a0,
    a2: (1 - alpha) / a0,
  };
}

function applyBiquad(x: number[], c: Biquad): number[] {
  const y = new Array<number>(x.length).fill(0);
  let x1 = 0;
  let x2 = 0;
  let y1 = 0;
  let y2 = 0;
  for (let n = 0; n < x.length; n++) {
    const out = c.b0 * x[n] + c.b1 * x1 + c.b2 * x2 - c.a1 * y1 - c.a2 * y2;
    x2 = x1;
    x1 = x[n];
    y2 = y1;
    y1 = out;
    y[n] = out;
  }
  return y;
}

/** Two cascaded sections, i.e. a fourth-order response, applied causally. */
function filterCausal(x: number[], c: Biquad): number[] {
  return applyBiquad(applyBiquad(x, c), c);
}

/** Forward then backward: zero phase, and the magnitude response squared. */
function filterZeroPhase(x: number[], c: Biquad): number[] {
  const fwd = filterCausal(x, c);
  const rev = filterCausal([...fwd].reverse(), c);
  return rev.reverse();
}

/** Onset in ms: rectify, smooth, undo the smoother's known linear-phase delay. */
function envelopeOnsetMs(y: number[]): number | null {
  const rect = y.map(Math.abs);
  const env = new Array<number>(y.length).fill(0);
  for (let n = 0; n < y.length; n++) {
    let acc = 0;
    for (let k = 0; k < SMOOTH_M; k++) if (n - k >= 0) acc += rect[n - k];
    env[n] = acc / SMOOTH_M;
  }
  const lag = (SMOOTH_M - 1) / 2;
  const peak = Math.max(...env);
  if (peak <= 0) return null;
  for (let n = 0; n < env.length; n++) {
    if (env[n] > 0.25 * peak) return ((n - lag) / FS) * 1000;
  }
  return null;
}

function path(values: number[], w: number, h: number, scale: number): string {
  const mid = h / 2;
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = Math.max(2, Math.min(h - 2, mid - v * scale));
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

function Trace({
  values,
  color,
  label,
  markerMs,
}: {
  values: number[];
  color: string;
  label: string;
  markerMs: number | null;
}) {
  const peak = Math.max(...values.map(Math.abs), 1e-9);
  const w = 620;
  const h = 74;
  return (
    <div className="rounded-lg border border-stone-800 bg-stone-950 p-2">
      <div className="flex justify-between text-[11px] text-stone-400">
        <span>{label}</span>
        <span className="font-mono">peak {peak.toFixed(3)}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h}>
        role="img"
        aria-label="A signal trace with the true onset marked in green and the detected onset in amber."
        <line x1={0} y1={h / 2} x2={w} y2={h / 2} stroke="#404040" strokeWidth={0.8} />
        <line
          x1={(ONSET_S * FS * w) / N}
          y1={0}
          x2={(ONSET_S * FS * w) / N}
          y2={h}
          stroke="#10b981"
          strokeWidth={1.2}
          strokeDasharray="4 3"
        />
        {markerMs !== null && (
          <line
            x1={((markerMs / 1000) * FS * w) / N}
            y1={0}
            x2={((markerMs / 1000) * FS * w) / N}
            y2={h}
            stroke="#f59e0b"
            strokeWidth={1.6}
          />
        )}
        <path d={path(values, w, h, (h / 2 - 4) / peak)} fill="none" stroke={color} strokeWidth={1.5} />
      </svg>
    </div>
  );
}

export function FilterLab() {
  const [centerHz, setCenterHz] = useState<number>(20);
  const [bandwidthHz, setBandwidthHz] = useState<number>(17);

  const coeffs = useMemo(() => designBandpass(centerHz, bandwidthHz, FS), [centerHz, bandwidthHz]);

  const burst = useMemo(() => {
    const out: number[] = [];
    for (let n = 0; n < N; n++) {
      const t = n / FS;
      const rise = t >= ONSET_S ? 1 - Math.exp(-(t - ONSET_S) / 0.05) : 0;
      out.push(rise * Math.sin(2 * Math.PI * centerHz * t));
    }
    return out;
  }, [centerHz]);

  const causal = useMemo(() => filterCausal(burst, coeffs), [burst, coeffs]);
  const zeroPhase = useMemo(() => filterZeroPhase(burst, coeffs), [burst, coeffs]);

  const onsetTrue = ONSET_S * 1000;
  const onsetCausal = useMemo(() => envelopeOnsetMs(causal), [causal]);
  const onsetZero = useMemo(() => envelopeOnsetMs(zeroPhase), [zeroPhase]);
  const errCausal = onsetCausal === null ? null : onsetCausal - onsetTrue;
  const errZero = onsetZero === null ? null : onsetZero - onsetTrue;

  // Step response: how many cycles of oscillation the filter invents from an edge.
  const step = useMemo(() => Array.from({ length: N }, (_, n) => (n >= N / 2 ? 1 : 0)), []);
  const rung = useMemo(() => filterZeroPhase(step, coeffs), [step, coeffs]);
  const ringCycles = useMemo(() => {
    const peak = Math.max(...rung.map(Math.abs));
    if (peak <= 0) return 0;
    const idx = rung.map((v, i) => (Math.abs(v) > 0.1 * peak ? i : -1)).filter((i) => i >= 0);
    if (idx.length < 2) return 0;
    return (((idx[idx.length - 1] - idx[0]) / FS) * centerHz);
  }, [rung, centerHz]);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-stone-200 bg-stone-900 p-6 text-white shadow-sm">
        <div className="inline-flex items-center gap-2 rounded-md border border-cyan-800/60 bg-cyan-950 px-2.5 py-1 text-xs font-medium text-cyan-400">
          Foundations · Signal Processing for Neural Time Series
        </div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">Filtering and Zero-Phase Distortion</h1>
        <p className="mt-1 max-w-3xl text-sm text-stone-300">
          Everyone reads the magnitude response. The latency errors live in the phase response, and
          the invented oscillations live in the impulse response. Both are below.
        </p>
        <a
          href="/notebooks/02_filtering_zero_phase_student.ipynb"
          download="02_filtering_zero_phase_student.ipynb"
          className="mt-4 inline-block rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-stone-950 shadow-sm transition-colors hover:bg-cyan-400"
        >
          Download Workbook (.ipynb)
        </a>
        <a
          href="/notebooks/02_filtering_zero_phase_solutions.ipynb"
          download="02_filtering_zero_phase_solutions.ipynb"
          className="mt-4 ml-2 inline-block rounded-lg border border-stone-600 px-4 py-2 text-sm font-semibold text-stone-200 transition-colors hover:bg-stone-800"
        >
          Solutions
        </a>
      </div>

      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-stone-900">1. What filtering does to a reported onset</h2>
        <p className="text-xs text-stone-500">
          Green line is the true onset. Amber is where an envelope detector reports it.
        </p>

        <div className="mt-4 space-y-2">
          <Trace values={burst} color="#a3a3a3" label="Input: burst with a known onset" markerMs={null} />
          <Trace values={causal} color="#ef4444" label="Causal filter (one forward pass)" markerMs={onsetCausal} />
          <Trace values={zeroPhase} color="#06b6d4" label="Zero-phase filter (forward then backward)" markerMs={onsetZero} />
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="text-xs font-medium text-stone-700">Center frequency: {centerHz} Hz</div>
            <input
              type="range"
              aria-label="Filter centre frequency in hertz"
              min={5}
              max={40}
              step={1}
              value={centerHz}
              onChange={(e) => setCenterHz(Number(e.target.value))}
              className="mt-1 w-full accent-cyan-600"
            />
          </div>
          <div>
            <div className="flex justify-between text-xs font-medium text-stone-700">
              <span>Bandwidth: {bandwidthHz} Hz</span>
              <span className="text-stone-600">Q = {(centerHz / bandwidthHz).toFixed(2)}</span>
            </div>
            <input
              type="range"
              aria-label="Filter bandwidth in hertz"
              min={2}
              max={20}
              step={1}
              value={bandwidthHz}
              onChange={(e) => setBandwidthHz(Number(e.target.value))}
              className="mt-1 w-full accent-purple-600"
            />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 text-center">
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
            <span className="text-[11px] uppercase tracking-wider text-stone-500">Causal onset error</span>
            <p className="text-lg font-bold text-rose-700">
              {errCausal === null ? "n/a" : `${errCausal > 0 ? "+" : ""}${errCausal.toFixed(0)} ms`}
            </p>
            <span className="text-[10px] text-stone-600">always late, never early</span>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
            <span className="text-[11px] uppercase tracking-wider text-stone-500">Zero-phase onset error</span>
            <p className={`text-lg font-bold ${errZero !== null && errZero < 0 ? "text-amber-700" : "text-cyan-700"}`}>
              {errZero === null ? "n/a" : `${errZero > 0 ? "+" : ""}${errZero.toFixed(0)} ms`}
            </p>
            <span className="text-[10px] text-stone-600">
              {errZero !== null && errZero < 0 ? "before the event" : "no systematic lag"}
            </span>
          </div>
        </div>

        <p className="mt-3 rounded-lg border border-stone-200 bg-stone-50 p-3 text-xs leading-relaxed text-stone-600">
          {errZero !== null && errZero < 0 ? (
            <>
              <b>The zero-phase filter now reports the burst starting {Math.abs(errZero).toFixed(0)} ms
              before it started.</b>{" "}
              Forward-backward filtering is non-causal, so it is permitted to smear energy backwards in
              time. Nothing in a magnitude response plot shows this, and no reviewer checks whether a
              response preceded its stimulus.
            </>
          ) : (
            <>
              The causal filter is late by {errCausal === null ? "n/a" : `${errCausal.toFixed(0)} ms`},
              and it can never be early. Narrow the bandwidth or lower the center frequency and watch
              that grow, then watch the zero-phase error cross into negative territory.
            </>
          )}
        </p>
      </div>

      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-stone-900">2. The oscillation the filter invented</h2>
        <p className="text-xs text-stone-500">
          The input below is a single step. It contains no rhythm at any frequency.
        </p>
        <div className="mt-3 space-y-2">
          <Trace values={step} color="#a3a3a3" label="Input: one step" markerMs={null} />
          <Trace values={rung} color="#f59e0b" label={`Filtered to ${centerHz} Hz, ${bandwidthHz} Hz wide`} markerMs={null} />
        </div>
        <div
          className={`mt-3 rounded-lg border p-3 text-xs leading-relaxed ${
            ringCycles > 6
              ? "border-rose-200 bg-rose-50 text-rose-900"
              : "border-stone-200 bg-stone-50 text-stone-600"
          }`}
        >
          The filter turned a step into roughly <b>{ringCycles.toFixed(1)} cycles</b> of oscillation at{" "}
          {centerHz} Hz. A movement artifact, an electrode touch, and a stimulation onset are all
          steps. Narrow the bandwidth and the invented burst gets longer, because a narrow band in
          frequency is a long function in time. This is the mechanism guardrail G5 exists to catch.
        </div>
      </div>
    </div>
  );
}

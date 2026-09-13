import { useMemo, useState } from "react";

const FS = 500;
const N = 500; // 1 second
const BETA_COMPONENTS = [15, 19, 23, 27]; // narrowband, so phase is well defined (SIG 6)

interface Complex {
  re: number;
  im: number;
}

/**
 * A narrowband beta signal built from known sinusoids, so its analytic signal is
 * exact rather than estimated. Avoids a numerical Hilbert transform entirely.
 */
function narrowband(seed: number, amplitude: number): { real: number[]; analytic: Complex[] } {
  let s = seed;
  const rand = () => {
    s = (1103515245 * s + 12345) % 2147483648;
    return s / 2147483648;
  };
  const phases = BETA_COMPONENTS.map(() => rand() * 2 * Math.PI);
  const real: number[] = [];
  const analytic: Complex[] = [];
  for (let n = 0; n < N; n++) {
    const t = n / FS;
    let re = 0;
    let im = 0;
    BETA_COMPONENTS.forEach((f, k) => {
      const arg = 2 * Math.PI * f * t + phases[k];
      re += Math.cos(arg);
      im += Math.sin(arg);
    });
    const scale = amplitude / BETA_COMPONENTS.length;
    real.push(re * scale);
    analytic.push({ re: re * scale, im: im * scale });
  }
  return { real, analytic };
}

/** Shift a narrowband analytic signal in time by `samples`, wrapping. */
function delay(sig: { real: number[]; analytic: Complex[] }, samples: number) {
  const shift = ((samples % N) + N) % N;
  return {
    real: sig.real.map((_, i) => sig.real[(i - shift + N) % N]),
    analytic: sig.analytic.map((_, i) => sig.analytic[(i - shift + N) % N]),
  };
}

function addSignals(a: { real: number[]; analytic: Complex[] }, b: { real: number[]; analytic: Complex[] }) {
  return {
    real: a.real.map((v, i) => v + b.real[i]),
    analytic: a.analytic.map((v, i) => ({ re: v.re + b.analytic[i].re, im: v.im + b.analytic[i].im })),
  };
}

function scaleSignal(a: { real: number[]; analytic: Complex[] }, k: number) {
  return {
    real: a.real.map((v) => v * k),
    analytic: a.analytic.map((v) => ({ re: v.re * k, im: v.im * k })),
  };
}

/** Phase-locking value and mean phase lag between two analytic signals. */
function plvAndLag(a: Complex[], b: Complex[]): { plv: number; lagDeg: number } {
  let sr = 0;
  let si = 0;
  for (let i = 0; i < a.length; i++) {
    const pa = Math.atan2(a[i].im, a[i].re);
    const pb = Math.atan2(b[i].im, b[i].re);
    const d = pa - pb;
    sr += Math.cos(d);
    si += Math.sin(d);
  }
  const n = a.length;
  return {
    plv: Math.hypot(sr / n, si / n),
    lagDeg: (Math.atan2(si / n, sr / n) * 180) / Math.PI,
  };
}

function tracePath(values: number[], w: number, h: number): string {
  const peak = Math.max(...values.map(Math.abs), 1e-9);
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h / 2 - (v / peak) * (h / 2 - 3);
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

export function ZeroLagLab() {
  const [localPct, setLocalPct] = useState<number>(20);
  const [delayMs, setDelayMs] = useState<number>(0);

  const { ch1, ch2, plv, lagDeg } = useMemo(() => {
    const source = narrowband(7, 1);
    const local1 = narrowband(101, localPct / 100);
    const local2 = narrowband(202, localPct / 100);

    // Contact 1 sees the source directly. Contact 2 sees it delayed: a delay of
    // zero is volume conduction, anything else is a real interaction.
    const seen2 = delay(source, Math.round((delayMs / 1000) * FS));
    const a = addSignals(source, local1);
    const b = addSignals(scaleSignal(seen2, 0.7), local2);
    const { plv: p, lagDeg: l } = plvAndLag(a.analytic, b.analytic);
    return { ch1: a.real, ch2: b.real, plv: p, lagDeg: l };
  }, [localPct, delayMs]);

  const isZeroLag = Math.abs(lagDeg) < 10;
  const locks = plv > 0.4;

  const verdict = !locks
    ? { label: "No locking", tone: "stone", text: "Local activity dominates. Neither reading supports a claim." }
    : isZeroLag
    ? {
        label: "Zero lag: cannot distinguish",
        tone: "rose",
        text:
          "High phase locking at a lag of zero. This is exactly what one source seen by two contacts produces, and exactly what two regions synchronised at zero lag produce. The measure cannot separate them, and neither can a bigger sample.",
      }
    : {
        label: "Lagged interaction",
        tone: "emerald",
        text:
          "High phase locking at a non-zero lag. Volume conduction is instantaneous, so it cannot produce this. Something is genuinely propagating.",
      };

  const toneClass =
    verdict.tone === "rose"
      ? "border-rose-200 bg-rose-50 text-rose-900"
      : verdict.tone === "emerald"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : "border-stone-200 bg-stone-50 text-stone-700";

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-stone-200 bg-stone-900 p-6 text-white shadow-sm">
        <div className="inline-flex items-center gap-2 rounded-md border border-cyan-800/60 bg-cyan-950 px-2.5 py-1 text-xs font-medium text-cyan-400">
          Analysis · Connectivity and Spectral Coupling
        </div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">
          Phase Locking and the Zero-Lag Volume Trap
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-stone-300">
          Set the delay to zero and watch the phase-locking value reach its maximum with no
          interaction of any kind. Only the lag separates volume conduction from communication,
          and the phase-locking value discards the lag by construction.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <a
            href="/notebooks/01_plv_and_the_zero_lag_trap_student.ipynb"
            download="01_plv_and_the_zero_lag_trap_student.ipynb"
            className="inline-block rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-stone-950 shadow-sm transition-colors hover:bg-cyan-400"
          >
            Download Workbook (.ipynb)
          </a>
          <a
            href="/notebooks/01_plv_and_the_zero_lag_trap_solutions.ipynb"
            download="01_plv_and_the_zero_lag_trap_solutions.ipynb"
            className="inline-block rounded-lg border border-stone-600 px-4 py-2 text-sm font-semibold text-stone-200 transition-colors hover:bg-stone-800"
          >
            Solutions
          </a>
        </div>
      </div>

      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-stone-900">Two contacts, one shared source</h2>
        <p className="text-xs text-stone-600">
          Contact 1 solid, contact 2 dashed. Both see the same beta source plus their own local
          activity.
        </p>

        <div className="mt-3 rounded-lg border border-stone-800 bg-stone-950 p-3">
          <svg
            viewBox="0 0 620 130"
            width="100%"
            height={130}
            role="img"
            aria-label={`Two beta traces. Phase locking value ${plv.toFixed(2)}, mean phase lag ${lagDeg.toFixed(0)} degrees.`}
          >
            <line x1={0} y1={65} x2={620} y2={65} stroke="#404040" strokeWidth={0.8} />
            <path d={tracePath(ch1, 620, 130)} fill="none" stroke="#06b6d4" strokeWidth={1.8} />
            <path
              d={tracePath(ch2, 620, 130)}
              fill="none"
              stroke="#f59e0b"
              strokeWidth={1.8}
              strokeDasharray="5 4"
            />
          </svg>
          <div className="mt-1 flex gap-4 text-[11px] text-stone-400">
            <span>
              <b className="text-cyan-400">Solid</b> contact 1
            </span>
            <span>
              <b className="text-amber-500">Dashed</b> contact 2
            </span>
          </div>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="flex justify-between text-xs font-medium text-stone-700">
              <span>Propagation delay: {delayMs} ms</span>
              <span className="text-stone-600">0 = volume conduction</span>
            </div>
            <input
              type="range"
              aria-label="Propagation delay in milliseconds, where zero is pure volume conduction"
              min={0}
              max={25}
              step={1}
              value={delayMs}
              onChange={(e) => setDelayMs(Number(e.target.value))}
              className="mt-1 w-full accent-cyan-700"
            />
          </div>
          <div>
            <div className="flex justify-between text-xs font-medium text-stone-700">
              <span>Independent local activity: {localPct}%</span>
            </div>
            <input
              type="range"
              aria-label="Independent local activity at each contact, as a percentage of the shared source"
              min={0}
              max={200}
              step={5}
              value={localPct}
              onChange={(e) => setLocalPct(Number(e.target.value))}
              className="mt-1 w-full accent-purple-700"
            />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 text-center">
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
            <span className="text-[11px] uppercase tracking-wider text-stone-600">
              Phase-locking value
            </span>
            <p className="text-2xl font-bold text-stone-900">{plv.toFixed(3)}</p>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
            <span className="text-[11px] uppercase tracking-wider text-stone-600">
              Mean phase lag
            </span>
            <p
              className={`text-2xl font-bold ${
                // stone-500, not 400: a value greyed as "not meaningful" still has
                // to be readable. stone-400 on this tile is 2.48:1.
                !locks ? "text-stone-500" : isZeroLag ? "text-rose-700" : "text-emerald-700"
              }`}
            >
              {lagDeg.toFixed(0)}°
            </p>
            {!locks && (
              <span className="text-[10px] text-stone-600">
                not meaningful below a locking value of 0.4
              </span>
            )}
          </div>
        </div>

        <div className={`mt-3 rounded-lg border p-3 text-xs leading-relaxed ${toneClass}`}>
          <b>{verdict.label}.</b> {verdict.text}
        </div>

        <p className="mt-3 text-xs leading-relaxed text-stone-600">
          Leave the delay at zero and raise local activity. The phase-locking value falls, because
          independent activity dilutes the shared source, but while it stays high the lag remains
          near zero: diluting a shared source does not make it propagate. Push local activity far
          enough and the locking value collapses, at which point the lag wanders and means nothing.
          A phase lag is only a measurement while there is something locked to measure it on, which
          is why the notebook reports the two numbers together and never the lag alone.
        </p>
      </div>
    </div>
  );
}

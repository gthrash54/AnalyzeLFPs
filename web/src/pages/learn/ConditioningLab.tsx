import { useMemo, useState } from "react";

const SIGMA = 0.3;                       // S/m, homogeneous isotropic tissue
const SOURCE_X = [-1, 0, 1];             // mm
const ELECTRODE_Y = 2.0;                 // mm
const TRUE_SOURCES = [10, 25, -15];      // nA, matching the notebook

/** Fixed noise draw, so the readouts do not jitter on every render. */
const NOISE_UNIT = (() => {
  let seed = 12345;
  return Array.from({ length: 4 }, () => {
    seed = (1103515245 * seed + 12345) % 2147483648;
    return (seed / 2147483648) * 2 - 1;
  });
})();

/** Quasi-static monopole leadfield, L[i][j] = 1 / (4 pi sigma r_ij). */
function buildLeadfield(spacingMm: number): number[][] {
  const ex = [-1.5, -0.5, 0.5, 1.5].map((k) => k * spacingMm);
  return ex.map((x) =>
    SOURCE_X.map((sx) => {
      const r = Math.hypot(x - sx, ELECTRODE_Y);
      return 1 / (4 * Math.PI * SIGMA * Math.max(r, 1e-6));
    }),
  );
}

function transposeTimes(L: number[][]): number[][] {
  const p = L[0].length;
  return Array.from({ length: p }, (_, i) =>
    Array.from({ length: p }, (_, j) => L.reduce((acc, row) => acc + row[i] * row[j], 0)),
  );
}

/** Cyclic Jacobi eigenvalues of a small symmetric matrix, descending. */
function symmetricEigenvalues(input: number[][]): number[] {
  const n = input.length;
  const a = input.map((row) => [...row]);
  for (let sweep = 0; sweep < 100; sweep++) {
    let off = 0;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) off += a[i][j] * a[i][j];
    if (off < 1e-30) break;
    for (let p = 0; p < n; p++) {
      for (let q = p + 1; q < n; q++) {
        if (Math.abs(a[p][q]) < 1e-300) continue;
        const theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
        const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
        const c = 1 / Math.sqrt(t * t + 1);
        const s = t * c;
        for (let k = 0; k < n; k++) {
          const akp = a[k][p];
          const akq = a[k][q];
          a[k][p] = c * akp - s * akq;
          a[k][q] = s * akp + c * akq;
        }
        for (let k = 0; k < n; k++) {
          const apk = a[p][k];
          const aqk = a[q][k];
          a[p][k] = c * apk - s * aqk;
          a[q][k] = s * apk + c * aqk;
        }
      }
    }
  }
  return Array.from({ length: n }, (_, i) => a[i][i]).sort((x, y) => y - x);
}

/** Gaussian elimination with partial pivoting. */
function solveLinear(A: number[][], b: number[]): number[] {
  const n = b.length;
  const m = A.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < n; col++) {
    let piv = col;
    for (let r = col + 1; r < n; r++) if (Math.abs(m[r][col]) > Math.abs(m[piv][col])) piv = r;
    [m[col], m[piv]] = [m[piv], m[col]];
    if (Math.abs(m[col][col]) < 1e-300) return Array(n).fill(Number.NaN);
    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const f = m[r][col] / m[col][col];
      for (let k = col; k <= n; k++) m[r][k] -= f * m[col][k];
    }
  }
  return m.map((row, i) => row[n] / m[i][i]);
}

export function ConditioningLab() {
  const [spacing, setSpacing] = useState<number>(2.0);
  const [logLambda, setLogLambda] = useState<number>(-5);
  const [noisePct, setNoisePct] = useState<number>(1);

  const L = useMemo(() => buildLeadfield(spacing), [spacing]);
  const singulars = useMemo(
    () => symmetricEigenvalues(transposeTimes(L)).map((e) => Math.sqrt(Math.max(e, 0))),
    [L],
  );
  const kappa = singulars[singulars.length - 1] > 0 ? singulars[0] / singulars[singulars.length - 1] : Infinity;

  // The forward problem is exact; only the measurement carries noise.
  const vNoisy = useMemo(() => {
    const clean = L.map((row) => row.reduce((acc, l, j) => acc + l * TRUE_SOURCES[j], 0));
    const scale = Math.max(...clean.map(Math.abs)) * (noisePct / 100);
    return clean.map((v, i) => v + NOISE_UNIT[i] * scale);
  }, [L, noisePct]);

  const lambda = Math.pow(10, logLambda);
  const solve = useMemo(() => {
    const LtL = transposeTimes(L);
    const LtV = L[0].map((_, j) => L.reduce((acc, row, i) => acc + row[j] * vNoisy[i], 0));
    const reg = (lam: number) => LtL.map((row, i) => row.map((v, j) => (i === j ? v + lam : v)));
    // A tiny floor stands in for the pseudo-inverse: exact OLS on a rank-deficient
    // normal matrix is what Section 4 of the notebook shows does not raise.
    return {
      ols: solveLinear(reg(1e-18), LtV),
      ridge: solveLinear(reg(lambda), LtV),
    };
  }, [L, vNoisy, lambda]);

  const relErr = (est: number[]) => {
    const num = Math.sqrt(est.reduce((a, v, i) => a + (v - TRUE_SOURCES[i]) ** 2, 0));
    const den = Math.sqrt(TRUE_SOURCES.reduce((a, v) => a + v * v, 0));
    return (num / den) * 100;
  };
  const errOls = relErr(solve.ols);
  const errRidge = relErr(solve.ridge);
  const illConditioned = kappa > 1e3;

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-stone-200 bg-stone-900 p-6 text-white shadow-sm">
        <div className="inline-flex items-center gap-2 rounded-md border border-cyan-800/60 bg-cyan-950 px-2.5 py-1 text-xs font-medium text-cyan-400">
          Foundations · Applied Linear Algebra for Neural Arrays
        </div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">
          Matrix Inverses, Conditioning, and Multicollinearity
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-stone-300">
          Moving contacts closer together makes neighbouring columns of the leadfield nearly
          identical. The forward problem stays easy. The inverse problem stops being answerable.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <a
            href="/notebooks/03_matrix_inverses_conditioning_student.ipynb"
            download="03_matrix_inverses_conditioning_student.ipynb"
            className="inline-block rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-stone-950 shadow-sm transition-colors hover:bg-cyan-400"
          >
            Download Workbook (.ipynb)
          </a>
          <a
            href="/notebooks/03_matrix_inverses_conditioning_solutions.ipynb"
            download="03_matrix_inverses_conditioning_solutions.ipynb"
            className="inline-block rounded-lg border border-stone-600 px-4 py-2 text-sm font-semibold text-stone-200 transition-colors hover:bg-stone-800"
          >
            Solutions
          </a>
        </div>
      </div>

      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-stone-900">1. Contact spacing sets the condition number</h2>
        <p className="text-xs text-stone-500">
          Four contacts at {ELECTRODE_Y} mm from three sources at −1, 0 and +1 mm.
        </p>

        <div className="mt-4">
          <div className="flex justify-between text-xs font-medium text-stone-700">
            <span>Contact spacing: {spacing.toFixed(2)} mm</span>
            <span className="text-stone-600">directional DBS segments sit near 0.5 mm</span>
          </div>
          <input
            type="range"
            aria-label="Contact spacing in millimetres"
            min={0.1}
            max={3}
            step={0.05}
            value={spacing}
            onChange={(e) => setSpacing(Number(e.target.value))}
            className="mt-1 w-full accent-cyan-600"
          />
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
            <div className="text-[11px] font-medium uppercase tracking-wider text-stone-500">
              Singular values of L
            </div>
            <div className="mt-2 flex items-end gap-3" style={{ height: 70 }}>
              {singulars.map((s, i) => (
                <div key={i} className="flex flex-1 flex-col items-center justify-end">
                  <span className="text-[9px] text-stone-500">{s.toExponential(1)}</span>
                  <div
                    className="w-full rounded-sm bg-cyan-600"
                    style={{ height: `${Math.max(2, (s / singulars[0]) * 48)}px` }}
                  />
                  <span className="mt-1 text-[9px] text-stone-500">σ{i + 1}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="flex flex-col justify-center rounded-lg border border-stone-200 bg-stone-50 p-3 text-center">
            <span className="text-[11px] uppercase tracking-wider text-stone-500">
              Condition number κ(L)
            </span>
            <p className={`text-2xl font-bold ${illConditioned ? "text-rose-700" : "text-emerald-700"}`}>
              {kappa > 1e6 ? kappa.toExponential(1) : kappa.toFixed(0)}
            </p>
            <span className="text-[11px] text-stone-500">
              {illConditioned ? "ill-conditioned (κ > 10³)" : "well conditioned"}
            </span>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-stone-900">
          2. What that does to a source estimate
        </h2>
        <p className="text-xs text-stone-500">
          The forward problem is untouched by conditioning. Only the inverse suffers.
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="text-xs font-medium text-stone-700">Measurement noise: {noisePct}%</div>
            <input
              type="range"
              aria-label="Measurement noise, percent"
              min={0.1}
              max={5}
              step={0.1}
              value={noisePct}
              onChange={(e) => setNoisePct(Number(e.target.value))}
              className="mt-1 w-full accent-rose-600"
            />
          </div>
          <div>
            <div className="text-xs font-medium text-stone-700">
              Tikhonov λ = {lambda.toExponential(1)}
            </div>
            <input
              type="range"
              aria-label="Tikhonov regularisation lambda, log scale"
              min={-9}
              max={-1}
              step={0.25}
              value={logLambda}
              onChange={(e) => setLogLambda(Number(e.target.value))}
              className="mt-1 w-full accent-purple-600"
            />
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-stone-200 text-left text-stone-500">
                <th className="py-1.5 font-medium">Source</th>
                <th className="py-1.5 font-medium">True (nA)</th>
                <th className="py-1.5 font-medium">Unregularized</th>
                <th className="py-1.5 font-medium">Tikhonov</th>
              </tr>
            </thead>
            <tbody>
              {TRUE_SOURCES.map((v, i) => (
                <tr key={i} className="border-b border-stone-100">
                  <td className="py-1.5 font-mono text-stone-700">s{i + 1}</td>
                  <td className="py-1.5 font-mono text-stone-900">{v.toFixed(1)}</td>
                  <td className="py-1.5 font-mono text-rose-700">{solve.ols[i].toFixed(1)}</td>
                  <td className="py-1.5 font-mono text-cyan-700">{solve.ridge[i].toFixed(1)}</td>
                </tr>
              ))}
              <tr className="font-semibold">
                <td className="py-1.5 text-stone-700">relative error</td>
                <td className="py-1.5" />
                <td className="py-1.5 font-mono text-rose-700">{errOls.toFixed(1)}%</td>
                <td className="py-1.5 font-mono text-cyan-700">{errRidge.toFixed(1)}%</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="mt-3 rounded-lg border border-stone-200 bg-stone-50 p-3 text-xs leading-relaxed text-stone-600">
          <b>Regularization buys variance with bias, and the bill is not small.</b> Even at its best
          λ the Tikhonov estimate here does not recover the sources: it shrinks them toward zero,
          and the largest source is the one it under-reports most. That is not a tuning failure. At
          κ = {kappa > 1e6 ? kappa.toExponential(1) : kappa.toFixed(0)} the information separating
          these sources is not in the measurement, and no estimator can invent it. The honest report
          is the condition number alongside the estimate, not the estimate alone.
        </div>
      </div>
    </div>
  );
}

import { useMemo, useState } from "react";

type MontageType = "raw" | "vert_bipolar" | "horiz_bipolar" | "car" | "custom_bipolar";

interface ContactInfo {
  id: number;
  label: string;
  name: string;
  level: string;
  angle: string;
  yPos: number;
  xOffset: number;
  width: number;
}

const DBS_CONTACTS: ContactInfo[] = [
  { id: 0, label: "1", name: "Ring 1 (Ventral)", level: "Level 1", angle: "360° Ring", yPos: 320, xOffset: 0, width: 70 },
  { id: 1, label: "2A", name: "Segment 2A (Anterior)", level: "Level 2", angle: "0°", yPos: 240, xOffset: -24, width: 22 },
  { id: 2, label: "2B", name: "Segment 2B (Posterolateral)", level: "Level 2", angle: "120°", yPos: 240, xOffset: 0, width: 22 },
  { id: 3, label: "2C", name: "Segment 2C (Posteromedial)", level: "Level 2", angle: "240°", yPos: 240, xOffset: 24, width: 22 },
  { id: 4, label: "3A", name: "Segment 3A (Anterior)", level: "Level 3", angle: "0°", yPos: 160, xOffset: -24, width: 22 },
  { id: 5, label: "3B", name: "Segment 3B (Posterolateral)", level: "Level 3", angle: "120°", yPos: 160, xOffset: 0, width: 22 },
  { id: 6, label: "3C", name: "Segment 3C (Posteromedial)", level: "Level 3", angle: "240°", yPos: 160, xOffset: 24, width: 22 },
  { id: 7, label: "4", name: "Ring 4 (Dorsal)", level: "Level 4", angle: "360° Ring", yPos: 80, xOffset: 0, width: 70 },
];

export function MontageSimulator() {
  const [montageType, setMontageType] = useState<MontageType>("vert_bipolar");
  const [activeRow, setActiveRow] = useState<number>(0);
  const [customPos, setCustomPos] = useState<number>(1); // 2A
  const [customNeg, setCustomNeg] = useState<number>(0); // 1
  const [noiseAmp, setNoiseAmp] = useState<number>(75); // uV common mode line noise
  const [signalAmp, setSignalAmp] = useState<number>(30); // uV local STN beta
  const [noiseFreq, setNoiseFreq] = useState<number>(60); // Hz
  const [stnContact, setStnContact] = useState<number>(1); // 2A carries pathology
  const [viewTab, setViewTab] = useState<"math" | "biophysics" | "rank">("math");

  // Define montage matrix M based on selection
  const { matrix, rowLabels, colLabels, title, description } = useMemo(() => {
    const C = 8;
    const cols = ["1", "2A", "2B", "2C", "3A", "3B", "3C", "4"];

    if (montageType === "raw") {
      const M = Array.from({ length: C }, (_, r) =>
        Array.from({ length: C }, (_, c) => (r === c ? 1 : 0))
      );
      return {
        matrix: M,
        rowLabels: cols,
        colLabels: cols,
        title: "Monopolar Montage (Identity Matrix I₈)",
        description:
          "Raw hardware channels referenced against a distant ground/case electrode. High vulnerability to common-mode electrical noise.",
      };
    }

    if (montageType === "vert_bipolar") {
      const rows = [
        "2A - 1",
        "2B - 1",
        "2C - 1",
        "3A - 4",
        "3B - 4",
        "3C - 4",
        "4 - 1",
      ];
      const M = [
        [-1, 1, 0, 0, 0, 0, 0, 0],
        [-1, 0, 1, 0, 0, 0, 0, 0],
        [-1, 0, 0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 1, 0, 0, -1],
        [0, 0, 0, 0, 0, 1, 0, -1],
        [0, 0, 0, 0, 0, 0, 1, -1],
        [-1, 0, 0, 0, 0, 0, 0, 1],
      ];
      return {
        matrix: M,
        rowLabels: rows,
        colLabels: cols,
        title: "Directional DBS Vertical Bipolar Montage [7 × 8]",
        description:
          "Segments on levels 2 and 3 referenced against adjacent solid ring electrodes. Rejects common-mode baseline drift while preserving directional STN signal.",
      };
    }

    if (montageType === "horiz_bipolar") {
      const rows = [
        "2A - 2B",
        "2B - 2C",
        "2C - 2A",
        "3A - 3B",
        "3B - 3C",
        "3C - 3A",
      ];
      const M = [
        [0, 1, -1, 0, 0, 0, 0, 0],
        [0, 0, 1, -1, 0, 0, 0, 0],
        [0, -1, 0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 1, -1, 0, 0],
        [0, 0, 0, 0, 0, 1, -1, 0],
        [0, 0, 0, 0, -1, 0, 1, 0],
      ];
      return {
        matrix: M,
        rowLabels: rows,
        colLabels: cols,
        title: "Directional Horizontal Bipolar Montage [6 × 8]",
        description:
          "Steering derivations computed azimuthally around the lead circumference. Ideal for isolating lateralized current spread in the subthalamic nucleus.",
      };
    }

    if (montageType === "car") {
      const M = Array.from({ length: C }, (_, r) =>
        Array.from({ length: C }, (_, c) => (r === c ? 1 - 1 / C : -1 / C))
      );
      return {
        matrix: M,
        rowLabels: cols.map((l) => `${l} - CAR`),
        colLabels: cols,
        title: "Common Average Reference (CAR) [8 × 8]",
        description:
          "Orthogonal projection operator subtracting the instantaneous spatial ensemble mean across all contacts. Guaranteed rank-deficient (rank = C - 1).",
      };
    }

    const rowLabel = `${cols[customPos]} - ${cols[customNeg]}`;
    const row = Array.from({ length: C }, (_, c) => {
      if (c === customPos) return 1;
      if (c === customNeg) return -1;
      return 0;
    });
    return {
      matrix: [row],
      rowLabels: [rowLabel],
      colLabels: cols,
      title: `Custom Bipolar Pair: ${rowLabel} [1 × 8]`,
      description:
        "Student-selected differential pair. Directly measures potential gradient between two arbitrary contacts.",
    };
  }, [montageType, customPos, customNeg]);

  // Compute Matrix Properties
  const { matrixRank, isCommonModeRejecting, isIdempotent, isSymmetric } = useMemo(() => {
    const D = matrix.length;
    const C = matrix[0].length;

    const rowSums = matrix.map((row) => row.reduce((a, b) => a + b, 0));
    const cmr = rowSums.every((sum) => Math.abs(sum) < 1e-6);

    const matCopy = matrix.map((row) => [...row]);
    let rank = 0;
    const rows = D;
    const cols = C;
    let r = 0;
    for (let c = 0; c < cols && r < rows; c++) {
      let pivot = r;
      for (let i = r + 1; i < rows; i++) {
        if (Math.abs(matCopy[i][c]) > Math.abs(matCopy[pivot][c])) {
          pivot = i;
        }
      }
      if (Math.abs(matCopy[pivot][c]) > 1e-9) {
        [matCopy[r], matCopy[pivot]] = [matCopy[pivot], matCopy[r]];
        const div = matCopy[r][c];
        for (let j = c; j < cols; j++) matCopy[r][j] /= div;
        for (let i = 0; i < rows; i++) {
          if (i !== r) {
            const factor = matCopy[i][c];
            for (let j = c; j < cols; j++) matCopy[i][j] -= factor * matCopy[r][j];
          }
        }
        rank++;
        r++;
      }
    }

    let symm = false;
    let idem = false;
    if (D === C) {
      symm = true;
      for (let i = 0; i < D; i++) {
        for (let j = 0; j < C; j++) {
          if (Math.abs(matrix[i][j] - matrix[j][i]) > 1e-6) symm = false;
        }
      }

      idem = true;
      for (let i = 0; i < D; i++) {
        for (let j = 0; j < C; j++) {
          let sum = 0;
          for (let k = 0; k < C; k++) {
            sum += matrix[i][k] * matrix[k][j];
          }
          if (Math.abs(sum - matrix[i][j]) > 1e-6) idem = false;
        }
      }
    }

    return {
      matrixRank: rank,
      isCommonModeRejecting: cmr,
      isIdempotent: idem,
      isSymmetric: symm,
    };
  }, [matrix]);

  const fs = 600;
  const N = 240;
  const { rawTraces, outTraces } = useMemo(() => {
    const time = Array.from({ length: N }, (_, i) => i / fs);
    const C = 8;

    const cmNoise = time.map(
      (t) =>
        noiseAmp * Math.sin(2 * Math.PI * noiseFreq * t) +
        20 * Math.sin(2 * Math.PI * 1.5 * t)
    );

    const raw: number[][] = [];
    for (let c = 0; c < C; c++) {
      const contactDist = Math.abs(c - stnContact);
      const betaFalloff = Math.exp(-0.7 * contactDist * contactDist);

      const channelWave = time.map((t, idx) => {
        const betaSignal =
          signalAmp * betaFalloff * Math.sin(2 * Math.PI * 20 * t + c * 0.15);
        const microNoise = Math.sin(idx * (c + 1) * 31.7) * 2.5;
        return cmNoise[idx] + betaSignal + microNoise;
      });
      raw.push(channelWave);
    }

    const D = matrix.length;
    const out: number[][] = [];
    for (let d = 0; d < D; d++) {
      const row = matrix[d];
      const derivWave = time.map((_, idx) => {
        let sum = 0;
        for (let c = 0; c < C; c++) {
          sum += row[c] * raw[c][idx];
        }
        return sum;
      });
      out.push(derivWave);
    }

    return { rawTraces: raw, outTraces: out };
  }, [noiseAmp, noiseFreq, signalAmp, stnContact, matrix]);

  const safeActiveRow = Math.min(activeRow, matrix.length - 1);
  const activeRowWeights = matrix[safeActiveRow] || [];

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="rounded-xl border border-stone-200 bg-white p-6 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 rounded-md bg-cyan-50 px-2.5 py-1 text-xs font-semibold text-cyan-700">
              <span>Track 1 • Lesson LIN 2</span>
              <span>•</span>
              <span>Spatial Operators</span>
            </div>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-stone-900">
              Matrices as Spatial Operators: Montages & Rank Deficiency
            </h1>
            <p className="mt-1 text-sm text-stone-600">
              Transform multichannel neural potentials from raw hardware recordings to clean
              bipolar or common-average spaces using linear algebraic projection operators.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <a
              href="/notebooks/02_matrices_and_montages_student.ipynb"
              download
              className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-xs font-medium text-stone-700 shadow-xs hover:bg-stone-50"
            >
              <svg className="h-3.5 w-3.5 text-stone-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                role="img"
                aria-label="Diagram illustrating this module's measurement."
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Student Workbook (.ipynb)
            </a>
            <a
              href="/notebooks/02_matrices_and_montages_solutions.ipynb"
              download
              className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white shadow-xs hover:bg-cyan-700"
            >
              <svg className="h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                role="img"
                aria-label="Diagram illustrating this module's measurement."
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Verified Solutions (.ipynb)
            </a>
          </div>
        </div>

        {/* Montage Mode Selector Bar */}
        <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-stone-100 pt-4">
          <span className="text-xs font-semibold text-stone-500 uppercase tracking-wide mr-2">
            Montage Operator (M):
          </span>
          {[
            { id: "vert_bipolar", label: "Vertical Bipolar (1-3-3-1)", badge: "7 derivations" },
            { id: "horiz_bipolar", label: "Horizontal Bipolar (Steering)", badge: "6 derivations" },
            { id: "car", label: "Common Average (CAR)", badge: "Rank C - 1" },
            { id: "raw", label: "Raw Monopolar (Identity)", badge: "No CMR" },
            { id: "custom_bipolar", label: "Custom 2-Contact Bipolar", badge: "1 pair" },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => {
                setMontageType(item.id as MontageType);
                setActiveRow(0);
              }}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                montageType === item.id
                  ? "bg-stone-900 text-white shadow-xs"
                  : "bg-stone-100 text-stone-600 hover:bg-stone-200"
              }`}
            >
              {item.label}
              <span className="ml-1.5 opacity-60 text-[10px]">({item.badge})</span>
            </button>
          ))}
        </div>
      </div>

      {/* Main Interactive Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: DBS 1-3-3-1 Physical Lead Visualization (4 cols) */}
        <div className="lg:col-span-4 space-y-4">
          <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between pb-3 border-b border-stone-100">
              <h2 className="text-xs font-bold uppercase tracking-wider text-stone-700">
                Directional DBS Lead (1-3-3-1)
              </h2>
              <span className="text-[11px] font-medium text-stone-500">
                Active: <span className="font-semibold text-cyan-700">{rowLabels[safeActiveRow]}</span>
              </span>
            </div>

            <p className="mt-2 text-xs text-stone-500 leading-relaxed">
              Standard clinical directional geometry (Medtronic SenSight / Boston Sci Cartesia).
              Contacts active in the selected derivation are highlighted (+ in cyan, - in amber).
            </p>

            {/* SVG Lead Shaft Schematic */}
            <div className="relative mt-4 flex justify-center py-4 bg-stone-950 rounded-lg overflow-hidden">
              <svg width="240" height="380" viewBox="0 0 240 380" className="select-none">
                role="img"
                aria-label="Diagram illustrating this module's measurement."
                <defs>
                  <linearGradient id="leadShaft" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#44403c" />
                    <stop offset="50%" stopColor="#78716c" />
                    <stop offset="100%" stopColor="#292524" />
                  </linearGradient>
                  <linearGradient id="platinumRing" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#94a3b8" />
                    <stop offset="40%" stopColor="#f8fafc" />
                    <stop offset="70%" stopColor="#cbd5e1" />
                    <stop offset="100%" stopColor="#64748b" />
                  </linearGradient>
                  <linearGradient id="posGlow" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#06b6d4" />
                    <stop offset="50%" stopColor="#67e8f9" />
                    <stop offset="100%" stopColor="#0891b2" />
                  </linearGradient>
                  <linearGradient id="negGlow" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#f59e0b" />
                    <stop offset="50%" stopColor="#fde68a" />
                    <stop offset="100%" stopColor="#d97706" />
                  </linearGradient>
                </defs>

                <rect x="85" y="30" width="70" height="340" rx="4" fill="url(#leadShaft)" />

                <text x="25" y="50" fill="#78716c" fontSize="10" fontWeight="600" textAnchor="middle">
                  DORSAL
                </text>
                <text x="25" y="360" fill="#78716c" fontSize="10" fontWeight="600" textAnchor="middle">
                  VENTRAL
                </text>

                {DBS_CONTACTS.map((contact) => {
                  const weight = activeRowWeights[contact.id] || 0;
                  const isPos = weight > 0;
                  const isNeg = weight < 0;
                  const isSTNSource = contact.id === stnContact;

                  let fill = "url(#platinumRing)";
                  let stroke = "#475569";
                  let strokeWidth = 1;

                  if (isPos) {
                    fill = "url(#posGlow)";
                    stroke = "#22d3ee";
                    strokeWidth = 2;
                  } else if (isNeg) {
                    fill = "url(#negGlow)";
                    stroke = "#f59e0b";
                    strokeWidth = 2;
                  }

                  const xPos = 120 + contact.xOffset - contact.width / 2;

                  return (
                    <g
                      key={contact.id}
                      tabIndex={0}
                      role="button"
                      aria-label={`Select contact ${contact.id}`}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          (e.currentTarget as unknown as SVGGElement).dispatchEvent(
                            new MouseEvent("click", { bubbles: true }),
                          );
                        }
                      }}
                      className="cursor-pointer transition-transform hover:scale-105"
                      onClick={() => {
                        if (montageType === "custom_bipolar") {
                          if (contact.id !== customPos) setCustomNeg(contact.id);
                        } else {
                          setStnContact(contact.id);
                        }
                      }}
                    >
                      <rect
                        x={xPos}
                        y={contact.yPos}
                        width={contact.width}
                        height="26"
                        rx="3"
                        fill={fill}
                        stroke={stroke}
                        strokeWidth={strokeWidth}
                      />
                      <text
                        x={xPos + contact.width / 2}
                        y={contact.yPos + 17}
                        fill={isPos || isNeg ? "#0f172a" : "#1e293b"}
                        fontSize="11"
                        fontWeight="bold"
                        textAnchor="middle"
                      >
                        {contact.label}
                      </text>

                      {weight !== 0 && (
                        <text
                          x={contact.xOffset >= 0 ? 175 : 65}
                          y={contact.yPos + 17}
                          fill={isPos ? "#67e8f9" : "#fde68a"}
                          fontSize="10"
                          fontWeight="bold"
                          textAnchor={contact.xOffset >= 0 ? "start" : "end"}
                        >
                          {weight > 0 ? `+${weight}` : `${weight}`}
                        </text>
                      )}

                      {isSTNSource && (
                        <circle
                          cx={xPos + contact.width / 2}
                          cy={contact.yPos + 32}
                          r="4"
                          fill="#10b981"
                          className="animate-pulse"
                        />
                      )}
                    </g>
                  );
                })}
              </svg>
            </div>

            <div className="mt-3 space-y-2 text-xs">
              <div className="flex items-center justify-between text-stone-600">
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 inline-block" />
                  Local STN Beta Burst Target:
                </span>
                <select
                  value={stnContact}
                  onChange={(e) => setStnContact(Number(e.target.value))}
                  className="rounded border border-stone-300 bg-white px-2 py-0.5 text-xs font-semibold text-stone-800"
                >
                  {DBS_CONTACTS.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label} ({c.name})
                    </option>
                  ))}
                </select>
              </div>

              {montageType === "custom_bipolar" && (
                <div className="pt-2 border-t border-stone-100 flex items-center justify-between">
                  <span className="text-stone-600 font-medium">Bipolar Pair (+ / -):</span>
                  <div className="flex gap-1.5">
                    <select
                      value={customPos}
                      onChange={(e) => setCustomPos(Number(e.target.value))}
                      className="rounded border border-cyan-300 bg-cyan-50 px-2 py-0.5 text-xs font-bold text-cyan-800"
                    >
                      {DBS_CONTACTS.map((c) => (
                        <option key={c.id} value={c.id}>
                          + {c.label}
                        </option>
                      ))}
                    </select>
                    <span className="text-stone-600 font-bold self-center">−</span>
                    <select
                      value={customNeg}
                      onChange={(e) => setCustomNeg(Number(e.target.value))}
                      className="rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-bold text-amber-800"
                    >
                      {DBS_CONTACTS.map((c) => (
                        <option key={c.id} value={c.id}>
                          − {c.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-xs space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-stone-700">
              Biophysical Signal Simulator
            </h4>

            <div>
              <div className="flex justify-between text-xs text-stone-600 mb-1">
                <span>Common-Mode Line Noise:</span>
                <span className="font-semibold text-stone-900">{noiseAmp} μV</span>
              </div>
              <input
                type="range"
                aria-label="Common-mode line noise amplitude in microvolts"
                min="0"
                max="150"
                value={noiseAmp}
                onChange={(e) => setNoiseAmp(Number(e.target.value))}
                className="w-full accent-amber-500"
              />
            </div>

            <div>
              <div className="flex justify-between text-xs text-stone-600 mb-1">
                <span>Local STN Beta Oscillation:</span>
                <span className="font-semibold text-stone-900">{signalAmp} μV</span>
              </div>
              <input
                type="range"
                aria-label="Local STN beta oscillation amplitude in microvolts"
                min="5"
                max="80"
                value={signalAmp}
                onChange={(e) => setSignalAmp(Number(e.target.value))}
                className="w-full accent-cyan-600"
              />
            </div>

            <div className="flex justify-between items-center text-xs pt-1">
              <span className="text-stone-600">Line Frequency:</span>
              <div className="flex gap-1.5">
                {[60, 50].map((f) => (
                  <button
                    key={f}
                    onClick={() => setNoiseFreq(f)}
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      noiseFreq === f
                        ? "bg-stone-800 text-white"
                        : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                    }`}
                  >
                    {f} Hz
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Matrix Math & Real-Time Oscilloscope Traces (8 cols) */}
        <div className="lg:col-span-8 space-y-4">
          <div className="flex gap-2 border-b border-stone-200 pb-2">
            {[
              { id: "math", label: "Matrix Equation & Inspector (M)" },
              { id: "biophysics", label: "Oscilloscope: Raw vs Montaged" },
              { id: "rank", label: "Rank Deficiency Guardrail (CAR)" },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setViewTab(tab.id as typeof viewTab)}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                  viewTab === tab.id
                    ? "bg-stone-900 text-white shadow-xs"
                    : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {viewTab === "math" && (
            <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs space-y-5">
              <div>
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-stone-900">{title}</h2>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="font-mono bg-stone-100 px-2 py-0.5 rounded text-stone-700">
                      Dim: [{matrix.length} × {matrix[0].length}]
                    </span>
                    <span className={`font-mono px-2 py-0.5 rounded font-semibold ${
                      matrixRank < matrix[0].length ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"
                    }`}>
                      Rank: {matrixRank}
                    </span>
                  </div>
                </div>
                <p className="mt-1 text-xs text-stone-600">{description}</p>
              </div>

              <div className="bg-stone-900 text-stone-100 p-4 rounded-lg font-mono text-xs overflow-x-auto">
                <div className="flex items-center gap-3">
                  <div className="text-cyan-400 font-bold">V_montage</div>
                  <div className="text-stone-400">=</div>
                  <div className="text-amber-300 font-bold">M</div>
                  <div className="text-stone-400">·</div>
                  <div className="text-emerald-400 font-bold">V_monopolar</div>
                </div>
                <div className="mt-2 text-[11px] text-stone-600 font-sans">
                  Output derivation <span className="text-cyan-300 font-mono font-bold">[{rowLabels[safeActiveRow]}]</span> is the linear combination:
                  <span className="text-stone-200 font-mono font-semibold ml-1">
                    v_{safeActiveRow} = ∑ (M[{safeActiveRow}, c] · V_raw[c])
                  </span>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-stone-500">
                  <span>Click a row to inspect its spatial derivation:</span>
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1">
                      <span className="h-2.5 w-2.5 rounded bg-cyan-500 inline-block" /> +1 (Positive)
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="h-2.5 w-2.5 rounded bg-amber-500 inline-block" /> -1 (Negative)
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="h-2.5 w-2.5 rounded bg-stone-100 border border-stone-300 inline-block" /> 0 (Inactive)
                    </span>
                  </div>
                </div>

                <div className="overflow-x-auto border border-stone-200 rounded-lg">
                  <table className="min-w-full text-center font-mono text-xs">
                    <thead>
                      <tr className="bg-stone-50 border-b border-stone-200 text-stone-600">
                        <th className="px-3 py-2 text-left font-sans text-[11px] font-semibold text-stone-500">
                          Derivation
                        </th>
                        {colLabels.map((c) => (
                          <th key={c} className="px-2.5 py-2 font-semibold text-stone-700">
                            {c}
                          </th>
                        ))}
                        <th className="px-2.5 py-2 font-sans text-[11px] font-semibold text-stone-500">
                          ∑ Row
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {matrix.map((row, rIdx) => {
                        const isSelected = rIdx === safeActiveRow;
                        const rowSum = row.reduce((a, b) => a + b, 0);

                        return (
                          <tr
                            key={rIdx}
                            tabIndex={0}
                            aria-label={`Select derivation row ${rIdx + 1}`}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                setActiveRow(rIdx);
                              }
                            }}
                            onClick={() => setActiveRow(rIdx)}
                            className={`cursor-pointer transition-colors border-b border-stone-100 ${
                              isSelected
                                ? "bg-cyan-50 font-bold text-cyan-900"
                                : "hover:bg-stone-50 text-stone-700"
                            }`}
                          >
                            <td className="px-3 py-2 text-left font-sans font-semibold text-xs text-stone-800">
                              {rowLabels[rIdx]}
                            </td>
                            {row.map((val, cIdx) => {
                              let cellBg = "bg-white text-stone-600";
                              if (val > 0.001) cellBg = "bg-cyan-100 text-cyan-800 font-bold";
                              else if (val < -0.001) cellBg = "bg-amber-100 text-amber-800 font-bold";

                              return (
                                <td key={cIdx} className={`px-2.5 py-1.5 ${cellBg}`}>
                                  {val > 0 ? `+${val.toFixed(val === 1 ? 0 : 2)}` : val.toFixed(val === 0 || val === -1 ? 0 : 2)}
                                </td>
                              );
                            })}
                            <td className={`px-2.5 py-1.5 text-xs font-semibold ${
                              Math.abs(rowSum) < 1e-6 ? "text-emerald-700" : "text-amber-700"
                            }`}>
                              {Math.abs(rowSum) < 1e-6 ? "0.0 (CMR ✓)" : rowSum.toFixed(1)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                <div className="p-3 rounded-lg border border-stone-200 bg-stone-50">
                  <div className="text-[10px] uppercase font-bold text-stone-500">Common-Mode Rejection</div>
                  <div className={`mt-1 text-sm font-bold ${isCommonModeRejecting ? "text-emerald-700" : "text-amber-700"}`}>
                    {isCommonModeRejecting ? "Active (∑ = 0)" : "None (∑ ≠ 0)"}
                  </div>
                  <div className="text-[10px] text-stone-500 mt-0.5">Rejects reference noise</div>
                </div>

                <div className="p-3 rounded-lg border border-stone-200 bg-stone-50">
                  <div className="text-[10px] uppercase font-bold text-stone-500">Subspace Rank</div>
                  <div className="mt-1 text-sm font-bold text-stone-900">
                    {matrixRank} of {matrix[0].length}
                  </div>
                  <div className="text-[10px] text-stone-500 mt-0.5">
                    {matrixRank < matrix[0].length ? "Rank deficient" : "Full rank"}
                  </div>
                </div>

                <div className="p-3 rounded-lg border border-stone-200 bg-stone-50">
                  <div className="text-[10px] uppercase font-bold text-stone-500">Orthogonal Projection</div>
                  <div className={`mt-1 text-sm font-bold ${isIdempotent ? "text-cyan-700" : "text-stone-600"}`}>
                    {isIdempotent ? "Yes (M² = M)" : "No"}
                  </div>
                  <div className="text-[10px] text-stone-500 mt-0.5">Idempotence test</div>
                </div>

                <div className="p-3 rounded-lg border border-stone-200 bg-stone-50">
                  <div className="text-[10px] uppercase font-bold text-stone-500">Operator Symmetry</div>
                  <div className={`mt-1 text-sm font-bold ${isSymmetric ? "text-cyan-700" : "text-stone-600"}`}>
                    {isSymmetric ? "Yes (Mᵀ = M)" : "No"}
                  </div>
                  <div className="text-[10px] text-stone-500 mt-0.5">Hermitian / Self-adjoint</div>
                </div>
              </div>
            </div>
          )}

          {viewTab === "biophysics" && (
            <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-bold text-stone-900">Live Dual-Scope: Common-Mode Cancellation</h2>
                  <p className="text-xs text-stone-500">
                    Watch common-mode line noise (60 Hz + drift) cancel out in real-time, exposing the underlying 20 Hz STN Beta burst.
                  </p>
                </div>
                <div
                  className={`text-xs font-semibold px-2.5 py-1 rounded border ${
                    isCommonModeRejecting
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : "bg-amber-50 text-amber-800 border-amber-200"
                  }`}
                >
                  {isCommonModeRejecting
                    ? "CMR Attenuation: complete (\u2211 = 0)"
                    : "CMR Attenuation: 0 dB (\u2211 \u2260 0)"}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-lg border border-stone-800 bg-stone-950 p-4 text-stone-100">
                  <div className="flex items-center justify-between pb-2 border-b border-stone-800">
                    <span className="text-xs font-bold text-amber-400 uppercase tracking-wide">
                      Raw Monopolar (Channel {DBS_CONTACTS[stnContact].label})
                    </span>
                    <span className="text-[10px] font-mono text-stone-500">Noise: {noiseAmp} μV</span>
                  </div>

                  <div className="mt-3 relative h-44 flex items-center justify-center">
                    <svg className="w-full h-full" viewBox="0 0 240 160" preserveAspectRatio="none">
                      role="img"
                      aria-label="Diagram illustrating this module's measurement."
                      <line x1="0" y1="80" x2="240" y2="80" stroke="#334155" strokeDasharray="3 3" />
                      <path
                        d={rawTraces[stnContact]
                          .map((val, idx) => {
                            const x = (idx / (N - 1)) * 240;
                            const y = 80 - (val / 120) * 70;
                            return `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
                          })
                          .join(" ")}
                        fill="none"
                        stroke="#fbbf24"
                        strokeWidth="1.75"
                      />
                    </svg>
                  </div>

                  <div className="mt-2 text-[11px] text-stone-600">
                    ⚠️ <strong className="text-stone-300">Biomarker Obscured:</strong> The 20 Hz beta signal is completely buried inside the 60 Hz line artifact and drift.
                  </div>
                </div>

                <div className="rounded-lg border border-cyan-900 bg-stone-950 p-4 text-stone-100">
                  <div className="flex items-center justify-between pb-2 border-b border-stone-800">
                    <span className="text-xs font-bold text-cyan-400 uppercase tracking-wide">
                      Montage Derivation [{rowLabels[safeActiveRow]}]
                    </span>
                    <span className="text-[10px] font-mono text-cyan-500 font-semibold">Clean STN Beta</span>
                  </div>

                  <div className="mt-3 relative h-44 flex items-center justify-center">
                    <svg className="w-full h-full" viewBox="0 0 240 160" preserveAspectRatio="none">
                      role="img"
                      aria-label="Diagram illustrating this module's measurement."
                      <line x1="0" y1="80" x2="240" y2="80" stroke="#334155" strokeDasharray="3 3" />
                      <path
                        d={outTraces[safeActiveRow]
                          .map((val, idx) => {
                            const x = (idx / (N - 1)) * 240;
                            const y = 80 - (val / 120) * 70;
                            return `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
                          })
                          .join(" ")}
                        fill="none"
                        stroke="#22d3ee"
                        strokeWidth="2"
                      />
                    </svg>
                  </div>

                  <div className="mt-2 text-[11px] text-stone-600">
                    {isCommonModeRejecting ? (
                      <>
                        ✨ <strong className="text-cyan-300">Clean Biomarker:</strong> every row of
                        this montage sums to zero, so the shared reference term cancels exactly:{" "}
                        <span className="font-mono text-stone-300">(N_cm - N_cm = 0)</span>. What
                        remains is local STN beta.
                      </>
                    ) : (
                      <>
                        ⚠️ <strong className="text-amber-300">Nothing has been rejected.</strong>{" "}
                        This montage has rows summing to{" "}
                        <span className="font-mono text-stone-300">1</span>, not{" "}
                        <span className="font-mono text-stone-300">0</span>, so the common-mode term
                        survives untouched and this trace is identical to the one on the left.
                        Attenuation is 0 dB. Switch to a bipolar or CAR montage to see the
                        difference.
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-stone-100">
                <h4 className="text-xs font-bold text-stone-700 uppercase tracking-wide mb-2">
                  All Output Derivations (Spatial Sweep):
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {outTraces.map((trace, dIdx) => (
                    <button
                      key={dIdx}
                      onClick={() => setActiveRow(dIdx)}
                      className={`p-2 rounded-lg border text-left transition-all ${
                        dIdx === safeActiveRow
                          ? "border-cyan-500 bg-cyan-50 shadow-xs"
                          : "border-stone-200 bg-stone-50 hover:bg-stone-100"
                      }`}
                    >
                      <div className="text-[11px] font-bold text-stone-800">{rowLabels[dIdx]}</div>
                      <div className="mt-1 h-8">
                        <svg className="w-full h-full" viewBox="0 0 100 40" preserveAspectRatio="none">
                          role="img"
                          aria-label="Diagram illustrating this module's measurement."
                          <path
                            d={trace
                              .filter((_, i) => i % 3 === 0)
                              .map((val, idx, arr) => {
                                const x = (idx / (arr.length - 1)) * 100;
                                const y = 20 - (val / 120) * 18;
                                return `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
                              })
                              .join(" ")}
                            fill="none"
                            stroke={dIdx === safeActiveRow ? "#0891b2" : "#64748b"}
                            strokeWidth="1.2"
                          />
                        </svg>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {viewTab === "rank" && (
            <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs space-y-4">
              <div className="flex items-center gap-2 text-amber-700 font-bold text-sm">
                <svg className="h-5 w-5 text-amber-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  role="img"
                  aria-label="Diagram illustrating this module's measurement."
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                Scientific Guardrail: The Common Average Referencing Rank Trap
              </div>

              <div className="space-y-3 text-xs text-stone-700 leading-relaxed">
                <p>
                  When applying <strong>Common Average Referencing (CAR)</strong> to a neural array (such as an
                  ECoG grid with C=64 channels or a Neuropixels shank with C=384 channels), each
                  channel subtracts the mean across all channels:
                </p>

                <div className="bg-stone-50 border border-stone-200 rounded-lg p-3 font-mono text-[11px] text-stone-800">
                  M_CAR = I_C - (1/C) · 1 · 1ᵀ
                </div>

                <p>
                  Because the sum across all channels is constrained to equal exactly zero:
                </p>

                <div className="bg-stone-50 border border-stone-200 rounded-lg p-3 font-mono text-[11px] text-stone-800">
                  ∑ v_CAR[i, t] = 0  (for all time points t)
                </div>

                <p>
                  The channels are no longer linearly independent! Any one channel can be perfectly
                  reconstructed from the sum of the remaining C - 1 channels:
                </p>

                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-900 font-semibold">
                  rank(M_CAR) = C - 1  (e.g., 64 channels → rank 63; 8 channels → rank 7)
                </div>

                <h4 className="font-bold text-stone-900 pt-2">The Clinical Data Analysis Trap:</h4>
                <p>
                  If an automated script attempts to compute the <strong>inverse covariance matrix</strong> Σ⁻¹
                  (required for Mahalanobis distance, Linear Discriminant Analysis, Kalman filter state updates,
                  or LCMV beamformer source localization), it will crash or produce wildly distorted weights
                  because:
                </p>

                <div className="bg-stone-900 text-stone-100 rounded-lg p-3 font-mono text-[11px]">
                  det(Σ_CAR) = 0  ⟹  Σ_CAR⁻¹ is UNDEFINED (Division by zero / singular matrix)
                </div>

                <h4 className="font-bold text-stone-900 pt-1">The Rigorous Solution:</h4>
                <ul className="list-disc pl-5 space-y-1">
                  <li>
                    <strong>Subspace Reduction:</strong> Drop 1 redundant channel before fitting the inverted model.
                  </li>
                  <li>
                    <strong>Moore-Penrose Pseudoinverse:</strong> Use <code className="font-mono bg-stone-100 px-1 py-0.5 rounded text-stone-800">np.linalg.pinv(cov)</code> to invert only within the rank-(C-1) signal subspace.
                  </li>
                  <li>
                    <strong>Tikhonov Regularization:</strong> Add a ridge diagonal loading term <code className="font-mono bg-stone-100 px-1 py-0.5 rounded text-stone-800">cov + λ · I</code>.
                  </li>
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

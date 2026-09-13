import { useCallback, useMemo, useRef, useState } from "react";

interface Vector2D {
  x: number;
  y: number;
}

export function DotProductDuality() {
  // Vector A (cyan) and Vector B (violet) in 2D state space
  const [vecA, setVecA] = useState<Vector2D>({ x: 120, y: 140 });
  const [vecB, setVecB] = useState<Vector2D>({ x: 180, y: 20 });
  const [dragging, setDragging] = useState<"A" | "B" | null>(null);

  // Neural Waveform Demo States
  const [activeTab, setActiveTab] = useState<"lfp" | "gamma" | "dc">("lfp");
  const [templateFreq, setTemplateFreq] = useState<number>(20);
  const [templatePhase, setTemplatePhase] = useState<number>(0);
  const [dcOffset, setDcOffset] = useState<number>(0);
  const [isCentered, setIsCentered] = useState<boolean>(false);

  const svgRef = useRef<SVGSVGElement | null>(null);

  // Canvas coordinate constants
  const origin = { x: 220, y: 220 };

  // Geometry calculations
  const normA = useMemo(() => Math.hypot(vecA.x, vecA.y), [vecA]);
  const normB = useMemo(() => Math.hypot(vecB.x, vecB.y), [vecB]);
  const dotProduct = useMemo(() => vecA.x * vecB.x + vecA.y * vecB.y, [vecA, vecB]);

  // Cosine similarity and angle
  const cosTheta = useMemo(() => {
    if (normA === 0 || normB === 0) return NaN;
    const val = dotProduct / (normA * normB);
    return Math.max(-1, Math.min(1, val));
  }, [dotProduct, normA, normB]);

  // Independent trigonometric angle calculation (3B1B non-circular validation)
  const angleDeg = useMemo(() => {
    if (normA === 0 || normB === 0) return NaN;
    const thetaA = Math.atan2(vecA.y, vecA.x);
    const thetaB = Math.atan2(vecB.y, vecB.x);
    let diff = Math.abs(thetaA - thetaB);
    if (diff > Math.PI) diff = 2 * Math.PI - diff;
    return (diff * 180) / Math.PI;
  }, [normA, normB, vecA, vecB]);

  // Projection of A onto B: ( (A . B) / ||B||^2 ) * B
  const projAonB = useMemo(() => {
    if (normB === 0) return { x: 0, y: 0 };
    const scalar = dotProduct / (normB * normB);
    return { x: vecB.x * scalar, y: vecB.y * scalar };
  }, [dotProduct, normB, vecB]);

  // Mouse/Touch Drag Handlers
  const handlePointerDown = (which: "A" | "B") => (e: React.PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    setDragging(which);
  };

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging || !svgRef.current) return;
      const rect = svgRef.current.getBoundingClientRect();
      const rawX = e.clientX - rect.left - origin.x;
      const rawY = origin.y - (e.clientY - rect.top);

      const clampedX = Math.max(-190, Math.min(190, rawX));
      const clampedY = Math.max(-190, Math.min(190, rawY));

      if (dragging === "A") setVecA({ x: clampedX, y: clampedY });
      if (dragging === "B") setVecB({ x: clampedX, y: clampedY });
    },
    [dragging, origin.x, origin.y],
  );

  /** Arrow keys nudge a vector, so the drag handles are reachable without a pointer. */
  const handleKeyNudge =
    (which: "A" | "B") => (e: React.KeyboardEvent<SVGCircleElement>) => {
      const step = e.shiftKey ? 20 : 5;
      const delta: Record<string, [number, number]> = {
        ArrowLeft: [-step, 0],
        ArrowRight: [step, 0],
        ArrowUp: [0, step],
        ArrowDown: [0, -step],
      };
      const move = delta[e.key];
      if (!move) return;
      e.preventDefault();
      const clamp = (v: number) => Math.max(-190, Math.min(190, v));
      const apply = (v: Vector2D) => ({ x: clamp(v.x + move[0]), y: clamp(v.y + move[1]) });
      if (which === "A") setVecA(apply);
      else setVecB(apply);
    };

  const handlePointerUp = () => {
    setDragging(null);
  };

  // Presets
  const setPreset = (preset: "ortho" | "parallel" | "opposite" | "unit") => {
    if (preset === "ortho") {
      setVecA({ x: 0, y: 150 });
      setVecB({ x: 150, y: 0 });
    } else if (preset === "parallel") {
      setVecA({ x: 140, y: 80 });
      setVecB({ x: 140, y: 80 });
    } else if (preset === "opposite") {
      setVecA({ x: 130, y: 60 });
      setVecB({ x: -130, y: -60 });
    } else if (preset === "unit") {
      setVecA({ x: 100, y: 0 });
      setVecB({ x: 0, y: 100 });
    }
  };

  // --------------------------------------------------------------------------
  // Synthetic Electrophysiology Streams (fs = 600 Hz, Nyquist = 300 Hz)
  // Well above beta (20 Hz), high-gamma (80 Hz), and noise components.
  // --------------------------------------------------------------------------
  const nSamples = 300;
  const durationS = 0.5; // 500 ms window
  const timeArray = useMemo(
    () => Array.from({ length: nSamples }, (_, i) => (i / nSamples) * durationS),
    [],
  );

  // Channel 1: STN LFP (20 Hz beta burst + multi-component physiological noise)
  const stnLfp = useMemo(() => {
    return timeArray.map((t) => {
      const beta = 1.3 * Math.sin(2 * Math.PI * 20 * t);
      const theta = 0.4 * Math.sin(2 * Math.PI * 6 * t);
      const noise = 0.3 * Math.sin(2 * Math.PI * 67 * t) + 0.2 * Math.sin(2 * Math.PI * 13 * t);
      return beta + theta + noise;
    });
  }, [timeArray]);

  // Channel 2: Independent Cortical ECoG Trace (Uncorrelated with STN)
  const ecogTrace = useMemo(() => {
    return timeArray.map((t) => {
      const gamma = 1.2 * Math.sin(2 * Math.PI * 80 * t);
      const alpha = 0.5 * Math.cos(2 * Math.PI * 11 * t);
      const noise = 0.3 * Math.sin(2 * Math.PI * 43 * t);
      return gamma + alpha + noise;
    });
  }, [timeArray]);

  // Independent white-noise channel for the DC trap demonstration
  const independentCh2 = useMemo(() => {
    // Generate deterministic independent signal orthogonal to stnLfp
    return timeArray.map((t) => {
      return 1.1 * Math.cos(2 * Math.PI * 37 * t) + 0.5 * Math.sin(2 * Math.PI * 79 * t);
    });
  }, [timeArray]);

  // Template wave for LFP oscillation matching
  const templateWave = useMemo(() => {
    const phaseRad = (templatePhase * Math.PI) / 180;
    return timeArray.map((t) => Math.sin(2 * Math.PI * templateFreq * t + phaseRad));
  }, [timeArray, templateFreq, templatePhase]);

  // Active Signals for Display
  const { signalA, signalB, signalALabel, signalBLabel } = useMemo(() => {
    if (activeTab === "lfp") {
      return {
        signalA: stnLfp,
        signalB: templateWave,
        signalALabel: "STN LFP (20 Hz Beta Burst)",
        signalBLabel: `Template Wave (${templateFreq} Hz, ${templatePhase}°)`,
      };
    }
    if (activeTab === "gamma") {
      return {
        signalA: ecogTrace,
        signalB: templateWave,
        signalALabel: "ECoG Cortical Trace (80 Hz High-Gamma Burst)",
        signalBLabel: `Template Wave (${templateFreq} Hz, ${templatePhase}°)`,
      };
    }
    // DC Offset Trap Mode: Two independent neural channels sharing reference drift
    const offsetVal = isCentered ? 0 : dcOffset;
    const chA = stnLfp.map((v) => v + offsetVal);
    const chB = independentCh2.map((v) => v + offsetVal);
    return {
      signalA: chA,
      signalB: chB,
      signalALabel: `Channel 1: STN LFP ${offsetVal > 0 ? `(+${offsetVal.toFixed(1)} μV DC)` : ""}`,
      signalBLabel: `Channel 2: Independent Cortex ${offsetVal > 0 ? `(+${offsetVal.toFixed(1)} μV DC)` : ""}`,
    };
  }, [activeTab, stnLfp, templateWave, ecogTrace, independentCh2, templateFreq, templatePhase, dcOffset, isCentered]);

  // Waveform Inner Product Metrics
  const { waveCosineSim, rawDotProd } = useMemo(() => {
    let dot = 0;
    let norm1 = 0;
    let norm2 = 0;
    for (let i = 0; i < nSamples; i++) {
      const a = signalA[i];
      const b = signalB[i];
      dot += a * b;
      norm1 += a * a;
      norm2 += b * b;
    }
    if (norm1 === 0 || norm2 === 0) return { waveCosineSim: 0, rawDotProd: 0 };
    return {
      waveCosineSim: dot / (Math.sqrt(norm1) * Math.sqrt(norm2)),
      rawDotProd: dot,
    };
  }, [signalA, signalB]);

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="rounded-xl border border-stone-200 bg-gradient-to-r from-stone-900 via-stone-850 to-stone-900 p-6 text-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 rounded-md bg-cyan-950 px-2.5 py-1 text-xs font-medium text-cyan-400 border border-cyan-800/60">
              Foundations · Applied Linear Algebra for Neural Arrays
            </div>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-white">
              The Dot Product as a Universal Neural Similarity Detector
            </h1>
            <p className="mt-1 text-sm text-stone-300 max-w-2xl">
              Understand the 3Blue1Brown projection duality: how dropping a perpendicular in
              multi-dimensional space forms the exact mathematical foundation of signal filtering,
              oscillation detection, and spike template matching.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              href="/notebooks/01_vectors_and_dot_products_student.ipynb"
              download="01_vectors_and_dot_products_student.ipynb"
              className="rounded-lg bg-cyan-500 px-3.5 py-2 text-xs font-semibold text-stone-950 hover:bg-cyan-400 transition-colors shadow-sm inline-flex items-center gap-1.5"
            >
              Download Student Workbook (.ipynb)
            </a>
            <a
              href="/notebooks/01_vectors_and_dot_products_solutions.ipynb"
              download="01_vectors_and_dot_products_solutions.ipynb"
              className="rounded-lg border border-stone-700 bg-stone-800/80 px-3.5 py-2 text-xs font-semibold text-stone-200 hover:bg-stone-700 transition-colors inline-flex items-center gap-1.5"
            >
              Solutions Guide (.ipynb)
            </a>
          </div>
        </div>
      </div>

      {/* Main Interactive Grid */}
      <div className="grid gap-6 lg:grid-cols-12">
        {/* Left 7 Columns: 3B1B Geometric State Space */}
        <div className="lg:col-span-7 space-y-4">
          <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between border-b border-stone-100 pb-3">
              <div>
                <h2 className="text-sm font-semibold text-stone-900">
                  1. Geometric State Space: Projection Duality
                </h2>
                <p className="text-xs text-stone-500">
                  Drag the arrowheads of Vector a (Cyan) and Vector b (Violet).
                </p>
              </div>
              <div className="flex gap-1.5">
                <button
                  onClick={() => setPreset("ortho")}
                  className="rounded border border-stone-200 bg-stone-50 px-2 py-1 text-xs font-medium text-stone-700 hover:bg-stone-100"
                >
                  90° (Ortho)
                </button>
                <button
                  onClick={() => setPreset("parallel")}
                  className="rounded border border-stone-200 bg-stone-50 px-2 py-1 text-xs font-medium text-stone-700 hover:bg-stone-100"
                >
                  0° (Match)
                </button>
                <button
                  onClick={() => setPreset("opposite")}
                  className="rounded border border-stone-200 bg-stone-50 px-2 py-1 text-xs font-medium text-stone-700 hover:bg-stone-100"
                >
                  180° (Invert)
                </button>
              </div>
            </div>

            {/* Coordinate Canvas */}
            <div className="mt-4 flex justify-center">
              <svg
                role="img"
                aria-label="Two-dimensional state space with draggable vectors a and b, the line through b, and the projection of a onto it."
                ref={svgRef}
                width={440}
                height={440}
                className="select-none rounded-xl border border-stone-800 bg-stone-950 shadow-inner cursor-crosshair"
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
              >
                <defs>
                  {/* Cyan Arrowhead */}
                  <marker id="arrow-cyan" markerWidth={8} markerHeight={8} refX={6} refY={4} orient="auto">
                    <polygon points="0 0, 8 4, 0 8" fill="#06b6d4" />
                  </marker>
                  {/* Violet Arrowhead */}
                  <marker id="arrow-violet" markerWidth={8} markerHeight={8} refX={6} refY={4} orient="auto">
                    <polygon points="0 0, 8 4, 0 8" fill="#a855f7" />
                  </marker>
                  {/* Amber Arrowhead */}
                  <marker id="arrow-amber" markerWidth={8} markerHeight={8} refX={6} refY={4} orient="auto">
                    <polygon points="0 0, 8 4, 0 8" fill="#f59e0b" />
                  </marker>
                  {/* Emerald Arrowhead for Basis Vectors î and ĵ */}
                  <marker id="arrow-emerald" markerWidth={8} markerHeight={8} refX={6} refY={4} orient="auto">
                    <polygon points="0 0, 8 4, 0 8" fill="#10b981" />
                  </marker>
                  {/* Grid Pattern */}
                  <pattern id="grid" width={40} height={40} patternUnits="userSpaceOnUse">
                    <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#262626" strokeWidth={0.8} />
                  </pattern>
                </defs>

                {/* Grid Background */}
                <rect width={440} height={440} fill="url(#grid)" />

                {/* Coordinate Axes */}
                <line x1={0} y1={origin.y} x2={440} y2={origin.y} stroke="#404040" strokeWidth={1.5} />
                <line x1={origin.x} y1={0} x2={origin.x} y2={440} stroke="#404040" strokeWidth={1.5} />

                {/* Axis Labels */}
                <text x={415} y={origin.y - 8} fill="#a8a29e" fontSize={11} fontFamily="sans-serif">
                  e₁ (STN)
                </text>
                <text x={origin.x + 8} y={18} fill="#a8a29e" fontSize={11} fontFamily="sans-serif">
                  e₂ (GPi)
                </text>

                {/* Basis Vectors î and ĵ */}
                <line
                  x1={origin.x}
                  y1={origin.y}
                  x2={origin.x + 40}
                  y2={origin.y}
                  stroke="#10b981"
                  strokeWidth={2}
                  markerEnd="url(#arrow-emerald)"
                />
                <text x={origin.x + 44} y={origin.y + 14} fill="#10b981" fontSize={10} fontStyle="italic">
                  î
                </text>
                <line
                  x1={origin.x}
                  y1={origin.y}
                  x2={origin.x}
                  y2={origin.y - 40}
                  stroke="#10b981"
                  strokeWidth={2}
                  markerEnd="url(#arrow-emerald)"
                />
                <text x={origin.x - 14} y={origin.y - 44} fill="#10b981" fontSize={10} fontStyle="italic">
                  ĵ
                </text>

                {/* Span line of Vector B for projection visualization */}
                {normB > 0 && (
                  <line
                    x1={origin.x - (vecB.x / normB) * 300}
                    y1={origin.y + (vecB.y / normB) * 300}
                    x2={origin.x + (vecB.x / normB) * 300}
                    y2={origin.y - (vecB.y / normB) * 300}
                    stroke="#c084fc"
                    strokeWidth={1}
                    strokeDasharray="4 4"
                  />
                )}

                {/* Dashed Drop Perpendicular (Projection Line from A to Line B) */}
                <line
                  x1={origin.x + vecA.x}
                  y1={origin.y - vecA.y}
                  x2={origin.x + projAonB.x}
                  y2={origin.y - projAonB.y}
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  strokeDasharray="3 3"
                />

                {/* Projected Vector along B (Amber) */}
                <line
                  x1={origin.x}
                  y1={origin.y}
                  x2={origin.x + projAonB.x}
                  y2={origin.y - projAonB.y}
                  stroke="#f59e0b"
                  strokeWidth={3}
                  markerEnd="url(#arrow-amber)"
                />

                {/* Vector B (Violet) */}
                <line
                  x1={origin.x}
                  y1={origin.y}
                  x2={origin.x + vecB.x}
                  y2={origin.y - vecB.y}
                  stroke="#a855f7"
                  strokeWidth={3}
                  markerEnd="url(#arrow-violet)"
                />

                {/* Vector A (Cyan) */}
                <line
                  x1={origin.x}
                  y1={origin.y}
                  x2={origin.x + vecA.x}
                  y2={origin.y - vecA.y}
                  stroke="#06b6d4"
                  strokeWidth={3}
                  markerEnd="url(#arrow-cyan)"
                />

                {/* Drag Handles */}
                <circle
                  cx={origin.x + vecA.x}
                  cy={origin.y - vecA.y}
                  r={9}
                  fill="#06b6d4"
                  stroke="#ffffff"
                  strokeWidth={2}
                  className="cursor-grab active:cursor-grabbing hover:scale-125 transition-transform"
                  tabIndex={0}
                  role="slider"
                  aria-label={`Vector a, currently ${Math.round(vecA.x)} across and ${Math.round(vecA.y)} up. Use the arrow keys to move it.`}
                  aria-valuenow={Math.round(Math.hypot(vecA.x, vecA.y))}
                  onPointerDown={handlePointerDown("A")}
                  onKeyDown={handleKeyNudge("A")}
                />
                <circle
                  cx={origin.x + vecB.x}
                  cy={origin.y - vecB.y}
                  r={9}
                  fill="#a855f7"
                  stroke="#ffffff"
                  strokeWidth={2}
                  className="cursor-grab active:cursor-grabbing hover:scale-125 transition-transform"
                  tabIndex={0}
                  role="slider"
                  aria-label={`Vector b, currently ${Math.round(vecB.x)} across and ${Math.round(vecB.y)} up. Use the arrow keys to move it.`}
                  aria-valuenow={Math.round(Math.hypot(vecB.x, vecB.y))}
                  onPointerDown={handlePointerDown("B")}
                  onKeyDown={handleKeyNudge("B")}
                />

                {/* Labels */}
                <text x={origin.x + vecA.x + 12} y={origin.y - vecA.y} fill="#06b6d4" fontSize={13} fontWeight="bold">
                  a
                </text>
                <text x={origin.x + vecB.x + 12} y={origin.y - vecB.y} fill="#a855f7" fontSize={13} fontWeight="bold">
                  b
                </text>
                <text
                  x={origin.x + projAonB.x - 14}
                  y={origin.y - projAonB.y + 16}
                  fill="#f59e0b"
                  fontSize={11}
                  fontWeight="bold"
                >
                  proj_b(a)
                </text>
              </svg>
            </div>

            {/* Mathematical Readouts */}
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 text-center">
              <div className="rounded-lg bg-stone-50 p-2.5 border border-stone-200">
                <span className="text-[11px] font-medium text-stone-500 uppercase tracking-wider">
                  Angle (θ)
                </span>
                <p className="mt-0.5 text-base font-bold text-stone-900">
                  {Number.isNaN(angleDeg) ? "—" : `${angleDeg.toFixed(1)}°`}
                </p>
                <span className="text-[10px] text-stone-600">Trig: atan2</span>
              </div>

              <div className="rounded-lg bg-stone-50 p-2.5 border border-stone-200">
                <span className="text-[11px] font-medium text-stone-500 uppercase tracking-wider">
                  Cosine Similarity
                </span>
                <p
                  className={`mt-0.5 text-base font-bold ${
                    cosTheta > 0.3
                      ? "text-emerald-700"
                      : cosTheta < -0.3
                      ? "text-rose-700"
                      : "text-stone-600"
                  }`}
                >
                  {Number.isNaN(cosTheta) ? "Undefined" : cosTheta.toFixed(3)}
                </p>
                <span className="text-[10px] text-stone-600">cos(θ) ∈ [-1, +1]</span>
              </div>

              <div className="rounded-lg bg-stone-50 p-2.5 border border-stone-200">
                <span className="text-[11px] font-medium text-stone-500 uppercase tracking-wider">
                  Dot Product (a · b)
                </span>
                <p className="mt-0.5 text-base font-bold text-stone-900">
                  {dotProduct.toFixed(0)}
                </p>
                <span className="text-[10px] text-stone-600">Σ (aᵢ · bᵢ)</span>
              </div>

              <div className="rounded-lg bg-stone-50 p-2.5 border border-stone-200">
                <span className="text-[11px] font-medium text-stone-500 uppercase tracking-wider">
                  Projection Length
                </span>
                <p className="mt-0.5 text-base font-bold text-amber-700">
                  {Number.isNaN(cosTheta) ? "0.0" : (normA * cosTheta).toFixed(1)}
                </p>
                <span className="text-[10px] text-stone-600">||a|| · cos(θ)</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right 5 Columns: Neural Signal Analysis Bridge */}
        <div className="lg:col-span-5 space-y-4">
          <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
            <div className="border-b border-stone-100 pb-3">
              <h2 className="text-sm font-semibold text-stone-900">
                2. Neural Electrophysiology Signal Analysis
              </h2>
              <p className="text-xs text-stone-500">
                Sampling rate: 600 Hz (Nyquist = 300 Hz). See projection in action across modalities.
              </p>
            </div>

            {/* Modality Tabs */}
            <div className="mt-3 flex gap-1 rounded-lg bg-stone-100 p-1">
              <button
                onClick={() => {
                  setActiveTab("lfp");
                  setTemplateFreq(20);
                  setDcOffset(0);
                  setIsCentered(false);
                }}
                className={`flex-1 rounded-md py-1 text-xs font-medium transition-colors ${
                  activeTab === "lfp" ? "bg-white text-stone-900 shadow-xs" : "text-stone-600 hover:text-stone-900"
                }`}
              >
                STN Beta (DBS)
              </button>
              <button
                onClick={() => {
                  setActiveTab("gamma");
                  setTemplateFreq(80);
                  setDcOffset(0);
                  setIsCentered(false);
                }}
                className={`flex-1 rounded-md py-1 text-xs font-medium transition-colors ${
                  activeTab === "gamma" ? "bg-white text-stone-900 shadow-xs" : "text-stone-600 hover:text-stone-900"
                }`}
              >
                High-Gamma (ECoG)
              </button>
              <button
                onClick={() => {
                  setActiveTab("dc");
                  setDcOffset(2.0);
                  setIsCentered(false);
                }}
                className={`flex-1 rounded-md py-1 text-xs font-medium transition-colors ${
                  activeTab === "dc" ? "bg-white text-stone-900 shadow-xs" : "text-stone-600 hover:text-stone-900"
                }`}
              >
                The DC Drift Trap
              </button>
            </div>

            {/* Waveform Visualization SVG */}
            <div className="mt-4 rounded-lg border border-stone-800 bg-stone-950 p-3">
              <div className="flex items-center justify-between text-[11px] text-stone-400 mb-1">
                <span className="truncate pr-2">
                  <b>solid</b> {signalALabel} · <b>dashed</b> {signalBLabel}
                </span>
                <span className="font-mono text-cyan-400 whitespace-nowrap">
                  Sim: <b>{waveCosineSim.toFixed(3)}</b>
                </span>
              </div>
              <svg width="100%" height={140} viewBox="0 0 300 140" className="overflow-visible">
                role="img"
                aria-label="Raw neural signal against a template wave, with the shaded area showing their point-by-point product."
                <line x1={0} y1={70} x2={300} y2={70} stroke="#404040" strokeWidth={1} strokeDasharray="2 2" />

                {/* Signal A (Cyan) */}
                <path
                  d={
                    `M 0 ${70 - signalA[0] * 18} ` +
                    timeArray
                      .slice(1)
                      .map((_, i) => {
                        const x = ((i + 1) / (nSamples - 1)) * 300;
                        const y = 70 - signalA[i + 1] * 18;
                        return `L ${x} ${y}`;
                      })
                      .join(" ")
                  }
                  fill="none"
                  stroke="#06b6d4"
                  strokeWidth={1.8}
                />

                {/* Signal B (Violet) */}
                <path
                  d={
                    `M 0 ${70 - signalB[0] * 18} ` +
                    timeArray
                      .slice(1)
                      .map((_, i) => {
                        const x = ((i + 1) / (nSamples - 1)) * 300;
                        const y = 70 - signalB[i + 1] * 18;
                        return `L ${x} ${y}`;
                      })
                      .join(" ")
                  }
                  fill="none"
                  stroke="#a855f7"
                  strokeWidth={1.8}
                  // Always dashed: in the DC tab both traces are channels, and hue
                  // alone is not a distinguishing cue for every reader.
                  strokeDasharray="3 2"
                />
              </svg>
              <div className="mt-2 flex items-center justify-between text-[10px] text-stone-600 border-t border-stone-800/80 pt-1.5">
                <span>Raw Dot Product: {rawDotProd.toFixed(1)}</span>
                <span>Cosine Similarity: {waveCosineSim.toFixed(3)}</span>
              </div>
            </div>

            {/* Contextual Sliders & Interactive Controls */}
            <div className="mt-4 space-y-3">
              {activeTab !== "dc" ? (
                <>
                  <div>
                    <div className="flex justify-between text-xs font-medium text-stone-700">
                      <span>Template Frequency: {templateFreq} Hz</span>
                      <span className="text-stone-600">{activeTab === "lfp" ? "Target: 20 Hz (Beta)" : "Target: 80 Hz (High-Gamma)"}</span>
                    </div>
                    <input
                      type="range"
                      aria-label="Template frequency in hertz"
                      min={5}
                      max={activeTab === "lfp" ? 60 : 140}
                      step={1}
                      value={templateFreq}
                      onChange={(e) => setTemplateFreq(Number(e.target.value))}
                      className="mt-1 w-full accent-cyan-600"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between text-xs font-medium text-stone-700">
                      <span>Template Phase Shift: {templatePhase}°</span>
                      <span className="text-stone-600">0° = In Phase</span>
                    </div>
                    <input
                      type="range"
                      aria-label="Template phase shift in degrees"
                      min={0}
                      max={360}
                      step={10}
                      value={templatePhase}
                      onChange={(e) => setTemplatePhase(Number(e.target.value))}
                      className="mt-1 w-full accent-purple-600"
                    />
                  </div>
                </>
              ) : (
                <div className="rounded-lg bg-amber-50 p-3 border border-amber-200">
                  <div className="flex justify-between items-center text-xs font-semibold text-amber-900">
                    <span>Shared Reference DC Drift: +{dcOffset.toFixed(1)} μV</span>
                    <button
                      onClick={() => setIsCentered(!isCentered)}
                      className="rounded bg-amber-200 px-2 py-0.5 text-[11px] font-medium text-amber-950 hover:bg-amber-300"
                    >
                      {isCentered ? "Restore DC Offset" : "Mean-Center (Fix)"}
                    </button>
                  </div>
                  <input
                    type="range"
                    aria-label="Shared reference DC drift in microvolts"
                    min={0}
                    max={4}
                    step={0.2}
                    value={dcOffset}
                    onChange={(e) => {
                      setDcOffset(Number(e.target.value));
                      setIsCentered(false);
                    }}
                    className="mt-2 w-full accent-amber-600"
                  />
                  <div className="mt-2 text-[11px] text-amber-950 leading-relaxed">
                    {!isCentered ? (
                      <p>
                        <b>The Common-Mode Trap:</b> Both channels are biologically independent, but because they
                        share a drifting reference, their cosine similarity falsely jumps to{" "}
                        <b>{waveCosineSim.toFixed(3)}</b>! This is why <b>Guardrail G1 (Monopolar Common-Mode)</b> exists.
                      </p>
                    ) : (
                      <p className="text-emerald-800 font-medium">
                        <b>Corrected:</b> Mean-centering subtracted the shared DC drift, revealing the true independent
                        relationship: <b>{waveCosineSim.toFixed(3)}</b> (near zero).
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Deep-Dive Theory Cards */}
      <div className="rounded-xl border border-stone-200 bg-white p-6 shadow-xs space-y-4">
        <h3 className="text-base font-semibold text-stone-900">
          The Foundations of Neural State Space
        </h3>
        <div className="grid gap-4 sm:grid-cols-3 text-xs text-stone-600 leading-relaxed">
          <div className="rounded-lg bg-stone-50 p-4 border border-stone-200">
            <h4 className="font-semibold text-stone-900 mb-1">1. Why Physical Channels Are Not Orthogonal</h4>
            <p>
              In linear algebra, coordinate axes are orthogonal by definition. In the brain, physical electrodes
              are volume-conducted and share reference grounds. Re-referencing (bipolar, CAR) is mathematically
              a <i>change of basis</i> to diagonalize the covariance matrix.
            </p>
          </div>
          <div className="rounded-lg bg-stone-50 p-4 border border-stone-200">
            <h4 className="font-semibold text-stone-900 mb-1">2. Filtering as State-Space Projection</h4>
            <p>
              When you compute a Fourier transform or wavelets, you project the multi-dimensional recording onto
              orthogonal sinusoidal basis vectors. The dot product extracts the exact coordinate magnitude along
              that frequency axis.
            </p>
          </div>
          <div className="rounded-lg bg-stone-50 p-4 border border-stone-200">
            <h4 className="font-semibold text-stone-900 mb-1">3. Cosine Similarity vs Matched Filter</h4>
            <p>
              Cosine similarity is scale-invariant (measuring pure shape). For spike sorting (Kilosort),
              unnormalized projection (the matched filter) is used because amplitude carries signal-to-noise
              information that scale-invariant metrics discard.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

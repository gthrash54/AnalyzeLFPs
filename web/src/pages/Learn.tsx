import { useState, type KeyboardEvent } from "react";
import { DotProductDuality } from "./learn/DotProductDuality";
import { MontageSimulator } from "./learn/MontageSimulator";
import { SamplingLab } from "./learn/SamplingLab";
import { FilterLab } from "./learn/FilterLab";
import { PreprocessingLab } from "./learn/PreprocessingLab";
import { ZeroLagLab } from "./learn/ZeroLagLab";
import { ConditioningLab } from "./learn/ConditioningLab";
import { NotebookModule } from "./learn/NotebookModule";
import { NOTEBOOK_MODULES } from "./learn/registry";

/** APG tablist keyboard navigation: arrows move between tabs, Home and End jump.
 *
 * Native buttons already answer Tab and Enter, which is why this page was
 * operable without it. The ARIA tab pattern expects the whole tablist to be one
 * tab stop, with the arrow keys moving inside it, and a screen reader user who
 * knows the pattern will try the arrows first.
 */
function moveTabFocus(event: KeyboardEvent<HTMLDivElement>): void {
  const handled = ["ArrowRight", "ArrowLeft", "Home", "End"];
  if (!handled.includes(event.key)) return;

  const tabs = Array.from(
    event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]:not([disabled])'),
  );
  const current = tabs.indexOf(document.activeElement as HTMLButtonElement);
  if (current === -1) return;

  event.preventDefault();
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? tabs.length - 1
        : event.key === "ArrowRight"
          ? (current + 1) % tabs.length
          : (current - 1 + tabs.length) % tabs.length;

  tabs[next].focus();
  tabs[next].click();
}

const COURSES = [
  {
    id: "stochastic",
    group: "Foundations",
    short: "Probability",
    title: "Probability and Stochastic Processes for Neural Data",
    lessons: [
      { id: "STO 1", title: "STO 1: An Estimator Is a Random Variable", active: true },
      { id: "STO 2", title: "STO 2: Autocorrelation and the Effective Sample Size", active: true },
      { id: "STO 3", title: "STO 3: Random Walks, and Correlations That Are Not There", active: true },
      { id: "STO 4", title: "STO 4: Events Rather Than Samples", active: true },
    ],
  },
  {
    id: "linear_algebra",
    group: "Foundations",
    short: "Linear Algebra",
    title: "Applied Linear Algebra for Neural Arrays",
    lessons: [
      { id: "LIN 1", title: "LIN 1: Vector State Space and the Dot Product Duality", active: true },
      { id: "LIN 2", title: "LIN 2: Matrices as Spatial Operators (Montages and Rereferencing)", active: true },
      { id: "LIN 3", title: "LIN 3: Matrix Inverses, Conditioning, and Multicollinearity", active: true },
      { id: "LIN 4", title: "LIN 4: Covariance Matrices and Volume Conduction", active: true },
      { id: "LIN 5", title: "LIN 5: Eigendecomposition and Principal Component Analysis", active: true },
      { id: "LIN 6", title: "LIN 6: Generalized Eigendecomposition (GED Spatial Filters)", active: true },
    ],
  },
  {
    id: "signal_processing",
    group: "Foundations",
    short: "Signal Processing",
    title: "Signal Processing for Neural Time Series",
    lessons: [
      { id: "SIG 1", title: "SIG 1: Sampling, Nyquist, and Aliasing", active: true },
      { id: "SIG 2", title: "SIG 2: Filtering and Zero-Phase Distortion", active: true },
      { id: "SIG 3", title: "SIG 3: The Fourier Transform from the Ground Up", active: true },
      { id: "SIG 4", title: "SIG 4: Welch's Method and DPSS Multitaper Estimation", active: true },
      { id: "SIG 5", title: "SIG 5: Complex Morlet Wavelets and Time-Frequency Trade-offs", active: true },
      { id: "SIG 6", title: "SIG 6: The Hilbert Transform and Instantaneous Features", active: true },
    ],
  },
  {
    id: "recording_physics",
    group: "Acquisition",
    short: "Recording Physics",
    title: "Recording Physics and Electrode Geometry",
    lessons: [
      { id: "REC 1", title: "REC 1: Extracellular Biophysics and Volume Conduction", active: true },
      { id: "REC 2", title: "REC 2: Directional DBS Leads versus Ring Contacts", active: true },
      { id: "REC 3", title: "REC 3: ECoG Grids, Strips, and Stereo-EEG Shafts", active: true },
      { id: "REC 4", title: "REC 4: Neuropixels, 384 Active Channels and Spatial Drift", active: true },
      { id: "REC 5", title: "REC 5: What a Contact Label Means", active: true },
    ],
  },
  {
    id: "preprocessing",
    group: "Acquisition",
    short: "Preprocessing",
    title: "The Preprocessing Contract",
    lessons: [
      { id: "PRE 1", title: "PRE 1: The Preprocessing Contract (Capstone)", active: true },
    ],
  },
  {
    id: "spike_trains",
    group: "Analysis",
    short: "Spike Trains",
    title: "Spike Trains and Single-Unit Activity",
    lessons: [
      { id: "SPK 1", title: "SPK 1: Splitting LFP from Spikes, and What Bleeds Across", active: true },
      { id: "SPK 2", title: "SPK 2: Robust Spike Detection via Median Noise Floor Estimation", active: true },
      { id: "SPK 3", title: "SPK 3: Spike Sorting and Unit Quality Metrics", active: true },
      { id: "SPK 4", title: "SPK 4: Peri-Stimulus Time Histograms and Spike-Field Coherence", active: true },
    ],
  },
  {
    id: "population_dynamics",
    group: "Analysis",
    short: "Population Dynamics",
    title: "Population Dynamics and Latent Structure",
    lessons: [
      { id: "POP 1", title: "POP 1: Neural State Space and Low-Dimensional Manifolds", active: true },
      { id: "POP 2", title: "POP 2: Latent Factor Analysis and Demixing", active: true },
      { id: "POP 3", title: "POP 3: Recursive Online Decoding with Kalman Filters", active: true },
    ],
  },
  {
    id: "connectivity",
    group: "Analysis",
    short: "Connectivity",
    title: "Connectivity and Spectral Coupling",
    lessons: [
      { id: "CON 1", title: "CON 1: Phase-Locking Value and the Zero-Lag Volume Trap", active: true },
      { id: "CON 2", title: "CON 2: Weighted Phase Lag Index and Granger Causality", active: true },
      { id: "CON 3", title: "CON 3: Phase-Amplitude Coupling and Waveform Harmonics", active: true },
      { id: "CON 4", title: "CON 4: Aperiodic Decay versus Periodic Oscillations", active: true },
    ],
  },
  {
    id: "guardrails",
    group: "Scientific Integrity",
    short: "Guardrails",
    title: "Closed-Loop Neuromodulation and Scientific Guardrails",
    lessons: [
      { id: "GRL 1", title: "GRL 1: Stimulation Artifact Mitigation and Blanking", active: true },
      { id: "GRL 2", title: "GRL 2: Adaptive DBS Control Loops", active: true },
      { id: "GRL 3", title: "GRL 3: EMG Contamination in the Speech Band", active: true },
      { id: "GRL 4", title: "GRL 4: Non-Stationarity Larger Than the Effect", active: true },
      { id: "GRL 5", title: "GRL 5: The Thirteen Scientific Guardrails", active: true },
    ],
  },
  {
    id: "inference",
    group: "Scientific Integrity",
    short: "Inference",
    title: "Statistical Inference for Neural Recordings",
    lessons: [
      { id: "INF 1", title: "INF 1: The Shuffled Null and Which Hypothesis Each Shuffle Encodes", active: true },
      { id: "INF 2", title: "INF 2: Multiple Comparisons and the Cluster Permutation Test", active: true },
      { id: "INF 3", title: "INF 3: What a z Score Means, and the Twenty Ways to Compute One", active: true },
    ],
  },
  {
    id: "decoding",
    group: "Electives",
    short: "Decoding",
    title: "Machine Learning and Neural Decoding",
    lessons: [
      { id: "DEC 1", title: "DEC 1: Least Squares and Ridge, Built and Then Checked", active: true },
      { id: "DEC 2", title: "DEC 2: Cross-Validation on Data That Is Not Independent", active: true },
      { id: "DEC 3", title: "DEC 3: Backpropagation, and How to Know It Is Right", active: true },
      { id: "DEC 4", title: "DEC 4: Whether Any of This Beats a Straight Line", active: true },
      { id: "DEC 5", title: "DEC 5: A Decoder's Weights Are Not an Encoding Map", active: true },
    ],
  },
];

export function Learn() {
  const [selectedCourse, setSelectedCourse] = useState<string>(COURSES[0].id);
  const [selectedLesson, setSelectedLesson] = useState<string>(COURSES[0].lessons[0].id);

  const currentCourse = COURSES.find((t) => t.id === selectedCourse) || COURSES[0];

  // The group each course belongs to is part of what the curriculum means:
  // Electives is elective on purpose, and Scientific Integrity comes last
  // because its lessons draw on everything earlier. Show it rather than
  // describing it only in the README.
  const groups = COURSES.reduce<{ name: string; courses: typeof COURSES }[]>((acc, course) => {
    const last = acc[acc.length - 1];
    if (last && last.name === course.group) last.courses.push(course);
    else acc.push({ name: course.group, courses: [course] });
    return acc;
  }, []);

  return (
    <div className="space-y-6">
      {/* Courses, in their groups. One tablist, so the arrow keys still walk the
          whole set; the group labels are presentational and out of the tab order. */}
      <div
        role="tablist"
        aria-label="Courses"
        onKeyDown={moveTabFocus}
        className="flex gap-4 overflow-x-auto pb-1 border-b border-stone-200"
      >
        {groups.map((group) => (
          <div key={group.name} className="flex flex-col gap-1">
            <span
              aria-hidden="true"
              className="whitespace-nowrap px-1 text-[10px] font-semibold uppercase tracking-wider text-stone-400"
            >
              {group.name}
            </span>
            <div className="flex gap-2">
              {group.courses.map((course) => (
                <button
                  key={course.id}
                  id={`course-tab-${course.id}`}
                  role="tab"
                  aria-selected={selectedCourse === course.id}
                  aria-controls="lesson-panel"
                  tabIndex={selectedCourse === course.id ? 0 : -1}
                  // The group is announced here because the visible label is
                  // aria-hidden, so a screen reader still hears which part of
                  // the program a course belongs to.
                  title={`${group.name}: ${course.title}`}
                  aria-label={`${course.title}, ${group.name}`}
                  onClick={() => {
                    setSelectedCourse(course.id);
                    setSelectedLesson(course.lessons[0].id);
                  }}
                  className={`whitespace-nowrap px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                    selectedCourse === course.id
                      ? "bg-stone-900 text-white shadow-xs"
                      : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                  }`}
                >
                  {course.short}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Track Title & Module Selector */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-stone-50 p-3 rounded-lg border border-stone-200">
        <p className="text-xs font-semibold text-stone-800 uppercase tracking-wide">
          {currentCourse.title}
        </p>
        <div
          role="tablist"
          aria-label={currentCourse.title}
          onKeyDown={moveTabFocus}
          className="flex flex-wrap gap-1.5"
        >
          {currentCourse.lessons.map((lesson) => (
            <button
              key={lesson.id}
              id={`lesson-tab-${lesson.id}`}
              role="tab"
              aria-selected={selectedLesson === lesson.id}
              aria-controls="lesson-panel"
              tabIndex={selectedLesson === lesson.id ? 0 : -1}
              title={lesson.title}
              onClick={() => setSelectedLesson(lesson.id)}
              disabled={!lesson.active}
              className={`px-2.5 py-1 text-xs rounded-md font-medium transition-all ${
                selectedLesson === lesson.id
                  ? "bg-cyan-700 text-white shadow-xs"
                  : lesson.active
                  ? "bg-white text-stone-700 border border-stone-300 hover:bg-stone-100"
                  : "bg-stone-200 text-stone-600 cursor-not-allowed"
              }`}
            >
              {lesson.title.split(":")[0]}
            </button>
          ))}
        </div>
      </div>

      {/* Module Content */}
      <div
        id="lesson-panel"
        role="tabpanel"
        aria-labelledby={`lesson-tab-${selectedLesson}`}
        tabIndex={0}
        aria-live="polite"
      >
      {selectedLesson === "LIN 1" ? (
        <DotProductDuality />
      ) : selectedLesson === "LIN 2" ? (
        <MontageSimulator />
      ) : selectedLesson === "LIN 3" ? (
        <ConditioningLab />
      ) : selectedLesson === "SIG 1" ? (
        <SamplingLab />
      ) : selectedLesson === "SIG 2" ? (
        <FilterLab />
      ) : selectedLesson === "PRE 1" ? (
        <PreprocessingLab />
      ) : selectedLesson === "CON 1" ? (
        <ZeroLagLab />
      ) : NOTEBOOK_MODULES[selectedLesson] ? (
        <NotebookModule {...NOTEBOOK_MODULES[selectedLesson]} />
      ) : (
        <div className="rounded-xl border border-stone-200 bg-white p-12 text-center text-stone-500">
          <p className="text-sm font-medium">This module is currently in syllabus design.</p>
          <p className="mt-1 text-xs">Switch to LIN 1, LIN 2, LIN 3, SIG 1, SIG 2, or PRE 1 to explore the interactive simulators.</p>
        </div>
      )}
      </div>
    </div>
  );
}

import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Help } from "./components/Help";
import { PageHeader } from "./components/ui";
import { Ask } from "./pages/Ask";
import { Compare } from "./pages/Compare";
import { Learn } from "./pages/Learn";
import { Qc } from "./pages/Qc";
import { Result } from "./pages/Result";
import { Run } from "./pages/Run";
import { Runs } from "./pages/Runs";
import { Status } from "./pages/Status";
import { Subjects } from "./pages/Subjects";

// Grouped, because the order of these screens is the order of the work: ask a
// question, look at what you have, run it, read what came out. A flat list of
// seven gives a newcomer no clue which of them comes first.
const NAV = [
  {
    group: "Analyze",
    items: [
      { to: "/", label: "Ask", end: true },
      { to: "/subjects", label: "Subjects" },
      { to: "/run", label: "Run" },
    ],
  },
  {
    group: "Records",
    items: [
      { to: "/runs", label: "Runs" },
      { to: "/compare", label: "Compare" },
    ],
  },
  {
    group: "Reference",
    items: [
      { to: "/learn", label: "Curriculum" },
      { to: "/status", label: "Status" },
    ],
  },
];

const FLAT_NAV = NAV.flatMap((section) => section.items);

// One title per screen, here rather than inside each page, so a page cannot
// invent its own heading style and the nav label and the title cannot drift
// apart. Routes carrying an identifier show it as the subtitle.
function titleFor(pathname: string): { title: string; subtitle?: string } {
  if (pathname.startsWith("/qc/")) {
    return { title: "Quality control", subtitle: pathname.slice("/qc/".length) };
  }
  if (/^\/runs\/.+/.test(pathname)) {
    return { title: "Result", subtitle: pathname.slice("/runs/".length) };
  }
  // Longest path first: /runs starts with /run, and matching in declaration
  // order titled the run log "Run".
  const item = [...FLAT_NAV]
    .sort((a, b) => b.to.length - a.to.length)
    .find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)));
  return { title: item?.label ?? "dbsspeech" };
}

function ScreenHeader() {
  const { pathname } = useLocation();
  const { title, subtitle } = titleFor(pathname);
  return <PageHeader title={title} subtitle={subtitle} />;
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded-control px-2 py-1.5 text-body whitespace-nowrap transition-colors ${
    isActive
      ? "bg-accent-soft font-medium text-accent-ink"
      : "text-ink-muted hover:bg-surface-hover hover:text-ink"
  }`;

export default function App() {
  return (
    <div className="min-h-screen">
      {/* The app chrome. Named once at the top rather than inside the nav
          column, so the product name stays put when the nav moves under it on a
          narrow screen. */}
      <header className="sticky top-0 z-20 border-b border-line bg-surface shadow-hairline">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-2">
          <span className="text-heading font-semibold tracking-tight text-ink">dbsspeech</span>
          <span className="hidden text-micro text-ink-muted sm:inline">
            intraoperative DBS and ECoG analysis
          </span>
          <span className="ml-auto rounded-control bg-surface-sunken px-1.5 py-0.5 text-micro text-ink-muted ring-1 ring-line-subtle">
            local only
          </span>
        </div>
        {/* Under about 768px the sidebar becomes this row, which scrolls
            sideways rather than squeezing the content column to nothing. */}
        <nav aria-label="Sections" className="md:hidden">
          <ul className="flex gap-1 overflow-x-auto border-t border-line-subtle px-3 py-1.5">
            {FLAT_NAV.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end} className={linkClass}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <div className="mx-auto flex max-w-6xl gap-6 px-4 py-4">
        <nav aria-label="Sections" className="hidden w-40 shrink-0 md:block">
          <div className="sticky top-16 space-y-4">
            {NAV.map((section) => (
              <div key={section.group}>
                <p className="px-2 pb-1 text-micro font-semibold uppercase tracking-wider text-ink-muted">
                  {section.group}
                </p>
                <ul className="space-y-0.5">
                  {section.items.map((item) => (
                    <li key={item.to}>
                      <NavLink to={item.to} end={item.end} className={linkClass}>
                        {item.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </nav>
        <main className="min-w-0 flex-1 pb-10">
          <ScreenHeader />
          {/* Above the screen rather than inside each page, so the wording stays
              consistent and a new page cannot quietly ship without any. */}
          <Help />
          <Routes>
            <Route path="/" element={<Ask />} />
            <Route path="/learn" element={<Learn />} />
            <Route path="/subjects" element={<Subjects />} />
            <Route path="/qc/:studyId" element={<Qc />} />
            <Route path="/run" element={<Run />} />
            <Route path="/runs" element={<Runs />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/status" element={<Status />} />
            <Route path="/runs/:runId" element={<Result />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

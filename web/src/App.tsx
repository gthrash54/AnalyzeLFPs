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

const NAV = [
  { to: "/", label: "Ask", end: true },
  { to: "/learn", label: "Curriculum" },
  { to: "/subjects", label: "Subjects" },
  { to: "/run", label: "Run" },
  { to: "/runs", label: "Runs" },
  { to: "/compare", label: "Compare" },
  { to: "/status", label: "Status" },
];

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
  const item = NAV.find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)));
  return { title: item?.label ?? "dbsspeech" };
}

function ScreenHeader() {
  const { pathname } = useLocation();
  const { title, subtitle } = titleFor(pathname);
  return <PageHeader title={title} subtitle={subtitle} />;
}

export default function App() {
  return (
    <div className="mx-auto flex max-w-6xl gap-6 p-4">
      <nav className="w-36 shrink-0">
        <h1 className="mb-3 text-heading font-semibold text-ink">dbsspeech</h1>
        <ul className="space-y-1">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `block rounded px-2 py-1 text-body ${
                    isActive
                      ? "bg-accent-soft font-medium text-accent"
                      : "text-ink-muted hover:bg-surface-sunken hover:text-ink"
                  }`
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <main className="min-w-0 flex-1">
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
  );
}

// A dense table: sortable columns, sticky header, rules instead of zebra fill.
//
// Every table in this app is the same table. Before this, each page wrote its
// own <table> with its own header styling and its own idea of how a numeric
// column aligns, which is how two screens end up disagreeing about what a run
// id looks like.
//
// Sorting is client side and deliberately so: these tables are tens of rows,
// not thousands, and a server round trip to sort a list already on screen is a
// worse experience than no sorting at all.

import { useMemo, useState } from "react";
import type { ReactNode } from "react";

export interface Column<T> {
  /** Stable identifier, also the sort key. */
  key: string;
  header: string;
  /** What to draw. Defaults to the sort value. */
  render?: (row: T) => ReactNode;
  /** What to sort and align on. A column with no value is not sortable. */
  value?: (row: T) => string | number | null | undefined;
  /** Numbers right align. Everything else left aligns. */
  align?: "left" | "right";
  /** Identifiers and measured numbers are monospace and do not wrap. */
  mono?: boolean;
  className?: string;
}

type Direction = "asc" | "desc";

export function DataTable<T>({ columns, rows, rowKey, initialSort, caption }: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  initialSort?: { key: string; direction: Direction };
  caption?: string;
}) {
  const [sort, setSort] = useState<{ key: string; direction: Direction } | null>(
    initialSort ?? null,
  );

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.value) return rows;
    const factor = sort.direction === "asc" ? 1 : -1;
    // A copy: sorting the array the caller handed us would mutate its state.
    return [...rows].sort((a, b) => {
      const left = column.value!(a);
      const right = column.value!(b);
      // Missing values sort last in both directions. A blank cell floating to
      // the top of a descending sort looks like a result.
      if (left === null || left === undefined) return 1;
      if (right === null || right === undefined) return -1;
      if (typeof left === "number" && typeof right === "number") {
        return (left - right) * factor;
      }
      return String(left).localeCompare(String(right)) * factor;
    });
  }, [rows, sort, columns]);

  const toggle = (key: string) =>
    setSort((current) =>
      current?.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: "asc" },
    );

  return (
    // The table scrolls inside the panel rather than widening the page. The
    // negative margin puts the rules flush with the panel border, so a table is
    // the panel rather than a box inside one.
    <div className="-mx-3 -my-3 overflow-x-auto overscroll-x-contain">
      {/* A floor on the width: without it a narrow window squeezes the last
          column to a few characters and every row becomes eight lines tall.
          Below the floor the table scrolls sideways instead. */}
      <table className="w-full min-w-2xl border-collapse text-body">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="sticky top-0 z-10 bg-surface-sunken shadow-sticky">
          <tr>
            {columns.map((column) => {
              const active = sort?.key === column.key;
              const alignment = column.align === "right" ? "text-right" : "text-left";
              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={
                    active ? (sort!.direction === "asc" ? "ascending" : "descending") : "none"
                  }
                  className={`border-b border-line px-2 py-2 text-small font-medium
                    whitespace-nowrap text-ink-muted ${alignment}`}
                >
                  {column.value ? (
                    // A real button, so a keyboard reaches it.
                    <button
                      type="button"
                      onClick={() => toggle(column.key)}
                      className="group/sort inline-flex items-center gap-1 rounded-control
                        transition-colors hover:text-ink"
                    >
                      {column.header}
                      <span
                        aria-hidden="true"
                        className={
                          active
                            ? "text-accent"
                            : "text-ink-muted opacity-0 transition-opacity group-hover/sort:opacity-60"
                        }
                      >
                        {active && sort!.direction === "desc" ? "↓" : "↑"}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={rowKey(row)}
              // A hover tint rather than zebra fill: it marks the row a person
              // is actually reading across without tinting half the table.
              className="border-b border-line-subtle transition-colors last:border-0
                hover:bg-surface-hover"
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`px-2 py-2 align-top
                    ${column.align === "right" ? "text-right" : "text-left"}
                    ${column.mono ? "whitespace-nowrap font-mono text-micro tabular" : ""}
                    ${column.className ?? ""}`}
                >
                  {column.render ? column.render(row) : String(column.value?.(row) ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

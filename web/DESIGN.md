# Design

The direction is a well-made lab instrument, not a marketing site. Dense,
quiet, and consistent, so that the numbers are the loudest thing on the screen.

Three rules behind everything below.

**Density is a feature.** A scientist comparing eight contacts wants them in one
view. Generous whitespace is not hospitality here, it is scrolling.

**Color means something or it is not used.** There is one accent, and the status
colors are reserved for status. A blue button and a blue heading and a blue link
teach nothing; a red badge that only ever means "blocked" teaches a lot.

**Nothing decorative competes with data.** No shadows, no gradients, no
animation beyond a focus ring. A border is enough to separate two regions.

## Tokens

Defined once in `src/index.css` under Tailwind's `@theme`, so a change lands
everywhere. Use the token, never a raw palette value: `text-muted`, not
`text-stone-500`.

### Color roles

| token | value | used for |
|---|---|---|
| `canvas` | stone 50 | the page behind everything |
| `surface` | white | panels, table bodies |
| `surface-sunken` | stone 50 | table headers, help panels, code |
| `border` | stone 300 | panel and table borders |
| `border-subtle` | stone 200 | rules inside a panel, row separators |
| `text` | stone 900 | body text and numbers |
| `text-muted` | stone 500 | labels, hints, secondary columns |
| `accent` | teal 700 | links, the primary button, the active nav item |
| `ok` | emerald 700 | approved, run succeeded |
| `warn` | amber 700 | needs attention, overridden, dirty tree |
| `danger` | rose 700 | blocked, failed, refused |

Teal rather than blue for the accent because blue reads as a hyperlink from the
1990s and because the status colors need the cool end of the range left alone.

Every status color has a `-soft` background variant for badges. Text on a soft
background uses the 900 weight of the same hue, which clears 7:1 contrast.

### Type scale

Five sizes. If a sixth seems necessary, the layout is the problem.

| token | size / line height | used for |
|---|---|---|
| `text-display` | 18px / 24px | the page title, once per screen |
| `text-heading` | 14px / 20px, 600 | panel titles |
| `text-body` | 13px / 18px | everything ordinary |
| `text-small` | 12px / 16px | labels, hints, table headers |
| `text-micro` | 11px / 14px | captions, run ids, timestamps |

System UI stack for prose. `ui-monospace` for anything that is an identifier or
a number a person might copy: run ids, hashes, file paths, versions, measured
values in tables. Numbers in tables are tabular-figure aligned so columns of
digits line up.

### Spacing

A 4px base: `1` = 4px, `2` = 8px, `3` = 12px, `4` = 16px, `6` = 24px. Panels use
`3` inside and `3` between. Table cells use `2` vertically and `2` horizontally.
Nothing uses a value off this scale.

## Components

In `src/components/ui/`. A page composes these; a page does not write its own
padding, border, or color classes. If a page needs a one-off class, that is a
signal the component is missing something.

| component | what it is for |
|---|---|
| `PageHeader` | the title of a screen, an optional subtitle, and optional actions on the right |
| `Panel` | a titled region with an optional hint under the title |
| `DataTable` | a dense table: sortable columns, sticky header, zebra-free rows separated by rules |
| `Badge` | one word of status, in a status color |
| `Button` | primary, secondary, danger, in one size |
| `Field` | a labelled input with help text and an optional caveat |
| `EmptyState` | what to see when there is nothing, and what to do about it |
| `Skeleton` | the shape of content that has not arrived |

### Table conventions

Headers are `text-small`, muted, left aligned, and sticky. Numeric columns are
right aligned and monospace. Rows are separated by a `border-subtle` rule rather
than by alternating fill, which is quieter at high density. A sortable header
shows its direction with an arrow and is a real `<button>` so it is reachable by
keyboard.

Long identifiers such as run ids do not wrap; they are monospace and the cell
scrolls if it must. A table wider than its container scrolls horizontally inside
the panel rather than widening the page.

### Badge conventions

Fixed, so a color always means the same thing.

| value | tone |
|---|---|
| `approved`, `ok` | ok |
| `in_review`, `reopened`, `queued`, `running` | warn |
| `unreviewed` | muted |
| `blocked`, `failed` | danger |

Guardrail severity: `block` is danger, `warn` is warn, `note` is muted. A dirty
tree is warn, always, on every screen that shows a run.

## Accessibility

The floor, not the ambition.

- Every input has a real `<label>`, associated by nesting or `htmlFor`. No
  placeholder-as-label.
- Focus is visible everywhere: a 2px accent ring with a 2px offset, never
  `outline: none` without a replacement.
- Anything clickable is a `<button>` or an `<a>`. No click handlers on `<div>`.
- Body text and muted text both clear 4.5:1 on their backgrounds; badge text
  clears 7:1 on its soft background.
- Status is never carried by color alone. A badge always has a word in it.

## Dark mode

Not done. It would need a second value for every token and a check of the status
colors against a dark ground, and nobody has asked. The tokens are defined in one
place so that it stays cheap to add.

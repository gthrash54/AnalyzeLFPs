// Builds a parameter form from a recipe's JSON schema, and shows the
// explanation and caveat the server sent for each choice.
//
// Hand-rolled on purpose: string, number, boolean, enum and string-list is
// everything the recipes use, and a general JSON-schema form generator would be
// far more code for no benefit here.
//
// Two things it does beyond rendering inputs, both for someone who has not run
// this before. It shows only the parameters the recipe called essential, where
// the recipe said which those are. And it puts the agent's reason for a value
// next to the value, because "what this is" and "why it is set to that" are one
// thought, and the second without the first teaches nothing.

import type {
  OptionExplanation,
  ProposedParameter,
  Recipe,
  SchemaProperty,
} from "../api/types";
import { Field } from "./ui";
import { inputClass } from "./ui/tones";

type Values = Record<string, unknown>;

/** Enum values, whether declared directly or inside an anyOf. */
function enumValues(prop: SchemaProperty): string[] | null {
  if (prop.enum) return prop.enum;
  for (const branch of prop.anyOf ?? []) if (branch.enum) return branch.enum;
  return null;
}

function isList(prop: SchemaProperty): boolean {
  if (prop.type === "array") return true;
  return (prop.anyOf ?? []).some((b) => b.type === "array");
}

function isNumber(prop: SchemaProperty): boolean {
  if (prop.type === "number" || prop.type === "integer") return true;
  return (prop.anyOf ?? []).some((b) => b.type === "number" || b.type === "integer");
}

function isBoolean(prop: SchemaProperty): boolean {
  if (prop.type === "boolean") return true;
  return (prop.anyOf ?? []).some((b) => b.type === "boolean");
}

/** A parameter that may be left unset, meaning the recipe resolves it elsewhere. */
function isNullable(prop: SchemaProperty): boolean {
  return (prop.anyOf ?? []).some((b) => b.type === "null");
}

/** What to show when a field is empty: the schema's default, or that there is none. */
function placeholderFor(prop: SchemaProperty): string {
  if (prop.default === null || prop.default === undefined) return "default";
  return String(prop.default);
}

/** The label a person reads: the recipe's own, or the field name made readable. */
function labelFor(name: string, prop: SchemaProperty): string {
  return prop.title ?? name.replace(/_/g, " ");
}

/** The field's help, with the agent's reason for the current value appended. */
function helpFor(
  name: string,
  prop: SchemaProperty,
  reasons: Record<string, ProposedParameter> | undefined,
  override?: string,
): string | undefined {
  const base = override ?? prop.description;
  const reason = reasons?.[name];
  if (!reason) return base;
  const said =
    reason.confidence === "yours" ? "You set this." : `Chosen for you: ${reason.reason}.`;
  // A description written without a full stop runs straight into the sentence
  // after it: "comma separated; blank means all You set this."
  const stopped = /[.!?]$/.test(base?.trim() ?? "") ? base : base ? `${base}.` : base;
  return stopped ? `${stopped} ${said}` : said;
}

/** Explanations are keyed by parameter suffix: baseline_center -> centers. */
function explanationsFor(
  name: string,
  explanations: Record<string, OptionExplanation[]> | undefined,
): OptionExplanation[] | undefined {
  if (!explanations) return undefined;
  if (name.endsWith("_center")) return explanations.centers;
  if (name.endsWith("_scale")) return explanations.scales;
  return undefined;
}

export function SchemaForm({ recipe, values, onChange, group = "all", reasons }: {
  recipe: Recipe;
  values: Values;
  onChange: (values: Values) => void;
  /** Which half to show. A recipe that declared no grouping shows everything,
      because guessing that a parameter is advanced is worse than a long form. */
  group?: "essential" | "advanced" | "all";
  /** What the agent set and why, shown against the field it set. */
  reasons?: Record<string, ProposedParameter>;
}) {
  const all = recipe.params_schema.properties ?? {};
  const declared = Object.values(all).some((p) => p["x-group"]);
  const props =
    group === "all" || !declared
      ? all
      : Object.fromEntries(
          Object.entries(all).filter(
            ([, prop]) => (prop["x-group"] ?? "advanced") === group,
          ),
        );

  const set = (key: string, value: unknown) => onChange({ ...values, [key]: value });

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {Object.entries(props).map(([name, prop]) => {
        const options = enumValues(prop);
        const explained = explanationsFor(name, recipe.option_explanations);
        const current = values[name];
        const chosen = explained?.find((o) => o.value === current);
        const label = labelFor(name, prop);

        if (options) {
          return (
            <Field
              key={name}
              label={label}
              help={helpFor(name, prop, reasons, chosen?.description)}
              caveat={chosen?.caveat}
            >
              <select
                className={inputClass}
                value={String(current ?? prop.default ?? "")}
                onChange={(e) => set(name, e.target.value === "" ? undefined : e.target.value)}
              >
                {/* A nullable enum with no default is genuinely unset. Showing
                    the first option instead would display a choice nobody made,
                    and hide the one the recipe will actually use. */}
                {isNullable(prop) && prop.default === null && (
                  <option value="">default</option>
                )}
                {options.map((value) => {
                  const info = explained?.find((o) => o.value === value);
                  return (
                    <option key={value} value={value}>
                      {info ? `${value} — ${info.label}` : value}
                    </option>
                  );
                })}
              </select>
            </Field>
          );
        }

        if (isList(prop)) {
          return (
            <Field
              key={name}
              label={label}
              help={helpFor(
                name, prop, reasons,
                prop.description ?? "comma separated; blank means all",
              )}
            >
              <input
                className={inputClass}
                value={Array.isArray(current) ? (current as string[]).join(",") : ""}
                placeholder="all"
                onChange={(e) => {
                  const parts = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
                  set(name, parts.length ? parts : undefined);
                }}
              />
            </Field>
          );
        }

        if (isBoolean(prop)) {
          return (
            <Field key={name} label={label} help={helpFor(name, prop, reasons)}>
              {/* Three states, not a checkbox: on, off, and left to the recipe.
                  A checkbox cannot say "unset", so it would send a choice for
                  every run whether or not anyone made one. */}
              <select
                className={inputClass}
                value={current === undefined ? "" : String(current)}
                onChange={(e) =>
                  set(name, e.target.value === "" ? undefined : e.target.value === "true")
                }
              >
                <option value="">default</option>
                <option value="true">yes</option>
                <option value="false">no</option>
              </select>
            </Field>
          );
        }

        if (isNumber(prop)) {
          return (
            <Field key={name} label={label} help={helpFor(name, prop, reasons)}>
              <input
                type="number"
                step="any"
                className={inputClass}
                value={current === undefined ? "" : String(current)}
                placeholder={placeholderFor(prop)}
                onChange={(e) =>
                  set(name, e.target.value === "" ? undefined : Number(e.target.value))
                }
              />
            </Field>
          );
        }

        return (
          <Field key={name} label={label} help={helpFor(name, prop, reasons)}>
            <input
              className={inputClass}
              value={current === undefined ? "" : String(current)}
              placeholder={placeholderFor(prop)}
              onChange={(e) => set(name, e.target.value === "" ? undefined : e.target.value)}
            />
          </Field>
        );
      })}
    </div>
  );
}

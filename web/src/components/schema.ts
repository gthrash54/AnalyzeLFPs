// Questions about a recipe's parameter schema that a component needs answered
// but should not have to work out inline.
//
// Its own file rather than sitting in SchemaForm, because a module that exports
// both components and plain functions loses fast refresh in development.

import type { Recipe } from "../api/types";

/** How many parameters a recipe puts in each half, so a button can say so.
 *
 *  A recipe that declared no grouping counts as all-essential: the form then
 *  shows everything, which is honest, rather than hiding fields on a guess. */
export function countByGroup(recipe: Recipe): { essential: number; advanced: number } {
  const props = Object.values(recipe.params_schema.properties ?? {});
  const declared = props.some((p) => p["x-group"]);
  if (!declared) return { essential: props.length, advanced: 0 };
  return {
    essential: props.filter((p) => p["x-group"] === "essential").length,
    advanced: props.filter((p) => (p["x-group"] ?? "advanced") === "advanced").length,
  };
}

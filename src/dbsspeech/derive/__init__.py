"""Building the derivative store: one pass over raw recordings, resampled.

The store exists so that analysis never reads raw again. Everything in this
package is pure: it reads a local block, transforms it, and hands back arrays
plus a record of exactly what the transform did. Nothing here talks to Box, and
nothing here knows a case number. The site-specific driver that fetches blocks
lives outside the package, in the archive's `_tools/` directory, by design.

`preprocess/resample.py` is deliberately left alone. Guardrail G6 and the
existing recipes depend on its behavior. This package resamples differently:
exact rational ratios, a designed anti-alias filter, and a report of the
measured response rather than an assumed cutoff fraction.
"""

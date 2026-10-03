# Reviewer fixes

New installs have empty `preferred_name` and `user_title` settings. The shared
`PersonalizationProfile` resolves title, then preferred name, then neutral address.
Prompts, deterministic replies, backend timeout messages, desktop presentation and
spoken reply text share that policy. Unicode and whitespace normalize consistently.
Save applies on the next reply; Clear removes custom identity and response style.
An existing title, including "All Father", remains an intentional saved value.
The creator's attribution is separate from the current user's identity.

The composer reports **Personalization: Off/Custom**. Identity fields include a
preview. Precision is checkable, saved, and described by the same sampling policy
used by streaming and ordinary generation: temperature 0.1, top-p 0.85, plus an
instruction to avoid guesses. Off uses the existing ordinary sampling policy.
This is no correctness guarantee or extra verification pass. All five controls
have accessible names, keyboard focus and descriptive tooltips. Files and Project
use distinct document/folder icons. Tools provides compact-layout access to the
hidden actions, personalization, Precision and command search.

## Computed graph insights

`graph_insight.py` constructs SymPy expressions from an allowlisted AST. It does
not use `eval`, `sympify` on arbitrary text, or model-generated mathematical facts.
Input length, expression-node count, powers, operation count and polynomial degree
are bounded. Each Cartesian `GraphSeries` carries a structured `GraphInsight`.

| Function | Supported properties |
|---|---|
| Quadratic | Real roots/multiplicity, y-intercept, vertex, symmetry, discriminant, domain/range and opening direction |
| Polynomial up to degree 8 | Real roots/multiplicity, derivative, critical points, local extrema, domain/range and end behavior |
| Bounded rational | Excluded denominator roots, removable holes, real roots, y-intercept, vertical/horizontal/slant asymptotes and critical points; range remains unknown |
| Affine sin/cos | Amplitude, period, phase and vertical shift, domain/range and real root families |
| Affine tan | Period, phase/vertical shift, domain exclusions, pole and root families; amplitude is undefined |
| Affine exp/log | Real domain/range, asymptote, intercepts and increasing/decreasing behavior |
| Other expressions | Existing sampled features explicitly limited to the displayed viewport; unknown global properties remain null |

Graph responses put mathematical results before rendering metadata. A failed or
unvalidated visualization still produces an error and never displays a success
placeholder. Non-Cartesian and surface renderers retain their existing geometry
and controls without inheriting unsupported Cartesian claims.

`numeric_format.py` is shared by native graph ticks, coordinate inspection,
surface legends and research SVG labels. Tick decimal precision follows spacing.
Ordinary thousands have comma separators; magnitudes at least 1e9 or below 1e-7
use scientific notation. Rounded negative zero becomes zero; non-finite values
display an unavailable marker. Exact symbolic fields remain available separately
from rounded coordinate summaries.

## Verification and publication scope

Regression checks cover identity save/change/clear/restart, Unicode, preserved
saved titles, neutral defaults, backend timeout wording, actual Precision payloads,
composer accessibility/compact access, real quadratic and polynomial results,
rational holes, transformed trig/exp/log, unsupported and malicious expressions,
numeric formatting, and honest render failures. Existing visual simulation tests
protect pause, step, reset, speed, trails, view switching and export behavior.

README screenshots are generated from the actual Qt application using temporary
settings. This source update is separate from older release binaries.

The isolated publication snapshot was verified on 3 October 2026: **564 Python
tests and 59 subtests passed**, **14 VNext tests passed**, and VNext type checking
passed. A model-free Python wheel built successfully; its dependency metadata,
imports from the unpacked wheel, neutral identity, and computed graph results were
checked. The existing terminal-cancellation regression was also fixed by stopping
owned command descendants, including Windows virtual-environment launchers.
These results do not claim a newly released Windows installer.

The NVIDIA integration and its evaluation models/benchmark artifacts were canceled
and removed at the user's request. They are excluded from this publication. The
hardware guidance in the README is explicitly not a benchmark result; no canceled
measurements are reproduced here.

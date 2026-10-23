# Technical reply amendment for MORICE 0.9.5

Long written audits now reach the selected thinking model. Words such as research, simulation or biological terms inside a specification no longer divert a written analysis into an empty Research project or an unrelated renderer. Explicit Research commands, structured calculation blocks and requests to draw or simulate remain available. Research synthesis resolves the installed default model when no custom model has been saved and stores one user turn per request.

The streaming backend honors each request's context and output budgets. A detailed Deep specification uses a 16,384-token context and up to 6,144 output tokens with the default routing configuration. Older turns and auxiliary context may be reduced; an oversized current prompt produces a clear error instead of silently removing its middle. Completion ignores delayed processing updates, so a completed result cannot restart the generation indicator.

## Conditional electromagnetic calculations

The existing scientific registry now includes `electromagnetic_harvester`, a linear single-degree-of-freedom base-excited model. Inputs require explicit units for mass, resonance and excitation frequency, unloaded mechanical Q, coupling, coil resistance, relative peak travel, peak acceleration, resistive load and converter efficiency. A load of -1 requests passive-load optimization; nonnegative values specify a fixed load.

An ordinary chat can recognize one complete two-column Markdown table with these labels and an explicit acceleration list or range. Ambiguous, incomplete or invalid tables fall back to ordinary model analysis. The recognizer does not infer missing parameters from chat history. Acceleration defaults explicitly to peak; an RMS label converts it to peak. If excitation frequency is absent, the report explicitly assumes resonance.

The calculation includes mechanical damping, coil loss and electromagnetic back-reaction. Its passive load is optimized for the supplied frequency, subject to the relative displacement limit. When even a short circuit cannot meet that limit, it reports an infeasible linear case without clipping motion and inventing power. An independent force/velocity impedance and circuit calculation checks the result, energy conservation and feasible neighbouring loads through the existing Kernel verifier.

The reply displays a conditional baseline table and detuning sweep before the model's interpretation in the same message. The original prompt is preserved. Potential DC applies the supplied efficiency; unspecified startup and quiescent losses can reduce actual usable output to zero. This tool does not validate magnetic geometry, coupling measurements, inductance, nonlinear stops, fatigue, converter behavior, fabrication or experiments. It distinguishes base displacement from relative resonant motion and unloaded mechanical Q from loaded Q.

The coupling and resonant load relation follow [Mösch and Fischerauer's primary study (2019)](https://doi.org/10.3390/mi10120826). This reference supports the analytical method; it is not evidence that a proposed device has been built or measured.

## Validation scope

Regression coverage exercises full-prompt model dispatch, one saved turn and reply, completion timers, unit conversion, ambiguous input rejection, resonance and detuning, passive-load sweeps, energy conservation, travel constraints and rejection of tampered calculation outputs. Local real-model checks use an unpublished reproduction prompt; private design inputs and generated answers are excluded from public packages.

The routing and calculation repairs do not turn a small local model into a certified engineering solver. Generated interpretation remains unverified and must be reviewed against calculations and real evidence. Existing file, command and execution permissions remain in force. This amendment replaces assets of the existing 0.9.5 publication without creating a new version.

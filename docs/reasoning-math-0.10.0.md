# Reasoning model and mathematical replies in 0.10.0

The reasoning profile now prefers `Qwen3.5-4B-abliterated.Q6_K.gguf` when that file is installed in the local data directory's `models/llm` folder, the application folder, or its model assets. An explicit model path, configured provider or environment selection still takes precedence. If the new weights are absent, existing model fallbacks remain available. Weights are not included in public packages or downloaded automatically.

Settings → Models still controls the primary model and separate Fast Reply Model. Automatic routing uses the fast profile for ordinary conversation and the reasoning profile for deeper requests. Changing the primary model does not overwrite the fast selection or remove older weights. Local file registration can use a same-volume hard link to avoid storing a second copy; an existing distinct file must not be overwritten.

## Compatibility and answer delivery

Qwen3.5's supplied chat template rejects a second system-role message. MORICE now joins the ordered initial host instructions into one system message at the transport boundary, without changing user turns, history or policy. The same normalization covers synchronous, streaming, tokenizer/template and optional in-process paths.

The modern llama.cpp request field is `reasoning_budget_tokens`. MORICE reserves part of each completion for the visible answer instead of letting hidden reasoning consume every token. A bounded concluding instruction accompanies enabled reasoning only. Older backends that finish with hidden reasoning and no answer get one retry with reasoning disabled and the same original conversation. Cancellation prevents that retry. No reasoning trace is deliberately displayed as an answer. Automatic GPU-layer values also import correctly.

The model still makes mistakes. An earlier controlled trial made a kilogram-to-milligram conversion error; Precision mode now supplies explicit SI conversion references. These references are instructions, not independent verification of a model's numbers. Use the existing unit-aware Research calculations and their actual receipts for numerical grounding. A plain generated answer does not establish physical feasibility, source verification or measured performance.

## Mathematical rendering

The bundled renderer recognizes `\(...\)`, `\[...\]`, `$...$` and `$$...$$` before Markdown can remove escapes or interpret subscripts. KaTeX renders the resulting tokens with its bundled fonts. Equations work offline; no remote math renderer is required. Inline and fenced code stay literal, ordinary currency stays text, and malformed expressions leave readable source instead of breaking the surrounding reply.

Streaming uses a stable text preview, then finalizes complete Markdown and equations in the same bubble. Copying retains the message text. Optional forms of address preserve the beginning of headings, code fences and display equations. History and duplicate-message checks remain in place.

The component uses the documented [KaTeX string-rendering API](https://katex.org/docs/api) and bounded [rendering options](https://katex.org/docs/options). The request adapter follows llama.cpp's [reasoning-budget and template handling](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-common.cpp). No model-generated JavaScript is executed.

## Validation and limits

Native tests check all four math delimiters, subscripts, fractions, units, tables, code, currency, invalid-expression fallback and actual stream finalization without duplicate rows. The package startup probe checks two rendered equations in the existing bubble using bundled assets. Wheel and frozen parity checks include every bundled web asset and font.

The supplied reply example produced 14 KaTeX expressions and zero parser errors. It was treated as rendering data; its engineering and paper claims were not verified. A window capture failed validation and was excluded. This is a programmatic DOM/layout check, not certification of every display driver or DPI setting.

Actual local-model samples, the final regression, executable/package fingerprints and publication status are recorded in the [local validation report](nlui-rich-validation-0.10.0.md). The tested CUDA runtime is installed separately; CPU inference is slower and has not been certified against every long technical prompt. Short controlled samples are not an intelligence score or a guarantee that all generated calculations are correct.

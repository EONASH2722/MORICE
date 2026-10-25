/* Preserve TeX as Markdown tokens before escaping, emphasis or typography. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.MoriceMath = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const limit = 65536;
  function escaped(source, index) {
    let slashes = 0;
    while (index > 0 && source[--index] === "\\") slashes++;
    return slashes % 2 === 1;
  }
  function closing(source, marker, from) {
    let at = from;
    while ((at = source.indexOf(marker, at)) !== -1) {
      if (!escaped(source, at) && (marker !== "$" ||
          (source[at - 1] !== "$" && source[at + 1] !== "$" && !/\d/.test(source[at + 1] || "")))) return at;
      at += marker.length;
    }
    return -1;
  }
  function install(md, katex) {
    function render(tokens, index) {
      const token = tokens[index];
      try {
        if (token.content.length > limit) throw new Error("Expression exceeds the display limit.");
        return katex.renderToString(token.content, {
          displayMode: token.type === "morice_math_block" || token.meta.display,
          throwOnError: true, strict: "warn", trust: false, maxExpand: 1000, maxSize: 20,
          output: "htmlAndMathml"
        });
      } catch (error) {
        return '<code class="morice-math-error" title="Expression could not be rendered">' +
          md.utils.escapeHtml(token.content) + "</code>";
      }
    }
    md.inline.ruler.before("escape", "morice_math", function (state, silent) {
      const start = state.pos, rest = state.src.slice(start);
      let left, right, display = false;
      if (rest.startsWith("\\(")) { left = "\\("; right = "\\)"; }
      else if (rest.startsWith("\\[")) { left = "\\["; right = "\\]"; display = true; }
      else if (rest.startsWith("$$")) { left = right = "$$"; display = true; }
      else if (rest.startsWith("$")) left = right = "$";
      else return false;
      const end = closing(state.src, right, start + left.length);
      if (end < 0 || end > state.posMax || end - start > limit || end === start + left.length) return false;
      if (!silent) {
        const token = state.push("morice_math_inline", "math", 0);
        token.content = state.src.slice(start + left.length, end).trim(); token.meta = { display };
      }
      state.pos = end + right.length;
      return true;
    });
    md.block.ruler.before("fence", "morice_math", function (state, startLine, endLine, silent) {
      if (state.sCount[startLine] - state.blkIndent >= 4) return false;
      const start = state.bMarks[startLine] + state.tShift[startLine];
      const first = state.src.slice(start, state.eMarks[startLine]);
      const left = first.startsWith("$$") ? "$$" : first.startsWith("\\[") ? "\\[" : "";
      if (!left) return false;
      const right = left === "$$" ? "$$" : "\\]";
      let text = first.slice(left.length), next = startLine + 1, at = closing(text, right, 0);
      while (at < 0 && next < endLine && text.length <= limit) {
        text += "\n" + state.src.slice(state.bMarks[next] + state.tShift[next], state.eMarks[next]);
        next++; at = closing(text, right, 0);
      }
      if (at < 0 || text.slice(at + right.length).trim() || at > limit) return false;
      if (silent) return true;
      const token = state.push("morice_math_block", "math", 0);
      token.block = true; token.content = text.slice(0, at).trim(); token.map = [startLine, next];
      state.line = next;
      return true;
    }, { alt: ["paragraph", "reference", "blockquote", "list"] });
    md.renderer.rules.morice_math_inline = render;
    md.renderer.rules.morice_math_block = function (tokens, index) { return render(tokens, index) + "\n"; };
    return md;
  }
  return { install };
});

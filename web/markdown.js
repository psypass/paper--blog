const PaperBlogMarkdown = (() => {
  const typeLabels = {
    arxiv: "arXiv",
    pdf: "PDF",
    markdown: "Markdown",
    docx: "Word",
    unsupported: "暂不支持"
  };

  function guessType(value, fileName = "") {
    const target = (fileName || value || "").trim();
    const lower = target.toLowerCase();
    if (/^\d{4}\.\d{4,5}(v\d+)?$/.test(target)) return "arxiv";
    if (lower.includes("arxiv.org/abs/") || lower.includes("arxiv.org/pdf/")) return "arxiv";
    if (lower.endsWith(".pdf")) return "pdf";
    if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "markdown";
    if (lower.endsWith(".docx")) return "docx";
    if (value.trim().startsWith("#")) return "markdown";
    return value.trim() ? "question" : "";
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function renderInlineMarkdown(value) {
    return escapeHtml(value)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\\\((.*?)\\\)/g, '<span class="math-inline">\\($1\\)</span>');
  }

  function renderMarkdown(value) {
    const text = String(value || "").trim();
    if (!text) return "";
    const normalized = text.replace(/\r\n/g, "\n").replace(/\\\[(.*?)\\\]/gs, (_, formula) => {
      return `\n\n@@MATH_BLOCK:${escapeHtml(formula.trim())}@@\n\n`;
    });
    const blocks = normalized.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
    return blocks
      .map((block) => {
        if (block.startsWith("@@MATH_BLOCK:")) {
          return `<div class="math-block">\\[${block.replace(/^@@MATH_BLOCK:/, "").replace(/@@$/, "")}\\]</div>`;
        }
        const heading = block.match(/^(#{1,3})\s+(.+)$/);
        if (heading) {
          const level = Math.min(heading[1].length + 2, 5);
          return `<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`;
        }
        const lines = block.split("\n");
        if (lines.every((line) => /^\s*[-*]\s+/.test(line))) {
          return `<ul>${lines.map((line) => `<li>${renderInlineMarkdown(line.replace(/^\s*[-*]\s+/, ""))}</li>`).join("")}</ul>`;
        }
        return `<p>${lines.map(renderInlineMarkdown).join("<br>")}</p>`;
      })
      .join("");
  }

  return { typeLabels, guessType, renderMarkdown };
})();

window.PaperBlogMarkdown = PaperBlogMarkdown;

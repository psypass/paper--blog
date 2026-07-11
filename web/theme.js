const PaperBlogTheme = (() => {
  function normalizeTheme(value) {
    return value === "dark" ? "dark" : "light";
  }

  function applyDocumentTheme(value) {
    const theme = normalizeTheme(value);
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("paper-blog-agent.theme", theme);
    return theme;
  }

  function themedResultHtmlForTheme(html, theme) {
    const value = String(html || "");
    const safeTheme = normalizeTheme(theme);
    if (/<html\b[^>]*data-theme=/.test(value)) {
      return value.replace(/(<html\b[^>]*data-theme=)["'][^"']*["']/, `$1"${safeTheme}"`);
    }
    return value.replace(/<html\b([^>]*)>/, `<html$1 data-theme="${safeTheme}">`);
  }

  return { applyDocumentTheme, normalizeTheme, themedResultHtmlForTheme };
})();

window.PaperBlogTheme = PaperBlogTheme;

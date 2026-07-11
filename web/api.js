const PaperBlogApi = (() => {
  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok || payload.status === "error") {
      throw new Error(payload.message || "请求失败");
    }
    return payload;
  }

  return { jsonFetch };
})();

window.PaperBlogApi = PaperBlogApi;

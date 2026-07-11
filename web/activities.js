const PaperBlogActivities = (() => {
  const agentStageSummaries = {
    local_retrieval: "检索论文片段",
    sufficiency_judgment: "判断来源是否足够",
    context_insufficient: "来源不足，准备补充证据",
    context_sufficient: "来源足够，准备回答",
    context_not_checked: "不联网，直接依据论文回答",
    context_unavailable: "证据判断暂不可用",
    search_planning: "规划联网检索词",
    web_search: "联网搜索补充资料",
    sufficiency_recheck: "核对搜索结果",
    web_search_failed: "联网搜索失败",
    answering: "组织最终回答",
    generation: "整理论文材料"
  };

  function activityDetail(event) {
    if (event.query) return `Query: ${event.query}`;
    if (event.reason) return event.reason;
    return "";
  }

  function activitySummary(event) {
    return agentStageSummaries[event.stage] || event.text || "Agent 正在处理";
  }

  function activityForEvidenceState(event) {
    if (event.context_status === "not_checked") {
      return { stage: "context_not_checked", text: "不联网模式，直接依据论文内容回答" };
    }
    if (event.context_status === "unavailable") {
      return { stage: "context_unavailable", text: "证据判断暂不可用，继续按现有证据处理" };
    }
    return event.context_sufficient
      ? { stage: "context_sufficient", text: "来源足够，可以开始回答" }
      : { stage: "context_insufficient", text: "来源还不够，需要补充证据" };
  }

  return { activityDetail, activitySummary, activityForEvidenceState };
})();

window.PaperBlogActivities = PaperBlogActivities;

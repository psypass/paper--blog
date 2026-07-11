const { computed, createApp, nextTick, onMounted, ref } = Vue;
const { typeLabels, guessType, renderMarkdown } = window.PaperBlogMarkdown;
const { activityDetail, activityForEvidenceState, activitySummary } = window.PaperBlogActivities;
const { createBlogTypePill } = window.PaperBlogSearchMode;
const { applyDocumentTheme, themedResultHtmlForTheme } = window.PaperBlogTheme;
createApp({
  setup() {
    const activePaperId = ref("");
    const activeTitle = ref("新的调研");
    const activeSubtitle = ref("材料完成后会成为当前聊天的知识来源。");
    const blogType = ref("learning");
    const draft = ref("");
    const error = ref("");
    const file = ref(null);
    const history = ref([]);
    const loadingModels = ref(false);
    const modelOptions = ref([]);
    const modelStatus = ref("模型列表来自供应商 /models 接口");
    const providers = ref([]);
    const profile = ref({
      language: "中文",
      default_blog_type: "learning",
      target_reader: "正在学习该方向的读者",
      tone: "清晰、可靠、避免营销腔",
      structure: ["导语", "核心问题", "方法解释", "结果解读", "局限", "总结"],
      depth: "中等",
      math_level: "保留必要公式并解释直觉",
      focus_areas: ["方法", "核心概念", "局限"]
    });
    const profileFocusText = ref("方法、核心概念、局限");
    const profileStructureText = ref("导语、核心问题、方法解释、结果解读、局限、总结");
    const blogTypePillCanvas = ref(null);
    const search = ref({
      mode: "auto",
      provider: "tavily",
      apiKey: "",
      maxResults: 5
    });
    const settingsOpen = ref(false);
    const settingsSection = ref("model");
    const theme = ref(localStorage.getItem("paper-blog-agent.theme") || "light");
    const settingsSections = [
      { id: "model", label: "模型设置", description: "供应商、模型和 API key" },
      { id: "profile", label: "用户偏好", description: "语言、语气和写作深度" },
      { id: "search", label: "联网补充", description: "搜索供应商和触发模式" }
    ];
    const llm = ref({
      providerId: "deepseek",
      baseUrl: "https://api.deepseek.com",
      modelsPath: "/models",
      apiKey: "",
      model: "deepseek-chat"
    });
    const messages = ref([
      {
        id: crypto.randomUUID(),
        role: "assistant",
        text: "把论文链接、Markdown 内容或文件发过来。我会先完成调研，再把这篇材料放进当前会话里。"
      }
    ]);
    const messagesEl = ref(null);
    const working = ref(false);
    const ACTIVITY_QUEUE_TICK_MS = 500;

    const predictedType = computed(() => guessType(draft.value, file.value?.name || ""));
    const detectorText = computed(() => {
      if (file.value) return `将识别附件：${typeLabels[predictedType.value] || predictedType.value}`;
      if (!predictedType.value) return activePaperId.value ? "继续追问当前论文，或发送新材料" : "等待材料";
      if (predictedType.value === "question") return activePaperId.value ? "将作为追问发送" : "像是普通问题；先给我一篇材料会更有用";
      return `将识别为：${typeLabels[predictedType.value] || predictedType.value}`;
    });
    const statusLabel = computed(() => {
      if (working.value) return "Working";
      if (error.value) return "Error";
      return activePaperId.value ? "Knowledge ready" : "Ready";
    });

    function sourceLabel(type) { return typeLabels[type] || type || "-"; }
    function applyTheme(value) { theme.value = applyDocumentTheme(value); }

    function toggleTheme() {
      applyTheme(theme.value === "dark" ? "light" : "dark");
    }

    function themedResultHtml(html) {
      return themedResultHtmlForTheme(html, theme.value);
    }

    async function loadHistory() {
      const response = await fetch("/api/history");
      const payload = await response.json();
      if (payload.status === "ok") history.value = payload.items;
    }

    async function loadProviders() {
      const response = await fetch("/api/llm/providers");
      const payload = await response.json();
      if (payload.status === "ok") providers.value = payload.providers;
    }

    async function loadProfile() {
      const response = await fetch("/api/profile");
      const payload = await response.json();
      if (payload.status !== "ok") return;
      profile.value = { ...profile.value, ...payload.profile };
      profileStructureText.value = listToText(profile.value.structure);
      profileFocusText.value = listToText(profile.value.focus_areas);
      if (profile.value.default_blog_type) blogType.value = profile.value.default_blog_type;
    }

    function scrollToBottom() {
      nextTick(() => {
        if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
      });
    }

    function pushMessage(role, payload) {
      const message = { id: crypto.randomUUID(), role, ...payload };
      messages.value.push(message);
      scrollToBottom();
      return messages.value[messages.value.length - 1];
    }

    function setLiveStatus(message, text) {
      message.statusBase = text || "我还在处理";
      message.statusTick = 0;
      message.text = message.statusBase;
      scrollToBottom();
    }

    function addActivityNow(message, event) {
      if (!message.activities) message.activities = [];
      const activities = message.activities;
      const last = activities[activities.length - 1];
      if (last && last.state === "running") last.state = "done";
      const activity = {
        id: crypto.randomUUID(),
        stage: event.stage || event.type,
        text: event.text || "更新状态",
        summary: activitySummary(event),
        detail: activityDetail(event),
        sites: event.sites || [],
        state: event.stage === "web_search_failed" ? "failed" : "running"
      };
      activities.push(activity);
      message.currentActivityId = activity.id;
      if (message.pending) {
        message.statusBase = activity.text || activity.summary;
        message.statusTick = 0;
        message.text = activity.text || activity.summary;
      }
      if (message.activityOpen === undefined) message.activityOpen = false;
      scrollToBottom();
    }

    function stopActivityTicker(message) {
      if (message.activityTicker) {
        window.clearInterval(message.activityTicker);
        message.activityTicker = null;
      }
      if (message.activityResolve) {
        message.activityResolve();
        message.activityResolve = null;
      }
      message.activityPromise = null;
    }

    function publishNextActivity(message) {
      if (!message.activityQueue?.length) {
        stopActivityTicker(message);
        return;
      }
      addActivityNow(message, message.activityQueue.shift());
    }

    function startActivityTicker(message) {
      if (message.activityTicker) return;
      if (!message.activityPromise) {
        message.activityPromise = new Promise((resolve) => {
          message.activityResolve = resolve;
        });
      }
      publishNextActivity(message);
      message.activityTicker = window.setInterval(() => publishNextActivity(message), ACTIVITY_QUEUE_TICK_MS);
    }

    function queueActivity(message, event) {
      if (!message.activityQueue) message.activityQueue = [];
      message.activityQueue.push(event);
      startActivityTicker(message);
      return message.activityPromise || Promise.resolve();
    }

    async function waitForActivities(message) {
      while (message.activityPromise || message.activityQueue?.length) {
        await message.activityPromise;
      }
    }

    function addActivity(message, event) {
      return queueActivity(message, event);
    }

    function finishActivities(message, state = "done") {
      for (const activity of message.activities || []) {
        if (activity.state === "running") activity.state = state;
      }
    }

    function currentActivity(message) {
      const activities = message.activities || [];
      return activities.find((activity) => activity.id === message.currentActivityId) || activities[activities.length - 1] || null;
    }

    function startLiveStatus(message, text) {
      const frames = ["", "。", "。。", "。。。"];
      setLiveStatus(message, text);
      return window.setInterval(() => {
        if (!message.pending) return;
        message.statusTick = (message.statusTick || 0) + 1;
        message.text = `${message.statusBase}${frames[message.statusTick % frames.length]}`;
        scrollToBottom();
      }, 450);
    }

    function stopLiveStatus(timer) {
      if (timer) window.clearInterval(timer);
    }

    function onFileChange(event) {
      file.value = event.target.files?.[0] || null;
      error.value = "";
    }

    function applyProvider() {
      const provider = providers.value.find((item) => item.id === llm.value.providerId);
      if (!provider) return;
      llm.value.baseUrl = provider.base_url;
      llm.value.modelsPath = provider.models_path || "/models";
      llm.value.model = provider.default_model || "";
      modelOptions.value = [];
      modelStatus.value = "模型列表来自供应商 /models 接口";
    }

    async function loadModels(options = {}) {
      if (!llm.value.apiKey || !llm.value.baseUrl) {
        if (!options.silent) modelStatus.value = "填入 API Key 后会自动获取模型列表";
        return;
      }
      modelStatus.value = options.silent ? "正在自动获取模型列表" : "正在获取模型列表";
      loadingModels.value = true;
      try {
        const response = await fetch("/api/llm/models", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider_id: llm.value.providerId,
            base_url: llm.value.baseUrl,
            api_key: llm.value.apiKey,
            models_path: llm.value.modelsPath || "/models",
            model: llm.value.model
          })
        });
        const payload = await response.json();
        if (!response.ok || payload.status !== "ok") {
          throw new Error(payload.message || "获取失败");
        }
        modelOptions.value = payload.models;
        if (payload.model) llm.value.model = payload.model;
        else if (payload.models.length && !payload.models.includes(llm.value.model)) {
          llm.value.model = payload.models[0];
        }
        modelStatus.value = `已获取并保存 ${payload.models.length} 个模型`;
      } catch (err) {
        modelStatus.value = err.message || String(err);
      } finally {
        loadingModels.value = false;
      }
    }

    async function saveAppConfig() {
      const response = await fetch("/api/llm/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: llm.value.providerId,
          base_url: llm.value.baseUrl,
          api_key: llm.value.apiKey,
          models_path: llm.value.modelsPath || "/models",
          model: llm.value.model,
          models: modelOptions.value,
          web_search_mode: search.value.mode,
          search_provider: search.value.provider,
          search_api_key: search.value.apiKey,
          max_search_results: search.value.maxResults
        })
      });
      const payload = await response.json();
      if (!response.ok || payload.status !== "ok") throw new Error(payload.message || "配置保存失败");
      return payload.config;
    }

    async function persistConfigQuietly() {
      try {
        await saveAppConfig();
        modelStatus.value = modelOptions.value.length ? `已保存 ${modelOptions.value.length} 个模型` : "已保存配置";
      } catch (err) {
        modelStatus.value = err.message || String(err);
      }
    }
    const { blogTypeIndex, blogTypeStatus, selectBlogType, updateBlogType } = createBlogTypePill(blogType, blogTypePillCanvas, computed);
    async function saveSettings() {
      profile.value.structure = textToList(profileStructureText.value);
      profile.value.focus_areas = textToList(profileFocusText.value);
      const response = await fetch("/api/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile.value)
      });
      const payload = await response.json();
      if (!response.ok || payload.status !== "ok") {
        modelStatus.value = payload.message || "偏好保存失败";
        return;
      }
      profile.value = { ...profile.value, ...payload.profile };
      try {
        await saveAppConfig();
      } catch (err) {
        modelStatus.value = err.message || String(err);
        return;
      }
      modelStatus.value = "已保存到配置文件";
      settingsOpen.value = false;
    }

    async function loadSavedSettings() {
      const savedKeys = localStorage.getItem("paper-blog-agent.keys");
      if (savedKeys) {
        try {
          const keys = JSON.parse(savedKeys);
          llm.value.apiKey = keys.llmApiKey || "";
          search.value.apiKey = keys.searchApiKey || "";
        } catch {
          localStorage.removeItem("paper-blog-agent.keys");
        }
      }
      const saved = localStorage.getItem("paper-blog-agent.llm");
      if (saved) {
        try {
          const legacy = JSON.parse(saved);
          llm.value.apiKey = llm.value.apiKey || legacy.apiKey || "";
        } catch {
          localStorage.removeItem("paper-blog-agent.llm");
        }
      }
      const savedSearch = localStorage.getItem("paper-blog-agent.search");
      if (savedSearch) {
        try {
          const legacySearch = JSON.parse(savedSearch);
          search.value.apiKey = search.value.apiKey || legacySearch.apiKey || "";
        } catch {
          localStorage.removeItem("paper-blog-agent.search");
        }
      }

      try {
        const response = await fetch("/api/llm/config");
        const payload = await response.json();
        if (payload.status !== "ok") return;
        const config = payload.config || {};
        const savedLlm = config.llm || {};
        const savedSearchConfig = config.search || {};
        llm.value = {
          ...llm.value,
          providerId: savedLlm.providerId || llm.value.providerId,
          baseUrl: savedLlm.baseUrl || llm.value.baseUrl,
          apiKey: savedLlm.apiKey || llm.value.apiKey,
          modelsPath: savedLlm.modelsPath || llm.value.modelsPath,
          model: savedLlm.model || llm.value.model
        };
        modelOptions.value = Array.isArray(savedLlm.models) ? savedLlm.models : [];
        search.value = {
          ...search.value,
          mode: savedSearchConfig.mode || search.value.mode,
          provider: savedSearchConfig.provider || search.value.provider,
          apiKey: savedSearchConfig.apiKey || search.value.apiKey,
          maxResults: savedSearchConfig.maxResults || search.value.maxResults
        };
        modelStatus.value = modelOptions.value.length ? `已加载 ${modelOptions.value.length} 个已保存模型` : "模型列表来自供应商 /models 接口";
      } catch {
        modelStatus.value = "配置文件读取失败，使用浏览器本地设置";
      }
      if (llm.value.apiKey && llm.value.baseUrl) {
        await loadModels({ silent: true });
      }
    }

    function listToText(value) {
      return Array.isArray(value) ? value.join("、") : String(value || "");
    }

    function textToList(value) {
      return String(value || "")
        .split(/[、,，]/)
        .map((item) => item.trim())
        .filter(Boolean);
    }

    function newConversation() {
      activePaperId.value = "";
      activeTitle.value = "新的调研";
      activeSubtitle.value = "材料完成后会成为当前聊天的知识来源。";
      draft.value = "";
      file.value = null;
      error.value = "";
      messages.value = [
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: "把论文链接、Markdown 内容或文件发过来。我会先完成调研，再把这篇材料放进当前会话里。"
        }
      ];
    }

    function selectProject(item) {
      activePaperId.value = item.paper_id;
      activeTitle.value = item.title;
      activeSubtitle.value = `${sourceLabel(item.source_type)} · 已作为知识来源`;
      messages.value = [
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: `已切换到《${item.title}》。你可以继续问这篇材料里的方法、结论、局限或写作角度。`
        }
      ];
      scrollToBottom();
    }

    async function deleteProject(item) {
      if (!confirm(`删除《${item.title}》？这会同时删除本地生成的 Markdown、HTML 和知识源。`)) return;
      error.value = "";
      try {
        const response = await fetch("/api/history/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paper_id: item.paper_id })
        });
        const payload = await response.json();
        if (!response.ok || payload.status !== "ok") {
          throw new Error(payload.message || "删除失败");
        }
        history.value = history.value.filter((project) => project.paper_id !== item.paper_id);
        if (activePaperId.value === item.paper_id) {
          newConversation();
        }
      } catch (err) {
        error.value = err.message || String(err);
        pushMessage("assistant", { text: error.value });
      }
    }

    async function submit() {
      if (working.value) return;
      const text = draft.value.trim();
      const selectedFile = file.value;
      const predicted = predictedType.value;
      if (!text && !selectedFile) return;
      error.value = "";
      working.value = true;
      pushMessage("user", { text: selectedFile ? `上传：${selectedFile.name}` : text });
      draft.value = "";
      file.value = null;

      try {
        if ((predicted === "question" || !predicted) && activePaperId.value && !selectedFile) {
          await askCurrentPaper(text);
        } else {
          await generateFromMaterial(text, selectedFile);
        }
      } catch (err) {
        error.value = err.message || String(err);
        pushMessage("assistant", { text: error.value });
      } finally {
        working.value = false;
      }
    }

    async function generateFromMaterial(text, selectedFile) {
      const data = new FormData();
      data.set("source_text", text);
      data.set("source_name", text.startsWith("#") ? "pasted.md" : "");
      data.set("blog_type", blogType.value);
      data.set("base_url", llm.value.baseUrl);
      data.set("api_key", llm.value.apiKey);
      data.set("model", llm.value.model);
      if (selectedFile) data.set("file", selectedFile);

      const assistantMessage = pushMessage("assistant", { text: "正在接收材料...", pending: true, activities: [], activityOpen: false });
      queueActivity(assistantMessage, { stage: "generation", text: "接收材料并启动整理流程" });
      const statusTimer = startLiveStatus(assistantMessage, "正在接收材料");
      let payload = null;
      try {
        const response = await fetch("/api/generate/stream", { method: "POST", body: data });
        if (!response.ok || !response.body) {
          throw new Error("生成失败");
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() || "";
          for (const rawEvent of events) {
            const line = rawEvent.split("\n").find((item) => item.startsWith("data:"));
            if (!line) continue;
            const event = JSON.parse(line.replace(/^data:\s*/, ""));
            if (event.type === "status") {
              queueActivity(assistantMessage, event);
            } else if (event.type === "done") {
              payload = event.result;
            } else if (event.type === "error") {
              await waitForActivities(assistantMessage);
              finishActivities(assistantMessage, "failed");
              throw new Error(event.message || "生成失败");
            }
          }
        }
      } finally {
        stopLiveStatus(statusTimer);
      }

      if (!payload || payload.status !== "ok") {
        throw new Error(payload?.message || payload?.errors?.join("; ") || "生成失败");
      }

      await waitForActivities(assistantMessage);
      finishActivities(assistantMessage);
      activePaperId.value = payload.paper_id;
      activeTitle.value = extractTitle(payload.markdown) || payload.paper_id;
      activeSubtitle.value = `${typeLabels[payload.detected_type] || payload.detected_type} · 已作为知识来源`;
      assistantMessage.pending = false;
      assistantMessage.text = "调研完成。这篇材料现在已经接入当前会话，可以继续追问。";
      assistantMessage.result = {
        title: activeTitle.value,
        detectedType: typeLabels[payload.detected_type] || payload.detected_type,
        verifyState: payload.verification?.status || "-",
        markdownPath: payload.markdown_path,
        htmlPath: payload.html_path,
        htmlUrl: payload.html_url,
        html: payload.html
      };
      await loadHistory();
    }

    async function askCurrentPaper(question) {
      const assistantMessage = pushMessage("assistant", { text: "正在检索相关片段...", pending: true, activities: [], activityOpen: false });
      queueActivity(assistantMessage, { stage: "local_retrieval", text: "准备检索当前论文知识源" });
      const statusTimer = startLiveStatus(assistantMessage, "正在检索相关片段");
      let chatAnswerBuffer = "";
      let answerStarted = false;
      try {
        const response = await fetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            paper_id: activePaperId.value,
            question,
            base_url: llm.value.baseUrl,
            api_key: llm.value.apiKey,
            model: llm.value.model,
            web_search_mode: search.value.mode,
            search_provider: search.value.provider,
            search_api_key: search.value.apiKey,
            max_search_results: search.value.maxResults
          })
        });
        if (!response.ok || !response.body) {
          throw new Error("回答失败");
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let streamDone = false;

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() || "";
          for (const rawEvent of events) {
            const line = rawEvent.split("\n").find((item) => item.startsWith("data:"));
            if (!line) continue;
            const event = JSON.parse(line.replace(/^data:\s*/, ""));
            if (event.type === "status") {
              if (!answerStarted) {
                queueActivity(assistantMessage, event);
              }
            } else if (event.type === "state") {
              assistantMessage.agentState = event;
              if (!answerStarted) {
                const stateActivity = activityForEvidenceState(event);
                queueActivity(assistantMessage, {
                  type: "state",
                  stage: stateActivity.stage,
                  text: stateActivity.text,
                  reason: event.reason
                });
              }
            } else if (event.type === "delta") {
              chatAnswerBuffer += event.text || "";
              if (!answerStarted) {
                stopLiveStatus(statusTimer);
                assistantMessage.text = chatAnswerBuffer;
                assistantMessage.pending = false;
                answerStarted = true;
              } else if (answerStarted) {
                assistantMessage.text = chatAnswerBuffer;
              }
              scrollToBottom();
            } else if (event.type === "done") {
              assistantMessage.sources = event.sources || [];
              assistantMessage.agentState = {
                context_sufficient: event.context_sufficient,
                context_status: event.context_status,
                evidence_round: event.evidence_round
              };
              streamDone = true;
            } else if (event.type === "error") {
              await waitForActivities(assistantMessage);
              finishActivities(assistantMessage, "failed");
              throw new Error(event.message || "回答失败");
            }
          }
          if (streamDone) {
            await reader.cancel();
            break;
          }
        }
      } finally {
        stopLiveStatus(statusTimer);
      }
      await waitForActivities(assistantMessage);
      finishActivities(assistantMessage);
      if (!answerStarted) {
        assistantMessage.text = chatAnswerBuffer;
        assistantMessage.pending = false;
      }
      scrollToBottom();
    }

    function extractTitle(markdown) {
      const match = markdown.match(/^#\s+(.+)$/m);
      return match?.[1]?.replace(/：.+$/, "") || "";
    }

    onMounted(async () => {
      applyTheme(theme.value);
      await loadProviders();
      await loadSavedSettings();
      await loadProfile();
      await loadHistory();
    });

    return {
      activePaperId,
      activeSubtitle,
      activeTitle,
      blogType,
      blogTypeIndex,
      blogTypePillCanvas,
      blogTypeStatus,
      deleteProject,
      detectorText,
      draft,
      file,
      history,
      llm,
      loadingModels,
      currentActivity,
      loadModels,
      messages,
      messagesEl,
      modelOptions,
      modelStatus,
      newConversation,
      onFileChange,
      applyProvider,
      profile,
      profileFocusText,
      profileStructureText,
      providers,
      renderMarkdown,
      saveSettings,
      search,
      selectProject,
      selectBlogType,
      persistConfigQuietly,
      settingsSection,
      settingsSections,
      settingsOpen,
      sourceLabel,
      statusLabel,
      submit,
      theme,
      themedResultHtml,
      toggleTheme,
      updateBlogType,
      working
    };
  }
}).mount("#app");

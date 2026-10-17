// 雾歇香薰 · AI 客服前端
// 连接本地 FastAPI 后端（SSE 流式），解析 retrieval / sources / content / error / done 事件。
// 这里只放后端地址，绝不出现任何 API Key。

const API_BASE = "http://127.0.0.1:8000";

const messagesEl = document.getElementById("chat-messages");
const textarea = document.getElementById("chat-textarea");
const countEl = document.getElementById("chat-count");
const sendBtn = document.getElementById("send-btn");

let streaming = false;

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function updateCount() {
  countEl.textContent = `${textarea.value.length} / 200`;
}

function setStreaming(on) {
  streaming = on;
  sendBtn.disabled = on;
  textarea.disabled = on;
  sendBtn.textContent = on ? "回答中…" : "发送 ↑";
}

function clearInput() {
  textarea.value = "";
  updateCount();
}

// ---- 消息气泡 ----
function appendUserMessage(text) {
  const wrap = document.createElement("div");
  wrap.className = "msg msg--user";
  const sender = document.createElement("span");
  sender.className = "msg-sender";
  sender.textContent = "YOU";
  const bubble = document.createElement("p");
  bubble.className = "msg-bubble";
  bubble.textContent = text;
  wrap.append(sender, bubble);
  messagesEl.appendChild(wrap);
  scrollToBottom();
}

// 返回 { wrap, answer }，answer 先显示「思考中…」占位，流式文本到达后逐段追加。
function appendAiMessage() {
  const wrap = document.createElement("div");
  wrap.className = "msg msg--ai";
  const sender = document.createElement("span");
  sender.className = "msg-sender";
  sender.textContent = "MISTAWAY";
  const answer = document.createElement("p");
  answer.className = "msg-answer";
  answer.textContent = "思考中…";
  wrap.append(sender, answer);
  messagesEl.appendChild(wrap);
  scrollToBottom();
  return { wrap, answer };
}

// ---- 来源渲染：标题 + 分数 + 正文摘录 ----
function fmtScore(v) {
  return typeof v === "number" ? v.toFixed(3) : "—";
}

function renderSources(wrap, sources) {
  if (!Array.isArray(sources) || sources.length === 0) return;
  const box = document.createElement("div");
  box.className = "sources";

  const label = document.createElement("p");
  label.className = "sources-label";
  label.textContent = "依据来源";
  box.appendChild(label);

  sources.forEach((s) => {
    const item = document.createElement("div");
    item.className = "source-item";

    const head = document.createElement("div");
    head.className = "source-head";
    const title = document.createElement("span");
    title.className = "source-title";
    title.textContent = s.title || s.category || "资料片段";
    const score = document.createElement("span");
    score.className = "source-score";
    score.textContent = `检索分 ${fmtScore(s.final_score)} · 精排分 ${fmtScore(s.rerank_score)}`;
    head.append(title, score);

    const body = document.createElement("p");
    body.className = "source-body";
    body.textContent = (s.content || "").trim();

    item.append(head, body);
    box.appendChild(item);
  });

  wrap.appendChild(box);
}

function showError(wrap, message) {
  // 若仍在「思考中…」占位阶段，清掉占位文本。
  const answer = wrap.querySelector(".msg-answer");
  if (answer && answer.textContent === "思考中…") {
    answer.textContent = "";
  }
  const err = document.createElement("p");
  err.className = "msg-error";
  err.textContent = message;
  wrap.appendChild(err);
  scrollToBottom();
}

// ---- SSE 单条事件解析：event: X + data: {...} ----
function parseEvent(raw, onEvent) {
  let name = "message";
  let dataStr = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      name = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataStr += line.slice("data:".length).trim();
    }
  }
  if (!dataStr) return;
  let payload;
  try {
    payload = JSON.parse(dataStr);
  } catch (e) {
    return;
  }
  onEvent(name, payload);
}

async function send(question) {
  question = (question || textarea.value).trim();
  if (!question || streaming) return;

  appendUserMessage(question);
  const ai = appendAiMessage();
  clearInput();
  setStreaming(true);

  try {
    const resp = await fetch(`${API_BASE}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question }),
    });

    if (!resp.ok) {
      let detail = "请求失败，请稍后重试";
      try {
        const j = await resp.json();
        detail = j.detail || detail;
      } catch (e) {}
      throw new Error(detail);
    }
    if (!resp.body) throw new Error("响应无内容");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let firstContent = true;

    const onEvent = (name, payload) => {
      if (name === "content") {
        const text = payload.text || "";
        if (firstContent) {
          ai.answer.textContent = "";
          firstContent = false;
        }
        ai.answer.appendChild(document.createTextNode(text));
        scrollToBottom();
      } else if (name === "sources") {
        renderSources(ai.wrap, payload);
        scrollToBottom();
      } else if (name === "error") {
        showError(ai.wrap, payload.message || "AI 回复生成失败，请稍后重试");
      }
      // retrieval / done 无需渲染
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        parseEvent(raw, onEvent);
      }
    }

    if (firstContent) {
      showError(ai.wrap, "AI 未返回内容，请稍后重试");
    }
  } catch (err) {
    showError(ai.wrap, err.message || "连接后端失败，请确认服务已启动");
  } finally {
    setStreaming(false);
  }
}

// ---- 事件绑定 ----
sendBtn.addEventListener("click", () => send());
textarea.addEventListener("input", updateCount);
textarea.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

document.querySelectorAll(".preset").forEach((btn) => {
  btn.addEventListener("click", () => send(btn.textContent));
});

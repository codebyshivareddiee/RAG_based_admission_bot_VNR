/**
 * VNRVJIET Admissions Chatbot – Widget JavaScript
 * =================================================
 * Handles: toggle, send/receive, typing indicator,
 *          session management, markdown rendering,
 *          quick replies, timestamps.
 */

(function () {
  "use strict";

  // ── Configuration ────────────────────────────────────────────
  const API_BASE = window.CHATBOT_API_BASE || "";
  const COLLEGE = "VNRVJIET";

  // ── DOM References ───────────────────────────────────────────
  const toggleBtn = document.getElementById("chat-toggle");
  const container = document.getElementById("chat-container");
  const closeBtn = document.getElementById("chat-close");
  const messagesEl = document.getElementById("chat-messages");
  const inputEl = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");
  let typingEl = null;

  // ── State ────────────────────────────────────────────────────
  let isOpen = false;
  let isSending = false;
  let sessionId = sessionStorage.getItem("chatbot_session") || generateId();
  sessionStorage.setItem("chatbot_session", sessionId);

  // ── Helpers ──────────────────────────────────────────────────
  function generateId() {
    return "s_" + Math.random().toString(36).substring(2, 10);
  }

  function timestamp() {
    return new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  /** Minimal Markdown → HTML (headings, bold, italic, lists, line breaks) */
  function renderMarkdown(text) {
    let html = text
      // Headings: ### h3, ## h2, # h1 (must be at line start)
      .replace(/^###\s+(.+)$/gm, "<strong style='font-size:1.05em;display:block;margin:8px 0 4px;'>$1</strong>")
      .replace(/^##\s+(.+)$/gm, "<strong style='font-size:1.1em;display:block;margin:8px 0 4px;'>$1</strong>")
      .replace(/^#\s+(.+)$/gm, "<strong style='font-size:1.15em;display:block;margin:8px 0 4px;'>$1</strong>")
      // Bold **text**
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      // Italic *text*
      .replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, "<em>$1</em>")
      // Inline code `text`
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      // Unordered list items
      .replace(/^[\s]*[-•]\s+(.+)$/gm, "<li>$1</li>")
      // Ordered list items
      .replace(/^[\s]*\d+\.\s+(.+)$/gm, "<li>$1</li>")
      // Line breaks
      .replace(/\n/g, "<br>");

    // Wrap consecutive <li> in <ul>
    html = html.replace(
      /(<li>.*?<\/li>(?:<br>)?)+/g,
      (match) => "<ul>" + match.replace(/<br>/g, "") + "</ul>"
    );

    return html;
  }

  // ── UI Functions ─────────────────────────────────────────────

  function toggleChat() {
    isOpen = !isOpen;
    container.classList.toggle("visible", isOpen);
    toggleBtn.classList.toggle("open", isOpen);

    if (isOpen) {
      inputEl.focus();
      // Show welcome if first time
      if (messagesEl.children.length === 0) {
        showWelcome();
      }
    }
  }

  function showWelcome() {
    addBotMessage(
      `Hello! 👋 Welcome to the **${COLLEGE}** admissions assistant.\n\n` +
        "I can help you with:\n" +
        "• Admission process & eligibility\n" +
        "• Branch-wise cutoff ranks\n" +
        "• Required documents\n" +
        "• Fee structure & scholarships\n\n" +
        "How can I assist you today?"
    );

    // Quick reply chips
    addQuickReplies([
      "What is the admission process?",
      "CSE cutoff for OC category?",
      "Documents required?",
    ]);
  }

  function addMessage(text, sender) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${sender}`;

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    if (sender === "bot") {
      bubble.innerHTML = renderMarkdown(text);
    } else {
      bubble.textContent = text;
    }

    const ts = document.createElement("span");
    ts.className = "timestamp";
    ts.textContent = timestamp();
    bubble.appendChild(ts);

    msgDiv.appendChild(bubble);
    messagesEl.appendChild(msgDiv);
    scrollToBottom();
  }

  function addBotMessage(text) {
    addMessage(text, "bot");
  }

  function addUserMessage(text) {
    addMessage(text, "user");
  }

  function addQuickReplies(options) {
    const wrapper = document.createElement("div");
    wrapper.className = "message bot";

    const qr = document.createElement("div");
    qr.className = "quick-replies";

    options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.textContent = opt;
      btn.addEventListener("click", () => {
        wrapper.remove(); // remove chips after click
        sendMessage(opt);
      });
      qr.appendChild(btn);
    });

    wrapper.appendChild(qr);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
  }

  function showTyping() {
    if (typingEl) return; // already showing
    typingEl = document.createElement("div");
    typingEl.id = "typing-indicator";
    typingEl.className = "typing-indicator active";
    typingEl.innerHTML =
      '<div class="bubble"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';
    messagesEl.appendChild(typingEl);
    scrollToBottom();
  }

  function hideTyping() {
    if (typingEl) {
      typingEl.remove();
      typingEl = null;
    }
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  }

  // ── API Communication ────────────────────────────────────────

  async function sendMessage(text) {
    if (!text || !text.trim() || isSending) return;

    const userText = text.trim();
    addUserMessage(userText);
    inputEl.value = "";
    inputEl.disabled = true;
    sendBtn.disabled = true;
    isSending = true;

    showTyping();

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userText,
          session_id: sessionId,
        }),
      });

      if (response.status === 429) {
        hideTyping();
        addBotMessage(
          "You're sending messages too quickly. Please wait a moment and try again."
        );
        return;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      hideTyping();

      sessionId = data.session_id || sessionId;
      sessionStorage.setItem("chatbot_session", sessionId);

      addBotMessage(data.reply);

      // Source citations
      if (data.sources && data.sources.length > 0) {
        const srcText =
          "📄 *Sources: " + data.sources.join(", ") + "*";
        // Small muted source line (append to last bot bubble)
        const bubbles = messagesEl.querySelectorAll(".message.bot .bubble");
        if (bubbles.length > 0) {
          const last = bubbles[bubbles.length - 1];
          const srcSpan = document.createElement("div");
          srcSpan.style.cssText =
            "font-size:10px;color:#888;margin-top:6px;font-style:italic;";
          srcSpan.textContent = "📄 Sources: " + data.sources.join(", ");
          last.appendChild(srcSpan);
        }
      }
    } catch (err) {
      hideTyping();
      console.error("Chat error:", err);
      addBotMessage(
        "Sorry, I'm having trouble connecting right now. Please try again in a moment."
      );
    } finally {
      isSending = false;
      inputEl.disabled = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  // ── Event Listeners ──────────────────────────────────────────

  toggleBtn.addEventListener("click", toggleChat);
  closeBtn.addEventListener("click", toggleChat);

  sendBtn.addEventListener("click", () => {
    sendMessage(inputEl.value);
  });

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(inputEl.value);
    }
  });

  // ── Accessibility ────────────────────────────────────────────
  toggleBtn.setAttribute("aria-label", "Open chat");
  closeBtn.setAttribute("aria-label", "Close chat");
})();

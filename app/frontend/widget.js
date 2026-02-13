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
  const inputArea = document.getElementById("chat-input-area");
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
      // Show welcome if first time
      if (messagesEl.children.length === 0) {
        showWelcome();
      }
      // Only focus input if it's visible
      if (inputArea.style.display !== "none") {
        inputEl.focus();
      }
    }
  }

  // ── Category definitions with follow-up questions ──────────
  const CATEGORIES = {
    "Admission Process & Eligibility": [
      "What is the admission process?",
      "Am I eligible for admission?",
      "What exams are accepted?",
      "What is the selection criteria?",
    ],
    "Branch-wise Cutoff Ranks": [
      "CSE cutoff for OC category?",
      "ECE cutoff for BC-B category?",
      "What was last year's closing rank?",
      "Cutoff for management quota?",
    ],
    "Required Documents": [
      "Documents required for admission?",
      "Is migration certificate needed?",
      "Documents for fee payment?",
      "What ID proofs are required?",
    ],
    "Fee Structure & Scholarships": [
      "What is the fee structure?",
      "Are there any scholarships?",
      "Is fee payment in installments?",
      "Scholarship for SC/ST students?",
    ],
    "Others": [
      "Hostel & accommodation details?",
      "Placement & internship info?",
      "Campus facilities & labs?",
      "NRI / Management quota process?",
      "Talk to admission department",
    ],
  };

  function showWelcome() {
    addBotMessage(
      `Hello! 👋 Welcome to the **${COLLEGE}** admissions assistant.\n\n` +
        "I can help you with the following topics. Please select one:"
    );

    // Show category buttons + Others
    addCategoryButtons();
  }

  /** Render main category buttons + "Others" */
  function addCategoryButtons() {
    const wrapper = document.createElement("div");
    wrapper.className = "message bot";

    const grid = document.createElement("div");
    grid.className = "category-buttons";

    const icons = [
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5"/></svg>',
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>',
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 6v2m0 8v2"/></svg>',
    ];
    // Only show the first 4 categories as grid buttons (not "Others")
    const cats = Object.keys(CATEGORIES).filter(c => c !== "Others");

    cats.forEach((cat, i) => {
      const btn = document.createElement("button");
      btn.className = "category-btn";
      btn.innerHTML = `<span class="cat-icon">${icons[i]}</span><span class="cat-label">${cat}</span>`;
      btn.addEventListener("click", () => {
        wrapper.remove();
        addUserMessage(cat);
        addBotMessage(`Here are some questions about **${cat}**. Pick one or type your own:`);
        showInputArea();
        addFollowUpButtons(CATEGORIES[cat], cat);
      });
      grid.appendChild(btn);
    });

    // "Others" button – shows follow-up options + open typing
    const othersBtn = document.createElement("button");
    othersBtn.className = "category-btn others-btn";
    othersBtn.innerHTML = `<span class="cat-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg></span><span class="cat-label">Others</span>`;
    othersBtn.addEventListener("click", () => {
      wrapper.remove();
      addUserMessage("Others");
      addBotMessage("Here are some common topics, or feel free to type your own question:");
      showInputArea();
      addFollowUpButtons(CATEGORIES["Others"], "Others");
    });
    grid.appendChild(othersBtn);

    wrapper.appendChild(grid);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
  }

  /** Render follow-up question buttons for a category */
  function addFollowUpButtons(questions, category) {
    const wrapper = document.createElement("div");
    wrapper.className = "message bot";

    const qr = document.createElement("div");
    qr.className = "followup-buttons";

    questions.forEach((q) => {
      const btn = document.createElement("button");
      btn.textContent = q;
      btn.addEventListener("click", () => {
        wrapper.remove();
        sendMessage(q);
      });
      qr.appendChild(btn);
    });

    // "Type my own" option
    const customBtn = document.createElement("button");
    customBtn.className = "custom-btn";
    customBtn.textContent = "✏️ Type my own question";
    customBtn.addEventListener("click", () => {
      wrapper.remove();
      addBotMessage(`Sure, type your question about **${category}** below:`);
      inputEl.focus();
    });
    qr.appendChild(customBtn);

    wrapper.appendChild(qr);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
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

  /** Show the input area (hidden until user picks a category) */
  function showInputArea() {
    inputArea.style.display = "";
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

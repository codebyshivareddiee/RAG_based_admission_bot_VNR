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
  const homeBtn = document.getElementById("home-btn");
  const messagesEl = document.getElementById("chat-messages");
  const inputEl = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");
  const micBtn = document.getElementById("mic-btn");
  const inputArea = document.getElementById("chat-input-area");
  const welcomePopup = document.getElementById("welcome-popup");
  const popupClose = document.getElementById("popup-close");
  let typingEl = null;

  // ── State ────────────────────────────────────────────────────
  let isOpen = false;
  let isSending = false;
  let sessionId = sessionStorage.getItem("chatbot_session") || generateId();
  sessionStorage.setItem("chatbot_session", sessionId);
  
  // TTS state
  let currentSpeech = null;
  let isSpeaking = false;
  
  // STT state
  let recognition = null;
  let isListening = false;
  
  // Language preference - check if user has explicitly selected a language
  let currentLanguage = sessionStorage.getItem("chatbot_language") || "en";
  let languageSelected = sessionStorage.getItem("chatbot_language_selected") === "true";
  
  // Debug logging
  console.log("Chatbot initialized:", {
    sessionId,
    currentLanguage,
    languageSelected,
    version: "v20-multilingual"
  });
  
  // Chat history is preserved in this session for context-aware responses
  // The backend automatically uses conversation history for better answers

  // ── Language Support ─────────────────────────────────────────
  const SUPPORTED_LANGUAGES = {
    en: { name: "English", native: "English", flag: "🇬🇧" },
    hi: { name: "Hindi", native: "हिन्दी", flag: "🇮🇳" },
    te: { name: "Telugu", native: "తెలుగు", flag: "🇮🇳" },
    ta: { name: "Tamil", native: "தமிழ்", flag: "🇮🇳" },
    mr: { name: "Marathi", native: "मराठी", flag: "🇮🇳" },
    kn: { name: "Kannada", native: "ಕನ್ನಡ", flag: "🇮🇳" },
  };

  const TRANSLATIONS = {
    welcome_title: {
      en: "Hello! 👋 Welcome to the **VNRVJIET** assistant.",
      hi: "नमस्ते! 👋 **VNRVJIET** सहायक में आपका स्वागत है।",
      te: "నమస్కారం! 👋 **VNRVJIET** సహాయకునికి స్వాగతం।",
      ta: "வணக்கம்! 👋 **VNRVJIET** உதவியாளருக்கு வரவேற்கிறோம்.",
      mr: "नमस्कार! 👋 **VNRVJIET** सहाय्यकांमध्ये आपले स्वागत आहे.",
      kn: "ನಮಸ್ಕಾರ! 👋 **VNRVJIET** ಸಹಾಯಕನಿಗೆ ಸ್ವಾಗತ.",
    },
    welcome_select_topic: {
      en: "I can help you with the following topics. Please select one:",
      hi: "मैं निम्नलिखित विषयों में आपकी मदद कर सकता/सकती हूं। कृपया एक चुनें:",
      te: "నేను ఈ క్రింది అంశాలలో మీకు సహాయం చేయగలను. దయచేసి ఒకదాన్ని ఎంచుకోండి:",
      ta: "நான் பின்வரும் தலைப்புகளில் உங்களுக்கு உதவ முடியும். தயவுசெய்து ஒன்றைத் தேர்ந்தெடுக்கவும்:",
      mr: "मी खालील विषयांमध्ये तुमची मदत करू शकतो. कृपया एक निवडा:",
      kn: "ನಾನು ಈ ಕೆಳಗಿನ ವಿಷಯಗಳಲ್ಲಿ ನಿಮಗೆ ಸಹಾಯ ಮಾಡಬಹುದು. ದಯವಿಟ್ಟು ಒಂದನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
    },
    language_prompt: {
      en: "Please select your preferred language:",
      hi: "कृपया अपनी पसंदीदा भाषा चुनें:",
      te: "దయచేసి మీ ఇష్ట భాషను ఎంచుకోండి:",
      ta: "உங்களுக்கு விருப்பமான மொழியைத் தேர்ந்தெடுக்கவும்:",
      mr: "कृपया तुमची पसंतीची भाषा निवडा:",
      kn: "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಆದ್ಯತೆಯ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
    },
    category_admission: {
      en: "Admission Process & Eligibility",
      hi: "प्रवेश प्रक्रिया और पात्रता",
      te: "ప్రవేశ ప్రక్రియ & అర్హత",
      ta: "சேர்க்கை செயல்முறை & தகுதி",
      mr: "प्रवेश प्रक्रिया आणि पात्रता",
      kn: "ಪ್ರವೇಶ ಪ್ರಕ್ರಿಯೆ ಮತ್ತು ಅರ್ಹತೆ",
    },
    category_cutoff: {
      en: "Branch-wise Cutoff Ranks",
      hi: "शाखा-वार कटऑफ रैंक",
      te: "బ్రాంచ్-వారీ కటాఫ్ ర్యాంక్‌లు",
      ta: "கிளை வாரியான கட்ஆஃப் தரவரிசை",
      mr: "शाखा-निहाय कटऑफ रॅंक",
      kn: "ಶಾಖೆಯ ಪ್ರಕಾರ ಕಟ್‌ಆಫ್ ಶ್ರೇಣಿಗಳು",
    },
    category_documents: {
      en: "Required Documents",
      hi: "आवश्यक दस्तावेज",
      te: "అవసరమైన పత్రాలు",
      ta: "தேவையான ஆவணங்கள்",
      mr: "आवश्यक कागदपत्रे",
      kn: "ಅಗತ್ಯ ದಾಖಲೆಗಳು",
    },
    category_fees: {
      en: "Fee Structure & Scholarships",
      hi: "शुल्क संरचना और छात्रवृत्ति",
      te: "ఫీజు నిర్మాణం & స్కాలర్‌షిప్‌లు",
      ta: "கட்டணம் & உதவித்தொகை",
      mr: "फी रचना आणि शिष्यवृत्ती",
      kn: "ಶುಲ್ಕ ರಚನೆ ಮತ್ತು ವಿದ್ಯಾರ್ಥಿವೇತನ",
    },
    category_others: {
      en: "Others",
      hi: "अन्य",
      te: "ఇతరములు",
      ta: "மற்றவை",
      mr: "इतर",
      kn: "ಇತರೆ",
    },
    input_placeholder: {
      en: "Ask about admissions...",
      hi: "प्रवेश के बारे में पूछें...",
      te: "ప్రవేశాల గురించి అడగండి...",
      ta: "சேர்க்கை பற்றி கேளுங்கள்...",
      mr: "प्रवेशाबद्दल विचारा...",
      kn: "ಪ್ರವೇಶದ ಬಗ್ಗೆ ಕೇಳಿ...",
    },
    error_connection: {
      en: "Sorry, I'm having trouble connecting right now. Please try again in a moment.",
      hi: "क्षमा करें, मुझे अभी कनेक्ट करने में समस्या हो रही है। कृपया कुछ देर बाद पुनः प्रयास करें।",
      te: "క్షమించండి, నాకు ఇప్పుడు కనెక్ట్ చేయడంలో సమస్య ఉంది. దయచేసి కొద్దిసేపటి తర్వాత మళ్లీ ప్రయత్నించండి।",
      ta: "மன்னிக்கவும், இப்போது இணைப்பதில் சிக்கல் உள்ளது. சிறிது நேரம் கழித்து மீண்டும் முயற்சிக்கவும்.",
      mr: "क्षमस्व, मला आत्ता कनेक्ट होण्यात समस्या येत आहे. कृपया काही वेळाने पुन्हा प्रयत्न करा.",
      kn: "ಕ್ಷಮಿಸಿ, ನನಗೆ ಈಗ ಸಂಪರ್ಕ ಸಾಧಿಸುವಲ್ಲಿ ತೊಂದರೆ ಇದೆ. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
    },
    rate_limit: {
      en: "You're sending messages too quickly. Please wait a moment and try again.",
      hi: "आप बहुत जल्दी संदेश भेज रहे हैं। कृपया प्रतीक्षा करें और पुनः प्रयास करें।",
      te: "మీరు చాలా త్వరగా సందేశాలు పంపుతున్నారు. దయచేసి కాసేపు వేచి ఉండి మళ్లీ ప్రయత్నించండి।",
      ta: "நீங்கள் மிக விரைவாக செய்திகளை அனுப்புகிறீர்கள். சிறிது நேரம் காத்திருந்து மீண்டும் முயற்சிக்கவும்.",
      mr: "तुम्ही खूप वेगाने संदेश पाठवत आहात. कृपया थांबा आणि पुन्हा प्रयत्न करा.",
      kn: "ನೀವು ತುಂಬಾ ವೇಗವಾಗಿ ಸಂದೇಶಗಳನ್ನು ಕಳುಹಿಸುತ್ತಿದ್ದೀರಿ. ದಯವಿಟ್ಟು ಕಾಯಿರಿ ಮತ್ತು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
    },
    change_language: {
      en: "🌐 Change Language",
      hi: "🌐 भाषा बदलें",
      te: "🌐 భాష మార్చండి",
      ta: "🌐 மொழியை மாற்றவும்",
      mr: "🌐 भाषा बदला",
      kn: "🌐 ಭಾಷೆಯನ್ನು ಬದಲಿಸಿ",
    },
    // ── Admission guided-flow translations ──────────────────────
    admission_sub_prompt: {
      en: "Would you like to know about the **Admission Process** or **Eligibility Criteria**?",
      hi: "क्या आप **प्रवेश प्रक्रिया** या **पात्रता मानदंड** के बारे में जानना चाहते हैं?",
      te: "మీరు **ప్రవేశ ప్రక్రియ** లేదా **అర్హత ప్రమాణాల** గురించి తెలుసుకోవాలనుకుంటున్నారా?",
      ta: "**சேர்க்கை செயல்முறை** அல்லது **தகுதி அளவுகோல்கள்** பற்றி தெரிந்துகொள்ள விரும்புகிறீர்களா?",
      mr: "तुम्हाला **प्रवेश प्रक्रिया** किंवा **पात्रता निकष** बद्दल जाणून घ्यायचे आहे का?",
      kn: "ನೀವು **ಪ್ರವೇಶ ಪ್ರಕ್ರಿಯೆ** ಅಥವಾ **ಅರ್ಹತೆ ಮಾನದಂಡಗಳ** ಬಗ್ಗೆ ತಿಳಿದುಕೊಳ್ಳಲು ಬಯಸುತ್ತೀರಾ?",
    },
    admission_type_process: {
      en: "Admission Process",
      hi: "प्रवेश प्रक्रिया",
      te: "ప్రవేశ ప్రక్రియ",
      ta: "சேர்க்கை செயல்முறை",
      mr: "प्रवेश प्रक्रिया",
      kn: "ಪ್ರವೇಶ ಪ್ರಕ್ರಿಯೆ",
    },
    admission_type_eligibility: {
      en: "Eligibility Criteria",
      hi: "पात्रता मानदंड",
      te: "అర్హత ప్రమాణాలు",
      ta: "தகுதி அளவுகோல்கள்",
      mr: "पात्रता निकष",
      kn: "ಅರ್ಹತೆ ಮಾನದಂಡಗಳು",
    },
    admission_program_prompt: {
      en: "Which program are you interested in?",
      hi: "आप किस कार्यक्रम में रुचि रखते हैं?",
      te: "మీకు ఏ ప్రోగ్రామ్‌పై ఆసక్తి ఉంది?",
      ta: "நீங்கள் எந்த திட்டத்தில் ஆர்வமாக உள்ளீர்கள்?",
      mr: "तुम्हाला कोणत्या कार्यक्रमात रस आहे?",
      kn: "ನೀವು ಯಾವ ಕಾರ್ಯಕ್ರಮದಲ್ಲಿ ಆಸಕ್ತಿ ಹೊಂದಿದ್ದೀರಿ?",
    },
    admission_query_process: {
      en: "What is the {program} admission process at VNRVJIET?",
      hi: "VNRVJIET में {program} प्रवेश प्रक्रिया क्या है?",
      te: "VNRVJIET లో {program} ప్రవేశ ప్రక్రియ ఏమిటి?",
      ta: "VNRVJIET இல் {program} சேர்க்கை செயல்முறை என்ன?",
      mr: "VNRVJIET मध्ये {program} प्रवेश प्रक्रिया काय आहे?",
      kn: "VNRVJIET ನಲ್ಲಿ {program} ಪ್ರವೇಶ ಪ್ರಕ್ರಿಯೆ ಏನು?",
    },
    admission_query_eligibility: {
      en: "What are the {program} eligibility criteria at VNRVJIET?",
      hi: "VNRVJIET में {program} पात्रता मानदंड क्या हैं?",
      te: "VNRVJIET లో {program} అర్హత ప్రమాణాలు ఏమిటి?",
      ta: "VNRVJIET இல் {program} தகுதி அளவுகோல்கள் என்ன?",
      mr: "VNRVJIET मध्ये {program} पात्रता निकष काय आहेत?",
      kn: "VNRVJIET ನಲ್ಲಿ {program} ಅರ್ಹತೆ ಮಾನದಂಡಗಳು ಯಾವುವು?",
    },
  };

  function t(key) {
    return TRANSLATIONS[key]?.[currentLanguage] || TRANSLATIONS[key]?.en || key;
  }

  function setLanguage(lang) {
    console.log("Setting language to:", lang);
    if (SUPPORTED_LANGUAGES[lang]) {
      currentLanguage = lang;
      sessionStorage.setItem("chatbot_language", lang);
      sessionStorage.setItem("chatbot_language_selected", "true");
      languageSelected = true;
      
      // Update input placeholder
      if (inputEl) {
        inputEl.placeholder = t("input_placeholder");
      }
      
      console.log("Language set successfully:", lang);
    } else {
      console.error("Unsupported language:", lang);
    }
  }
  
  // Chat history is preserved in this session for context-aware responses
  // The backend automatically uses conversation history for better answers

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

  /** Minimal Markdown → HTML (headings, bold, italic, lists, line breaks, links) */
  function renderMarkdown(text) {
    // ── Step 1: wrap field lines (**Label:** value) in block divs LINE BY LINE
    // Using split/map is more reliable than a /^$/gm regex (avoids CRLF edge cases).
    text = text
      .split("\n")
      .map(function (line) {
        // Match lines like **Branch:** CSE  or  **First Rank (Opening):** 1,714
        // The colon sits INSIDE the closing **: **Label:**
        if (/^\*\*[A-Za-z][^*]*:\*\*\s*.+/.test(line)) {
          return '<div class="cutoff-field" style="display:block!important;margin:3px 0;clear:both;width:100%;">' + line + "</div>";
        }
        return line;
      })
      .join("\n");

    let html = text
      // Headings: ### h3, ## h2, # h1
      .replace(/^###\s+(.+)$/gm, "<strong style='font-size:1.05em;display:block;margin:8px 0 4px;'>$1</strong>")
      .replace(/^##\s+(.+)$/gm, "<strong style='font-size:1.1em;display:block;margin:8px 0 4px;'>$1</strong>")
      .replace(/^#\s+(.+)$/gm, "<strong style='font-size:1.15em;display:block;margin:8px 0 4px;'>$1</strong>")
      // Bold **text**
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      // Italic *text*
      .replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, "<em>$1</em>")
      // Inline code `text`
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      // Markdown links: [text](url)
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" style="color:#0066cc;text-decoration:underline;">$1</a>')
      // Auto-detect plain URLs (http:// or https://)
      .replace(/(^|[^"'\(>])((https?:\/\/)[^\s<]+[^\s<.,;!?'"\)])/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer" style="color:#0066cc;text-decoration:underline;">$2</a>')
      // Unordered list items
      .replace(/^[\s]*[-•]\s+(.+)$/gm, "<li>$1</li>")
      // Ordered list items
      .replace(/^[\s]*\d+\.\s+(.+)$/gm, "<li>$1</li>")
      // Line breaks
      .replace(/\n/g, "<br>")
      // Remove redundant <br> immediately after block divs (prevents double spacing)
      .replace(/<\/div><br>/g, "</div>");

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
    } else {
      // Stop speech when closing chat
      stopSpeech();
    }
  }

  /** Open chat without toggling (for auto-popup) */
  function openChat() {
    if (!isOpen) {
      isOpen = true;
      container.classList.add("visible");
      toggleBtn.classList.add("open");
    }
  }

  /** Close chat */
  function closeChat() {
    if (isOpen) {
      isOpen = false;
      container.classList.remove("visible");
      toggleBtn.classList.remove("open");
      // Stop speech when closing
      stopSpeech();
    }
  }

  // ── Category definitions with follow-up questions ──────────
  // Category names will be translated dynamically
  const CATEGORY_KEYS = {
    "admission": "category_admission",
    "cutoff": "category_cutoff",
    "documents": "category_documents",
    "fees": "category_fees",
    "others": "category_others",
  };
  
  const CATEGORIES_EN = {
    "Admission Process & Eligibility": [
      "What is the admission process?",
      "Am I eligible for admission?",
      "What exams are accepted?",
      "What is the selection criteria?",
    ],
    "Branch-wise Cutoff Ranks": [
      "Show cutoff trend analysis for a branch",
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
      "Management quota process?(NRI/NRI Sponsored or Category B)",
      "Talk to admission department",
    ],
  };
  
  function getTranslatedCategories() {
    return [
      t("category_admission"),
      t("category_cutoff"),
      t("category_documents"),
      t("category_fees"),
    ];
  }

  function showWelcome() {
    console.log("showWelcome called, languageSelected:", languageSelected);
    
    // Show language selector if not yet selected
    if (!languageSelected) {
      console.log("Showing language selector");
      showLanguageSelector();
      return;
    }
    
    console.log("Showing welcome in language:", currentLanguage);
    addBotMessage(
      t("welcome_title") + "\n\n" + t("welcome_select_topic")
    );

    // Show category buttons + Others
    addCategoryButtons();
    
    // Add language change button at the bottom
    addLanguageChangeButton();
    
    // Hide input area when showing welcome buttons
    inputArea.style.display = "none";
  }

  /** Show language selector on first interaction */
  function showLanguageSelector() {
    console.log("showLanguageSelector called");
    addBotMessage(t("language_prompt"));
    
    // Hide input area when showing language selector
    inputArea.style.display = "none";
    
    const wrapper = document.createElement("div");
    wrapper.className = "message bot";

    const grid = document.createElement("div");
    grid.className = "language-buttons";
    grid.style.cssText = "display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; max-width: 300px;";

    Object.entries(SUPPORTED_LANGUAGES).forEach(([code, info]) => {
      const btn = document.createElement("button");
      btn.className = "language-btn";
      btn.style.cssText = (
        "padding: 12px; border: 2px solid #e0e0e0; background: white; " +
        "border-radius: 8px; cursor: pointer; transition: all 0.2s; " +
        "font-size: 14px; display: flex; align-items: center; gap: 8px; " +
        "justify-content: center;"
      );
      btn.innerHTML = `<span style="font-size: 20px;">${info.flag}</span><span style="font-weight: 500;">${info.native}</span>`;
      
      btn.addEventListener("mouseover", () => {
        btn.style.borderColor = "#1976d2";
        btn.style.backgroundColor = "#f0f7ff";
      });
      btn.addEventListener("mouseout", () => {
        btn.style.borderColor = "#e0e0e0";
        btn.style.backgroundColor = "white";
      });
      
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        console.log("Language selected:", code, info.native);
        wrapper.remove();
        setLanguage(code);
        addUserMessage(info.native);
        showWelcome();  // Show welcome in selected language
        // Keep input visible for continuous interaction
        showInputArea();
      });
      grid.appendChild(btn);
    });

    wrapper.appendChild(grid);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
    
    console.log("Language selector displayed with", Object.keys(SUPPORTED_LANGUAGES).length, "languages");
  }

  /** Add language change button to allow users to switch language */
  function addLanguageChangeButton() {
    const wrapper = document.createElement("div");
    wrapper.className = "message bot";
    wrapper.style.marginTop = "10px";

    const btn = document.createElement("button");
    btn.className = "language-change-btn";
    btn.textContent = t("change_language");
    btn.style.cssText = (
      "padding: 8px 16px; background: #f5f5f5; border: 1px solid #ddd; " +
      "border-radius: 20px; cursor: pointer; font-size: 12px; " +
      "color: #555; transition: all 0.2s;"
    );
    
    btn.addEventListener("mouseover", () => {
      btn.style.backgroundColor = "#e0e0e0";
    });
    btn.addEventListener("mouseout", () => {
      btn.style.backgroundColor = "#f5f5f5";
    });
    
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      languageSelected = false;  // Reset language selection
      sessionStorage.removeItem("chatbot_language_selected");
      messagesEl.innerHTML = "";  // Clear messages
      showWelcome();  // This will show language selector
    });

    wrapper.appendChild(btn);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
  }

  /** Return to home screen while preserving chat history */
  // ── Text-to-Speech Functions ─────────────────────────────────
  
  /**
   * Create TTS button for bot messages
   */
  function createTTSButton(text) {
    const ttsBtn = document.createElement("button");
    ttsBtn.className = "tts-button";
    ttsBtn.setAttribute("aria-label", "Listen to response");
    ttsBtn.innerHTML = '<span class="tts-icon">🔊</span> Listen';
    
    // Check if browser supports Speech Synthesis
    if (!('speechSynthesis' in window)) {
      ttsBtn.disabled = true;
      ttsBtn.title = "Text-to-speech not supported in your browser";
      return ttsBtn;
    }
    
    // Store reference to the text for this button
    ttsBtn.dataset.ttsText = text;
    
    ttsBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      
      // Prevent double-clicking
      if (ttsBtn.disabled) return;
      
      // Check if this button is currently playing
      const isThisButtonPlaying = ttsBtn.classList.contains("playing");
      
      if (isThisButtonPlaying) {
        // Stop current speech
        stopSpeech();
      } else {
        // Stop any other speech first
        stopSpeech();
        
        // Small delay to ensure previous speech is fully stopped
        setTimeout(() => {
          // Start new speech
          speakText(text, ttsBtn);
        }, 100);
      }
    });
    
    return ttsBtn;
  }
  
  /**
   * Convert text to speech with improved error handling and dynamic language detection
   */
  function speakText(text, buttonElement) {
    try {
      // Ensure speechSynthesis is available
      if (!window.speechSynthesis) {
        console.error("Speech synthesis not available");
        return;
      }
      
      // Cancel any existing speech first (safety check)
      if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
        window.speechSynthesis.cancel();
      }
      
      // Clean markdown and HTML from text
      let cleanText = text
        .replace(/<[^>]*>/g, '') // Remove HTML tags
        .replace(/\*\*/g, '') // Remove bold markdown
        .replace(/\*/g, '') // Remove italic markdown
        .replace(/`/g, '') // Remove code markdown
        .replace(/#{1,6}\s/g, '') // Remove heading markers
        .replace(/\n+/g, '. ') // Replace line breaks with pauses
        .trim();
      
      // Validate text
      if (!cleanText || cleanText.length === 0) {
        console.warn("No text to speak");
        return;
      }
      
      // Limit text length to prevent issues (max 5000 chars)
      if (cleanText.length > 5000) {
        cleanText = cleanText.substring(0, 5000) + "...";
      }
      
      const utterance = new SpeechSynthesisUtterance(cleanText);
      
      // ALWAYS use the user's selected language (currentLanguage)
      // This is more reliable than auto-detection
      const langMap = {
        'en': 'en-US',
        'hi': 'hi-IN',
        'te': 'te-IN',
        'ta': 'ta-IN',
        'mr': 'mr-IN',
        'kn': 'kn-IN'
      };
      
      const targetLang = langMap[currentLanguage] || 'en-US';
      utterance.lang = targetLang;
      
      console.log("🔊 TTS Details:");
      console.log("  - Selected Language:", currentLanguage);
      console.log("  - Target Voice Lang:", targetLang);
      console.log("  - Text Preview:", cleanText.substring(0, 50) + "...");
      
      // Get available voices and try to use the best match
      const voices = window.speechSynthesis.getVoices();
      console.log("  - Available voices:", voices.length);
      
      // Find best matching voice for the language
      let matchingVoice = null;
      
      // First try: exact lang match (e.g., "te-IN")
      matchingVoice = voices.find(voice => voice.lang === targetLang);
      
      // Second try: language prefix match (e.g., "te")
      if (!matchingVoice) {
        const langPrefix = targetLang.split('-')[0];
        matchingVoice = voices.find(voice => voice.lang.startsWith(langPrefix));
      }
      
      // Third try: any voice with the language name
      if (!matchingVoice) {
        const langNames = {
          'te-IN': ['telugu', 'తెలుగు'],
          'hi-IN': ['hindi', 'हिन्दी'],
          'ta-IN': ['tamil', 'தமிழ்'],
          'kn-IN': ['kannada', 'ಕನ್ನಡ'],
          'mr-IN': ['marathi', 'मराठी'],
          'en-US': ['english']
        };
        
        const names = langNames[targetLang] || [];
        for (const name of names) {
          matchingVoice = voices.find(voice => 
            voice.name.toLowerCase().includes(name.toLowerCase()) ||
            voice.lang.toLowerCase().includes(name.toLowerCase())
          );
          if (matchingVoice) break;
        }
      }
      
      if (matchingVoice) {
        utterance.voice = matchingVoice;
        console.log("  - Using voice:", matchingVoice.name, "(" + matchingVoice.lang + ")");
      } else {
        console.warn("  - ⚠️ No matching voice found for", targetLang);
        console.warn("  - Available voice languages:", voices.map(v => v.lang).join(", "));
        console.warn("  - Will use default voice (may not be correct)");
      }
      
      // Speech settings
      utterance.rate = 0.9; // Slightly slower for clarity
      utterance.pitch = 1.0;
      utterance.volume = 1.0;
      
      // Event handlers with improved error handling
      utterance.onstart = function() {
        console.log("  - ✅ Speech started successfully");
        isSpeaking = true;
        if (buttonElement) {
          buttonElement.classList.add("playing");
          buttonElement.innerHTML = '<span class="tts-icon">⏸</span> Stop';
        }
      };
      
      utterance.onend = function() {
        console.log("  - ✅ Speech ended");
        resetSpeechState(buttonElement);
      };
      
      utterance.onerror = function(event) {
        console.error("  - ❌ Speech error:", event.error);
        
        // Handle specific errors
        if (event.error === 'interrupted') {
          console.log("  - Speech was interrupted (normal)");
        } else if (event.error === 'canceled') {
          console.log("  - Speech was canceled (normal)");
        } else if (event.error === 'not-allowed') {
          console.error("  - ❌ Speech not allowed - check permissions");
        } else if (event.error === 'language-unavailable') {
          console.error("  - ❌ Language voice not available:", targetLang);
          console.error("  - Install language pack or use different browser");
        } else {
          console.error("  - ❌ Unexpected error:", event.error);
        }
        
        resetSpeechState(buttonElement);
      };
      
      utterance.onpause = function() {
        console.log("  - Speech paused");
      };
      
      utterance.onresume = function() {
        console.log("  - Speech resumed");
      };
      
      // Store current speech reference
      currentSpeech = utterance;
      isSpeaking = true;
      
      // Try to speak with error handling
      try {
        window.speechSynthesis.speak(utterance);
        
        // Fallback: If speech doesn't start within 1 second, reset
        setTimeout(() => {
          if (isSpeaking && !window.speechSynthesis.speaking) {
            console.warn("  - ⚠️ Speech failed to start, resetting");
            resetSpeechState(buttonElement);
          }
        }, 1000);
        
      } catch (error) {
        console.error("  - ❌ Error calling speak():", error);
        resetSpeechState(buttonElement);
      }
      
    } catch (error) {
      console.error("❌ Error in speakText:", error);
      resetSpeechState(buttonElement);
    }
  }
  
  /**
   * Detect language from text content using Unicode ranges
   * NOTE: Currently not used - using currentLanguage instead for reliability
   */
  function detectLanguageFromText(text) {
    if (!text || text.length === 0) return null;
    
    // Get first 200 characters for detection (enough to determine language)
    const sample = text.substring(0, 200);
    
    // Count characters from different scripts
    let counts = {
      devanagari: 0,  // Hindi, Marathi
      telugu: 0,
      tamil: 0,
      kannada: 0,
      latin: 0        // English
    };
    
    for (let char of sample) {
      const code = char.charCodeAt(0);
      
      // Devanagari (Hindi, Marathi): U+0900 to U+097F
      if (code >= 0x0900 && code <= 0x097F) {
        counts.devanagari++;
      }
      // Telugu: U+0C00 to U+0C7F
      else if (code >= 0x0C00 && code <= 0x0C7F) {
        counts.telugu++;
      }
      // Tamil: U+0B80 to U+0BFF
      else if (code >= 0x0B80 && code <= 0x0BFF) {
        counts.tamil++;
      }
      // Kannada: U+0C80 to U+0CFF
      else if (code >= 0x0C80 && code <= 0x0CFF) {
        counts.kannada++;
      }
      // Latin (English): U+0041 to U+007A
      else if ((code >= 0x0041 && code <= 0x005A) || (code >= 0x0061 && code <= 0x007A)) {
        counts.latin++;
      }
    }
    
    // Determine dominant script
    const maxCount = Math.max(...Object.values(counts));
    
    // Need at least 20% of characters to be from a script to detect it
    const threshold = sample.length * 0.2;
    
    if (maxCount < threshold) {
      // Not enough script characters, use current language
      return currentLanguage;
    }
    
    // Find which script has the most characters
    if (counts.telugu === maxCount && counts.telugu >= threshold) {
      return 'te';
    } else if (counts.tamil === maxCount && counts.tamil >= threshold) {
      return 'ta';
    } else if (counts.kannada === maxCount && counts.kannada >= threshold) {
      return 'kn';
    } else if (counts.devanagari === maxCount && counts.devanagari >= threshold) {
      // Could be Hindi or Marathi - check current language preference
      if (currentLanguage === 'mr') {
        return 'mr';
      } else {
        return 'hi';
      }
    } else if (counts.latin === maxCount) {
      return 'en';
    }
    
    // Fallback to current language
    return currentLanguage;
  }
  
  /**
   * Reset speech state and button UI
   */
  function resetSpeechState(buttonElement) {
    isSpeaking = false;
    currentSpeech = null;
    
    if (buttonElement && buttonElement.classList) {
      buttonElement.classList.remove("playing");
      buttonElement.innerHTML = '<span class="tts-icon">🔊</span> Listen';
    }
    
    // Reset all TTS buttons as safety measure
    try {
      document.querySelectorAll('.tts-button.playing').forEach(btn => {
        btn.classList.remove('playing');
        btn.innerHTML = '<span class="tts-icon">🔊</span> Listen';
      });
    } catch (error) {
      console.error("Error resetting buttons:", error);
    }
  }
  
  /**
   * Stop any ongoing speech with improved reliability
   */
  function stopSpeech() {
    try {
      // Check if speechSynthesis exists
      if (!window.speechSynthesis) {
        return;
      }
      
      // Cancel any ongoing or pending speech
      if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
        window.speechSynthesis.cancel();
      }
      
      // Wait a moment for cancel to complete
      setTimeout(() => {
        // Double-check and cancel again if needed
        if (window.speechSynthesis.speaking) {
          window.speechSynthesis.cancel();
        }
        
        // Reset state
        resetSpeechState(null);
      }, 50);
      
    } catch (error) {
      console.error("Error stopping speech:", error);
      // Still try to reset state
      resetSpeechState(null);
    }
  }
  
  /**
   * Pause speech (for future use)
   */
  function pauseSpeech() {
    try {
      if (window.speechSynthesis && window.speechSynthesis.speaking) {
        window.speechSynthesis.pause();
      }
    } catch (error) {
      console.error("Error pausing speech:", error);
    }
  }
  
  /**
   * Resume speech (for future use)
   */
  function resumeSpeech() {
    try {
      if (window.speechSynthesis && window.speechSynthesis.paused) {
        window.speechSynthesis.resume();
      }
    } catch (error) {
      console.error("Error resuming speech:", error);
    }
  }
  
  // ── Speech-to-Text Functions ─────────────────────────────────
  
  /**
   * Initialize Speech Recognition
   */
  function initSpeechRecognition() {
    // Check browser support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    
    if (!SpeechRecognition) {
      console.warn("Speech Recognition not supported in this browser");
      if (micBtn) {
        micBtn.disabled = true;
        micBtn.title = "Speech recognition not supported in your browser";
      }
      return;
    }
    
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    
    // Set language based on current selection
    const langMap = {
      'en': 'en-US',
      'hi': 'hi-IN',
      'te': 'te-IN',
      'ta': 'ta-IN',
      'mr': 'mr-IN',
      'kn': 'kn-IN'
    };
    recognition.lang = langMap[currentLanguage] || 'en-US';
    
    // Event handlers for continuous listening with auto-stop
    recognition.onstart = function() {
      console.log("🎤 Continuous speech recognition started for language:", recognition.lang);
      updateListeningUI(true);
      resetAutoStopTimer();
    };
    
    recognition.onresult = function(event) {
      let finalTranscript = '';
      let interimTranscript = '';
      
      // Process all results
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += result[0].transcript;
        } else {
          interimTranscript += result[0].transcript;
        }
      }
      
      // Reset auto-stop timer when we get any speech activity
      if (finalTranscript || interimTranscript) {
        resetAutoStopTimer();
      }
      
      console.log("🎤 Speech detected (final):", finalTranscript);
      console.log("🎤 Speech detected (interim):", interimTranscript);
      
      // Update input field with results
      if (inputEl) {
        if (finalTranscript) {
          // Final result - append to existing text or replace
          const currentValue = inputEl.value.replace(/\s*$/, ''); // Remove trailing spaces
          const newValue = currentValue ? currentValue + ' ' + finalTranscript : finalTranscript;
          inputEl.value = newValue.trim();
          
          // Clear interim styling
          inputEl.style.fontStyle = '';
          inputEl.style.opacity = '';
          
          // Continue listening for more speech
          showListeningStatus("Listening... (say more or wait to stop)");
          
        } else if (interimTranscript) {
          // Show interim results with visual indication
          const currentValue = inputEl.value.replace(/\s*$/, ''); // Remove trailing spaces
          const displayValue = currentValue ? currentValue + ' ' + interimTranscript : interimTranscript;
          inputEl.value = displayValue;
          
          // Style interim text
          inputEl.style.fontStyle = 'italic';
          inputEl.style.opacity = '0.8';
          
          showListeningStatus("Listening...");
        }
      }
    };
    
    recognition.onerror = function(event) {
      console.error("🎤 Speech recognition error:", event.error);
      
      let errorMessage = "Speech recognition error";
      
      // Handle specific errors with user-friendly messages
      switch (event.error) {
        case 'no-speech':
          // Don't treat no-speech as error in continuous mode
          console.log("🎤 No speech detected (normal in continuous mode)");
          return; // Don't stop listening
        case 'audio-capture':
          errorMessage = "Microphone not available";
          break;
        case 'not-allowed':
          errorMessage = "Microphone permission denied";
          break;
        case 'network':
          errorMessage = "Network error. Check connection";
          break;
        case 'aborted':
          // Normal when user stops
          console.log("🎤 Recognition aborted (normal)");
          return;
        default:
          errorMessage = `Recognition error: ${event.error}`;
      }
      
      console.warn("🎤", errorMessage);
      showListeningStatus("Error: " + errorMessage);
      
      // Stop listening on real errors
      setTimeout(() => stopListening(), 2000);
    };
    
    recognition.onend = function() {
      console.log("🎤 Speech recognition ended");
      updateListeningUI(false);
      clearAutoStopTimer();
    };
  }
  
  /**
   * Start/Stop speech recognition with continuous listening and auto-stop
   */
  function toggleSpeechRecognition() {
    if (!recognition) {
      initSpeechRecognition();
      if (!recognition) return; // Still no support
    }
    
    if (isListening) {
      // Stop listening
      stopListening();
    } else {
      // Start continuous listening
      startContinuousListening();
    }
  }
  
  /**
   * Start continuous speech recognition with auto-stop
   */
  function startContinuousListening() {
    if (!recognition) return;
    
    // Update language before starting
    const langMap = {
      'en': 'en-US',
      'hi': 'hi-IN',
      'te': 'te-IN',
      'ta': 'ta-IN',
      'mr': 'mr-IN',
      'kn': 'kn-IN'
    };
    recognition.lang = langMap[currentLanguage] || 'en-US';
    
    // Configure for continuous listening
    recognition.continuous = true;
    recognition.interimResults = true;
    
    // Update UI to listening state (without changing icon)
    updateListeningUI(true);
    
    // Start auto-stop timer
    startAutoStopTimer();
    
    // Start recognition
    try {
      recognition.start();
      console.log("🎤 Starting continuous speech recognition for:", recognition.lang);
    } catch (error) {
      console.error("Failed to start recognition:", error);
      // Recognition might already be running, try to stop and restart
      recognition.stop();
      setTimeout(() => {
        try {
          recognition.start();
        } catch (e) {
          console.error("Failed to restart recognition:", e);
          updateListeningUI(false);
        }
      }, 100);
    }
  }
  
  /**
   * Stop speech recognition
   */
  function stopListening() {
    if (!recognition) return;
    
    recognition.stop();
    updateListeningUI(false);
    clearAutoStopTimer();
    console.log("🎤 Stopping speech recognition");
  }
  
  /**
   * Auto-stop timer management
   */
  let autoStopTimer = null;
  let lastSpeechTime = null;
  const AUTO_STOP_DELAY = 4000; // 4 seconds of silence
  
  function startAutoStopTimer() {
    lastSpeechTime = Date.now();
    
    // Clear existing timer
    clearAutoStopTimer();
    
    // Start new timer that checks periodically
    autoStopTimer = setInterval(() => {
      const silenceDuration = Date.now() - lastSpeechTime;
      
      if (silenceDuration > AUTO_STOP_DELAY && isListening) {
        console.log("🎤 Auto-stopping after", silenceDuration, "ms of silence");
        stopListening();
      }
    }, 1000); // Check every second
  }
  
  function clearAutoStopTimer() {
    if (autoStopTimer) {
      clearInterval(autoStopTimer);
      autoStopTimer = null;
    }
  }
  
  function resetAutoStopTimer() {
    lastSpeechTime = Date.now();
  }
  
  /**
   * Update UI for listening state (without changing microphone icon)
   */
  function updateListeningUI(listening) {
    if (!inputEl || !inputArea) return;
    
    if (listening) {
      // Add listening state to input area
      inputArea.classList.add('listening');
      inputEl.classList.add('listening');
      
      // Show listening text
      showListeningStatus("Listening...");
      
      isListening = true;
    } else {
      // Remove listening state
      inputArea.classList.remove('listening');
      inputEl.classList.remove('listening');
      
      // Hide listening text
      hideListeningStatus();
      
      // Clear interim text styling
      if (inputEl) {
        inputEl.style.fontStyle = '';
        inputEl.style.opacity = '';
      }
      
      isListening = false;
    }
  }
  
  /**
   * Show listening status text
   */
  function showListeningStatus(text) {
    let statusEl = document.querySelector('.listening-status');
    
    if (!statusEl) {
      statusEl = document.createElement('div');
      statusEl.className = 'listening-status';
      inputArea.appendChild(statusEl);
    }
    
    statusEl.textContent = text;
    statusEl.style.display = 'block';
  }
  
  /**
   * Hide listening status text
   */
  function hideListeningStatus() {
    const statusEl = document.querySelector('.listening-status');
    if (statusEl) {
      statusEl.style.display = 'none';
    }
  }

  function returnToHome() {
    // Stop any speech and listening
    stopSpeech();
    stopListening();
    
    // Clear visual messages
    messagesEl.innerHTML = "";
    
    // Hide input area
    inputArea.style.display = "none";
    inputEl.value = "";
    
    // Keep the same session ID to preserve chat history
    // This allows the model to use previous conversation context
    
    // Show welcome screen
    showWelcome();
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
    
    const translatedCategories = getTranslatedCategories();
    const categoriesEnKeys = Object.keys(CATEGORIES_EN).filter(c => c !== "Others");

    translatedCategories.forEach((cat, i) => {
      const btn = document.createElement("button");
      btn.className = "category-btn";
      btn.innerHTML = `<span class="cat-icon">${icons[i]}</span><span class="cat-label">${cat}</span>`;
      
      const enKey = categoriesEnKeys[i];  // Get corresponding English key
      
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        wrapper.remove();
        addUserMessage(cat);
        if (i === 0) {
          // Step 1 of guided admission flow instead of dumping all info at once
          showAdmissionTypeMenu();
        } else {
          sendMessage(cat, true);
        }
      });
      grid.appendChild(btn);
    });

    // "Others" button
    const othersBtn = document.createElement("button");
    othersBtn.className = "category-btn others-btn";
    const othersText = t("category_others");
    othersBtn.innerHTML = `<span class="cat-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg></span><span class="cat-label">${othersText}</span>`;
    othersBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      wrapper.remove();
      // Don't add user message here - just show input area
      // User will type their own question
      showInputArea();
      inputEl.focus();
      // Optionally show a prompt
      if (currentLanguage !== "en") {
        addBotMessage("Please type your question:");
      }
    });
    grid.appendChild(othersBtn);

    wrapper.appendChild(grid);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
  }

  /**
   * Guided admission flow – Step 1
   * Ask the user whether they want Admission Process or Eligibility Criteria.
   */
  function showAdmissionTypeMenu() {
    addBotMessage(t("admission_sub_prompt"));

    const wrapper = document.createElement("div");
    wrapper.className = "message bot";

    const qr = document.createElement("div");
    qr.className = "quick-replies";

    ["admission_type_process", "admission_type_eligibility"].forEach((key) => {
      const btn = document.createElement("button");
      btn.textContent = t(key);
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        wrapper.remove();
        addUserMessage(t(key));
        showProgramMenu(key);
      });
      qr.appendChild(btn);
    });

    wrapper.appendChild(qr);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
  }

  /**
   * Guided admission flow – Step 2
   * Ask which program (B.Tech / M.Tech / MCA) then send the composed query.
   */
  function showProgramMenu(admissionTypeKey) {
    addBotMessage(t("admission_program_prompt"));

    const wrapper = document.createElement("div");
    wrapper.className = "message bot";

    const qr = document.createElement("div");
    qr.className = "quick-replies";

    ["B.Tech", "M.Tech", "MCA"].forEach((program) => {
      const btn = document.createElement("button");
      btn.textContent = program;
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        wrapper.remove();
        addUserMessage(program);
        // Compose the specific query and send it to the backend
        const queryKey = admissionTypeKey === "admission_type_process"
          ? "admission_query_process"
          : "admission_query_eligibility";
        const query = t(queryKey).replace("{program}", program);
        sendMessage(query, true);
      });
      qr.appendChild(btn);
    });

    wrapper.appendChild(qr);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
  }

  /** Render follow-up question buttons for a category */
  function addFollowUpButtons(questions, category) {
    // Simplified - just show input for multilingual support
    // Backend will handle the conversation in user's language
    showInputArea();
  }

  function addMessage(text, sender) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${sender}`;

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    if (sender === "bot") {
      bubble.innerHTML = renderMarkdown(text);
      
      // Add TTS button for bot messages
      const ttsBtn = createTTSButton(text);
      bubble.appendChild(ttsBtn);
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
    // Always show and enable input area after bot message
    // This ensures users can type their answers during conversation flows
    showInputArea();
    inputEl.disabled = false;
    sendBtn.disabled = false;
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
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        wrapper.remove(); // remove chips after click
        sendMessage(opt);
      });
      qr.appendChild(btn);
    });

    wrapper.appendChild(qr);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
  }

  /**
   * Render clickable options as buttons after a bot message
   * @param {Array} options - Array of {label, value} objects
   * @param {HTMLElement} bubbleElement - The bubble element to attach options to
   */
  function renderClickableOptions(options, bubbleElement) {
    if (!options || options.length === 0) return;

    const optionsContainer = document.createElement("div");
    optionsContainer.className = "clickable-options";

    options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.className = "option-button";
      btn.textContent = opt.label;

      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        // Remove all option buttons after selection
        optionsContainer.remove();
        // Send the value automatically
        sendMessage(opt.value);
      });

      optionsContainer.appendChild(btn);
    });

    bubbleElement.appendChild(optionsContainer);
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
    // Focus on input field when shown (if chat is open)
    if (isOpen) {
      setTimeout(() => inputEl.focus(), 100);
    }
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  }

  /**
   * Scroll to show the top of a specific message element
   */
  function scrollToShowMessage(messageElement) {
    if (!messageElement) return;
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messageElement.offsetTop;
    });
  }

  /**
   * Check if the user's question message has reached the viewport top
   * Returns true when we should stop auto-scrolling
   */
  function isMessageTopVisible(messageElement) {
    if (!messageElement) return true;
    
    const messageTop = messageElement.offsetTop;
    const scrollTop = messagesEl.scrollTop;
    const threshold = 10; // Stop when user question is just visible at top
    
    // Stop scrolling when scroll position reaches the user's question
    return scrollTop >= (messageTop - threshold);
  }

  // ── Auto-Popup Welcome Messages ──────────────────────────────

  /**
   * Display welcome popup bubble next to chatbot icon
   * Triggers only once per session
   */
  async function showAutoWelcomeMessages() {
    const POPUP_SHOWN_KEY = "chatbot_popup_shown";
    
    // Check if popup was already shown in this session
    if (sessionStorage.getItem(POPUP_SHOWN_KEY)) {
      return;
    }

    // Mark as shown for this session
    sessionStorage.setItem(POPUP_SHOWN_KEY, "true");

    // Wait 5 seconds after page load before showing welcome popup
    await new Promise(resolve => setTimeout(resolve, 5000));

    // Show the popup bubble
    showWelcomePopup();

    // Auto-hide popup after 5 seconds if no interaction
    setTimeout(() => {
      hideWelcomePopup();
    }, 5000);
  }

  /**
   * Show the welcome popup bubble
   */
  function showWelcomePopup() {
    if (welcomePopup) {
      welcomePopup.style.display = '';
      welcomePopup.classList.add('visible');
    }
  }

  /**
   * Hide the welcome popup bubble
   */
  function hideWelcomePopup() {
    if (welcomePopup) {
      welcomePopup.classList.remove('visible');
      // Force hide with inline style as fallback
      setTimeout(() => {
        if (welcomePopup && !welcomePopup.classList.contains('visible')) {
          welcomePopup.style.display = 'none';
        }
      }, 400);
    }
  }

  /**
   * Open chat from popup - shows welcome screen
   */
  function openChatFromPopup() {
    // Hide the popup
    hideWelcomePopup();
    
    // Open the chat
    openChat();
    
    // Show welcome if first time or no messages
    if (messagesEl.children.length === 0) {
      showWelcome();
    }
  }

  // ── API Communication ────────────────────────────────────────

  async function sendMessage(text, skipAddingUserMessage = false) {
    if (!text || !text.trim() || isSending) return;

    const userText = text.trim();
    
    // Only add user message if not already added (prevents duplicates)
    if (!skipAddingUserMessage) {
      addUserMessage(userText);
    }
    
    inputEl.value = "";
    inputEl.disabled = true;
    sendBtn.disabled = true;
    isSending = true;

    showTyping();

    try {
      // Use streaming endpoint for ChatGPT-style typing effect
      const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userText,
          session_id: sessionId,
          language: currentLanguage,
        }),
      });

      if (response.status === 429) {
        hideTyping();
        addBotMessage(t("rate_limit"));
        return;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      hideTyping();

      // Get the user's question message that was just added (to use for scroll tracking)
      const userMessages = messagesEl.querySelectorAll('.message.user');
      const userMessageDiv = userMessages[userMessages.length - 1]; // Last user message

      // Create bot message container for streaming
      const messageDiv = document.createElement("div");
      messageDiv.className = "message bot";
      let shouldAutoScroll = true; // Track if we should keep auto-scrolling
      
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      
      const content = document.createElement("div");
      content.className = "content streaming"; // Add streaming class for cursor effect
      content.innerHTML = ""; // Will be filled with streamed tokens
      
      const timeDiv = document.createElement("div");
      timeDiv.className = "time";
      timeDiv.textContent = timestamp();
      
      bubble.appendChild(content);
      bubble.appendChild(timeDiv);
      messageDiv.appendChild(bubble);
      messagesEl.appendChild(messageDiv);
      scrollToBottom();

      // Read streaming response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullReply = "";
      let sources = [];
      let intent = "";
      let options = [];  // Clickable options from backend
      let hasError = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        
        // Keep incomplete line in buffer
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.error) {
                content.innerHTML = renderMarkdown(`❌ ${data.error}`);
                content.classList.remove("streaming");
                hasError = true;
                break;
              }
              
              if (!data.done && data.token) {
                // Append token to display
                fullReply += data.token;
                content.innerHTML = renderMarkdown(fullReply);
                
                // Auto-scroll until user's question reaches viewport top
                if (shouldAutoScroll) {
                  if (isMessageTopVisible(userMessageDiv)) {
                    // User's question has reached viewport top
                    // Keep it pinned there, don't scroll anymore
                    shouldAutoScroll = false;
                  } else {
                    // User question not at viewport top yet, keep scrolling down
                    scrollToBottom();
                  }
                } else {
                  // After stopping, keep user question pinned at viewport top
                  if (userMessageDiv) {
                    scrollToShowMessage(userMessageDiv);
                  }
                }
              }
              
              if (data.done) {
                // Stream complete - save metadata and remove streaming cursor
                content.classList.remove("streaming");
                
                if (data.session_id) {
                  sessionId = data.session_id;
                  sessionStorage.setItem("chatbot_session", sessionId);
                }
                if (data.sources) {
                  sources = data.sources;
                }
                if (data.intent) {
                  intent = data.intent;
                }
                if (data.options && Array.isArray(data.options)) {
                  options = data.options;
                }
              }
            } catch (e) {
              console.error("Failed to parse SSE data:", e, line);
            }
          }
        }
        
        // Exit while loop if error occurred
        if (hasError) break;
      }

      // Add source citations if available
      if (sources && sources.length > 0) {
        const srcSpan = document.createElement("div");
        srcSpan.style.cssText =
          "font-size:10px;color:#888;margin-top:6px;font-style:italic;";
        srcSpan.textContent = "📄 Sources: " + sources.join(", ");
        bubble.appendChild(srcSpan);
      }

      // Render clickable options if available
      if (options && options.length > 0) {
        renderClickableOptions(options, bubble);
      }

    } catch (err) {
      hideTyping();
      console.error("Chat error:", err);
      addBotMessage(t("error_connection"));
    } finally {
      isSending = false;
      showInputArea();  // Make sure input area is visible
      inputEl.disabled = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }



  // ── Event Listeners ──────────────────────────────────────────

  toggleBtn.addEventListener("click", toggleChat);
  closeBtn.addEventListener("click", toggleChat);

  // Close popup button - simple and direct
  if (popupClose) {
    popupClose.onclick = function(e) {
      e.stopPropagation();
      hideWelcomePopup();
    };
  }

  // Popup message click to open chat
  if (welcomePopup) {
    const popupMessage = welcomePopup.querySelector('.popup-message');
    if (popupMessage) {
      popupMessage.onclick = function(e) {
        // Don't trigger if clicking close button
        if (e.target.id === 'popup-close' || e.target.closest('#popup-close')) {
          return;
        }
        openChatFromPopup();
      };
    }
  }
  
  homeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    returnToHome();
  });
  
  micBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleSpeechRecognition();
  });

  sendBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    sendMessage(inputEl.value);
  });

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(inputEl.value);
    }
  });

  // Close widget when clicking outside (improved to prevent accidental closures)
  document.addEventListener("click", (e) => {
    if (!isOpen) return;
    
    // Check if click is outside both the container and toggle button
    const clickedInsideContainer = container.contains(e.target);
    const clickedToggleBtn = toggleBtn.contains(e.target);
    const clickedInsidePopup = welcomePopup && welcomePopup.contains(e.target);
    
    // Only close if click is truly outside all chat-related elements
    if (!clickedInsideContainer && !clickedToggleBtn && !clickedInsidePopup) {
      isOpen = false;
      container.classList.remove("visible");
      toggleBtn.classList.remove("open");
    }
  });

  // ── Accessibility ────────────────────────────────────────────
  toggleBtn.setAttribute("aria-label", "Open chat");
  closeBtn.setAttribute("aria-label", "Close chat");
  
  // ── Page Visibility Handler ──────────────────────────────────
  // Stop speech when user switches tabs or minimizes browser
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopSpeech();
    }
  });
  
  // Stop speech when page is about to unload
  window.addEventListener("beforeunload", () => {
    stopSpeech();
  });

  // ── Initialize Speech Recognition ────────────────────────────
  // Initialize STT when page loads (will check browser support)
  initSpeechRecognition();
  
  // Initialize microphone with simple icon (no state changes)
  if (micBtn) {
    micBtn.innerHTML = '🎤';
    micBtn.title = "Click to start/stop voice input";
  }
  
  // ── Initialize Speech Synthesis Voices ───────────────────────
  // Load voices on page load (some browsers need this)
  if (window.speechSynthesis) {
    // Load voices immediately
    window.speechSynthesis.getVoices();
    
    // Also listen for voiceschanged event (Chrome needs this)
    window.speechSynthesis.addEventListener('voiceschanged', () => {
      const voices = window.speechSynthesis.getVoices();
      console.log("🔊 Voices loaded:", voices.length);
      
      // Log available Indian language voices for debugging
      const indianVoices = voices.filter(v => 
        v.lang.includes('IN') || 
        v.lang.startsWith('hi') || 
        v.lang.startsWith('te') || 
        v.lang.startsWith('ta') || 
        v.lang.startsWith('kn') || 
        v.lang.startsWith('mr')
      );
      
      if (indianVoices.length > 0) {
        console.log("  - Indian language voices available:");
        indianVoices.forEach(v => console.log("    •", v.name, "(" + v.lang + ")"));
      } else {
        console.warn("  - ⚠️ No Indian language voices found");
        console.warn("  - Install language packs or use Chrome for best support");
      }
    });
  }

  // ── Auto-Popup on Page Load ──────────────────────────────────
  // Trigger auto-welcome messages after page loads
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", showAutoWelcomeMessages);
  } else {
    // DOM already loaded
    showAutoWelcomeMessages();
  }
})();

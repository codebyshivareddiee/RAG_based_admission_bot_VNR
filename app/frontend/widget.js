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
  const homeBtn = document.getElementById("home-btn");
  const fullscreenBtn = document.getElementById("fullscreen-btn");
  const messagesEl = document.getElementById("chat-messages");
  const inputEl = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");
  const micBtn = document.getElementById("mic-btn");
  const inputArea = document.getElementById("chat-input-area");
  const welcomePopup = document.getElementById("welcome-popup");
  const popupClose = document.getElementById("popup-close");
  const disclaimerEl = document.getElementById("chat-disclaimer");
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
  let lastTranscript = "";
  let sttCommittedTranscript = "";
  let availableVoices = [];
  
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
  const chatHistory = [];

  // ── Language Configuration ───────────────────────────────────
  let enabledLanguagesConfig = null;
  let languagesConfigLoaded = false;
  let languagesConfigPromise = null;
  let micEnabled = true;
  let dynamicDisclaimer = "⚠️ Official assistant for VNRVJIET. Information is for guidance only. Multilingual chatbot - Available in English, Hindi, Telugu, Tamil, Marathi, Kannada & more.";

  // Fetch enabled languages from backend on init
  async function fetchEnabledLanguages() {
    if (languagesConfigLoaded) {
      return enabledLanguagesConfig;
    }
    if (languagesConfigPromise) {
      return languagesConfigPromise;
    }

    languagesConfigPromise = (async () => {
    try {
      const response = await fetch(`${API_BASE}/api/config/languages`);
      if (response.ok) {
        const data = await response.json();
        enabledLanguagesConfig = data.languages;
        dynamicDisclaimer = data.disclaimer;
        micEnabled = data.mic_enabled !== false;
        console.log("Enabled languages loaded:", Object.keys(enabledLanguagesConfig));
        
        // Update disclaimer in DOM
        if (disclaimerEl) {
          disclaimerEl.textContent = dynamicDisclaimer;
        }
        if (micBtn) {
          micBtn.style.display = micEnabled ? "flex" : "none";
          micBtn.disabled = !micEnabled;
        }
        languagesConfigLoaded = true;
        return enabledLanguagesConfig;
      }
    } catch (err) {
      console.warn("Failed to fetch language config:", err);
    }
    languagesConfigLoaded = true;
    return enabledLanguagesConfig;
    })();

    return languagesConfigPromise;
  }

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
    // ── Fee guided-flow translations ───────────────────────────
    fees_sub_prompt: {
      en: "What would you like to know?",
      hi: "आप क्या जानना चाहते हैं?",
      te: "మీరు ఏమి తెలుసుకోవాలనుకుంటున్నారు?",
      ta: "நீங்கள் என்ன தெரிந்துகொள்ள விரும்புகிறீர்கள்?",
      mr: "तुम्हाला काय जाणून घ्यायचे आहे?",
      kn: "ನೀವು ಏನು ತಿಳಿದುಕೊಳ್ಳಲು ಬಯಸುತ್ತೀರಿ?",
    },
    fees_type_structure: {
      en: "Fee Structure",
      hi: "शुल्क संरचना",
      te: "ఫీజు నిర్మాణం",
      ta: "கட்டண அமைப்பு",
      mr: "फी रचना",
      kn: "ಶುಲ್ಕ ರಚನೆ",
    },
    fees_type_scholarships: {
      en: "Scholarships",
      hi: "छात्रवृत्तियां",
      te: "స్కాలర్‌షిప్‌లు",
      ta: "உதவித்தொகைகள்",
      mr: "शिष्यवृत्ती",
      kn: "ವಿದ್ಯಾರ್ಥಿವೇತನಗಳು",
    },
    fees_query_structure: {
      en: "What is the {program} fee structure at VNRVJIET?",
      hi: "VNRVJIET में {program} की शुल्क संरचना क्या है?",
      te: "VNRVJIET లో {program} ఫీజు నిర్మాణం ఏమిటి?",
      ta: "VNRVJIET இல் {program} கட்டண அமைப்பு என்ன?",
      mr: "VNRVJIET मध्ये {program} ची फी रचना काय आहे?",
      kn: "VNRVJIET ನಲ್ಲಿ {program} ಶುಲ್ಕ ರಚನೆ ಏನು?",
    },
    fees_query_scholarships: {
      en: "What scholarships are available for {program} at VNRVJIET?",
      hi: "VNRVJIET में {program} के लिए कौन सी छात्रवृत्तियां उपलब्ध हैं?",
      te: "VNRVJIET లో {program} కోసం ఏ స్కాలర్‌షిప్‌లు అందుబాటులో ఉన్నాయి?",
      ta: "VNRVJIET இல் {program}க்கு எந்த உதவித்தொகைகள் கிடைக்கின்றன?",
      mr: "VNRVJIET मध्ये {program} साठी कोणत्या शिष्यवृत्ती उपलब्ध आहेत?",
      kn: "VNRVJIET ನಲ್ಲಿ {program}ಗಾಗಿ ಯಾವ ವಿದ್ಯಾರ್ಥಿವೇತನಗಳು ಲಭ್ಯವಿವೆ?",
    },
    type_question_prompt: {
      en: "Please type your question:",
      hi: "कृपया अपना प्रश्न टाइप करें:",
      te: "దయచేసి మీ ప్రశ్నను టైప్ చేయండి:",
      ta: "தயவுசெய்து உங்கள் கேள்வியை டைப் செய்யவும்:",
      mr: "कृपया तुमचा प्रश्न टाइप करा:",
      kn: "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಟೈಪ್ ಮಾಡಿ:",
    },
    tts_listen: {
      en: "Listen",
      hi: "सुनें",
      te: "వినండి",
      ta: "கேளுங்கள்",
      mr: "ऐका",
      kn: "ಆಲಿಸಿ",
    },
    tts_stop: {
      en: "Stop",
      hi: "रोकें",
      te: "ఆపండి",
      ta: "நிறுத்து",
      mr: "थांबवा",
      kn: "ನಿಲ್ಲಿಸಿ",
    },
    tts_aria_listen: {
      en: "Listen to response",
      hi: "उत्तर सुनें",
      te: "సమాధానం వినండి",
      ta: "பதிலை கேளுங்கள்",
      mr: "उत्तर ऐका",
      kn: "ಉತ್ತರವನ್ನು ಆಲಿಸಿ",
    },
    tts_not_supported: {
      en: "Text-to-speech is not supported in your browser",
      hi: "आपके ब्राउज़र में टेक्स्ट-टू-स्पीच उपलब्ध नहीं है",
      te: "మీ బ్రౌజర్‌లో టెక్స్ట్-టు-స్పీచ్ అందుబాటులో లేదు",
      ta: "உங்கள் உலாவியில் உரை-ஒலி வசதி இல்லை",
      mr: "तुमच्या ब्राउझरमध्ये टेक्स्ट-टू-स्पीच उपलब्ध नाही",
      kn: "ನಿಮ್ಮ ಬ್ರೌಸರ್‌ನಲ್ಲಿ ಟೆಕ್ಸ್ಟ್-ಟು-ಸ್ಪೀಚ್ ಲಭ್ಯವಿಲ್ಲ",
    },
    stt_listening: {
      en: "Listening...",
      hi: "सुन रहा हूं...",
      te: "వింటున్నాను...",
      ta: "கேட்கிறேன்...",
      mr: "ऐकत आहे...",
      kn: "ಆಲಿಸುತ್ತಿದ್ದೇನೆ...",
    },
    stt_listening_more: {
      en: "Listening... You can continue speaking.",
      hi: "सुन रहा हूं... आप बोलना जारी रख सकते हैं।",
      te: "వింటున్నాను... మీరు మాట్లాడటం కొనసాగించవచ్చు.",
      ta: "கேட்கிறேன்... நீங்கள் தொடர்ந்து பேசலாம்.",
      mr: "ऐकत आहे... तुम्ही बोलणे सुरू ठेवू शकता.",
      kn: "ಆಲಿಸುತ್ತಿದ್ದೇನೆ... ನೀವು ಮುಂದುವರಿದು ಮಾತನಾಡಬಹುದು.",
    },
    stt_error_start: {
      en: "Failed to start microphone. Please try again.",
      hi: "माइक्रोफोन शुरू नहीं हो सका। कृपया फिर से प्रयास करें।",
      te: "మైక్రోఫోన్ ప్రారంభం కాలేదు. దయచేసి మళ్లీ ప్రయత్నించండి.",
      ta: "மைக்ரோஃபோனை தொடங்க முடியவில்லை. மீண்டும் முயற்சிக்கவும்.",
      mr: "मायक्रोफोन सुरू होऊ शकला नाही. कृपया पुन्हा प्रयत्न करा.",
      kn: "ಮೈಕ್ರೊಫೋನ್ ಪ್ರಾರಂಭಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
    },
    stt_not_supported: {
      en: "Speech recognition is not supported in your browser",
      hi: "आपके ब्राउज़र में वॉइस पहचान उपलब्ध नहीं है",
      te: "మీ బ్రౌజర్‌లో వాయిస్ గుర్తింపు అందుబాటులో లేదు",
      ta: "உங்கள் உலாவியில் குரல் அறிதல் வசதி இல்லை",
      mr: "तुमच्या ब्राउझरमध्ये आवाज ओळख उपलब्ध नाही",
      kn: "ನಿಮ್ಮ ಬ್ರೌಸರ್‌ನಲ್ಲಿ ಧ್ವನಿ ಗುರುತింపు ಲಭ್ಯವಿಲ್ಲ",
    },
  };

  function t(key) {
    return TRANSLATIONS[key]?.[currentLanguage] || TRANSLATIONS[key]?.en || key;
  }

  function ttsButtonLabel(isPlaying) {
    return isPlaying ? t("tts_stop") : t("tts_listen");
  }

  function setTTSButtonVisualState(buttonElement, isPlaying) {
    if (!buttonElement) return;
    const icon = isPlaying ? "⏸" : "🔊";
    buttonElement.innerHTML = `<span class="tts-icon">${icon}</span> ${ttsButtonLabel(isPlaying)}`;
    buttonElement.setAttribute("aria-label", t("tts_aria_listen"));
  }

  function refreshTTSButtonsForLanguage() {
    try {
      document.querySelectorAll(".tts-button").forEach((btn) => {
        const isPlaying = btn.classList.contains("playing");
        setTTSButtonVisualState(btn, isPlaying);
      });
    } catch (error) {
      console.error("Error refreshing TTS button labels:", error);
    }
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
      refreshTTSButtonsForLanguage();
      
      console.log("Language set successfully:", lang);
    } else {
      console.error("Unsupported language:", lang);
    }
  }

  // ── Speech normalization helpers ──────────────────────────────
  const EMOJI_PATTERN = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu;
  const SPEECH_REPLACEMENTS = {
    hi: [
      [/\bb\.?\s*tech\b/gi, "बी टेक"],
      [/\bm\.?\s*tech\b/gi, "एम टेक"],
      [/\bm\.?\s*b\.?\s*a\b|\bmba\b/gi, "एम बी ए"],
      [/\bm\.?\s*c\.?\s*a\b|\bmca\b/gi, "एम सी ए"],
      [/\bcse\b/gi, "सी एस ई"],
      [/\bece\b/gi, "ई सी ई"],
      [/\beee\b/gi, "ई ई ई"],
      [/\bit\b/gi, "आई टी"],
    ],
    te: [
      [/\bb\.?\s*tech\b/gi, "బి టెక్"],
      [/\bm\.?\s*tech\b/gi, "ఎం టెక్"],
      [/\bm\.?\s*b\.?\s*a\b|\bmba\b/gi, "ఎం బి ఏ"],
      [/\bm\.?\s*c\.?\s*a\b|\bmca\b/gi, "ఎం సి ఏ"],
    ],
    mr: [
      [/\bb\.?\s*tech\b/gi, "बी टेक"],
      [/\bm\.?\s*tech\b/gi, "एम टेक"],
      [/\bm\.?\s*b\.?\s*a\b|\bmba\b/gi, "एम बी ए"],
      [/\bm\.?\s*c\.?\s*a\b|\bmca\b/gi, "एम सी ए"],
    ],
  };

  function normalizeSpeechText(text, language) {
    let normalized = (text || "");
    normalized = normalized
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
      .replace(/https?:\/\/[^\s)]+/gi, " ")
      .replace(/www\.[^\s)]+/gi, " ")
      .replace(/<[^>]*>/g, " ")
      .replace(/\*\*(.*?)\*\*/g, "$1")
      .replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/#{1,6}\s*/g, "")
      .replace(/[•●▪◦]/g, ". ")
      .replace(/^\s*\d+\.\s+/gm, "")
      .replace(/[→⇒]/g, " ")
      .replace(EMOJI_PATTERN, " ")
      .replace(/\n+/g, ". ");

    const languageRules = SPEECH_REPLACEMENTS[language] || [];
    for (const [pattern, replacement] of languageRules) {
      normalized = normalized.replace(pattern, replacement);
    }

    return normalized.replace(/\s+/g, " ").trim();
  }

  const TTS_LANG_TO_LOCALES = {
    en: ["en-IN", "en-US", "en-GB"],
    hi: ["hi-IN", "hi"],
    te: ["te-IN", "te"],
    ta: ["ta-IN", "ta"],
    kn: ["kn-IN", "kn"],
    ml: ["ml-IN", "ml"],
    mr: ["mr-IN", "mr"],
    bn: ["bn-IN", "bn-BD", "bn"],
    gu: ["gu-IN", "gu"],
    pa: ["pa-IN", "pa"],
    or: ["or-IN", "or"],
    ur: ["ur-IN", "ur-PK", "ur"],
  };

  const TTS_NEIGHBOR_LANGUAGE_FALLBACK = {
    ml: ["ta", "kn", "te"],
    ta: ["ml", "te", "kn"],
    te: ["kn", "ta", "ml"],
    kn: ["te", "ta", "ml"],
    bn: ["hi", "mr"],
    gu: ["hi", "mr"],
    pa: ["hi"],
    mr: ["hi"],
    hi: ["mr", "bn", "gu", "pa"],
  };

  function getBrowserLanguageCode() {
    const navLang = (navigator.language || "en").toLowerCase();
    return navLang.split("-")[0] || "en";
  }

  function detectLanguageFromText(text) {
    if (!text || text.length === 0) {
      return currentLanguage || getBrowserLanguageCode();
    }

    const sample = text.slice(0, 400);
    const counts = {
      devanagari: 0,
      telugu: 0,
      tamil: 0,
      kannada: 0,
      malayalam: 0,
      bengali: 0,
      gujarati: 0,
      gurmukhi: 0,
      odia: 0,
      latin: 0,
    };

    for (const char of sample) {
      const code = char.charCodeAt(0);

      if (code >= 0x0900 && code <= 0x097F) counts.devanagari++;
      else if (code >= 0x0C00 && code <= 0x0C7F) counts.telugu++;
      else if (code >= 0x0B80 && code <= 0x0BFF) counts.tamil++;
      else if (code >= 0x0C80 && code <= 0x0CFF) counts.kannada++;
      else if (code >= 0x0D00 && code <= 0x0D7F) counts.malayalam++;
      else if (code >= 0x0980 && code <= 0x09FF) counts.bengali++;
      else if (code >= 0x0A80 && code <= 0x0AFF) counts.gujarati++;
      else if (code >= 0x0A00 && code <= 0x0A7F) counts.gurmukhi++;
      else if (code >= 0x0B00 && code <= 0x0B7F) counts.odia++;
      else if ((code >= 0x0041 && code <= 0x005A) || (code >= 0x0061 && code <= 0x007A)) counts.latin++;
    }

    const maxCount = Math.max(...Object.values(counts));
    const threshold = Math.max(2, sample.length * 0.12);

    if (maxCount >= threshold) {
      if (counts.telugu === maxCount) return "te";
      if (counts.tamil === maxCount) return "ta";
      if (counts.kannada === maxCount) return "kn";
      if (counts.malayalam === maxCount) return "ml";
      if (counts.bengali === maxCount) return "bn";
      if (counts.gujarati === maxCount) return "gu";
      if (counts.gurmukhi === maxCount) return "pa";
      if (counts.odia === maxCount) return "or";
      if (counts.devanagari === maxCount) {
        if (currentLanguage === "mr") return "mr";
        return "hi";
      }
      if (counts.latin === maxCount) return "en";
    }

    return currentLanguage || getBrowserLanguageCode();
  }

  function updateAvailableVoices() {
    if (!window.speechSynthesis) return [];
    availableVoices = window.speechSynthesis.getVoices() || [];
    return availableVoices;
  }

  function getVoiceForLang(langCode) {
    const normalizedLang = (langCode || "").toLowerCase();
    const allVoices = availableVoices.length ? availableVoices : updateAvailableVoices();
    if (!allVoices.length) return null;

    const localeCandidates = TTS_LANG_TO_LOCALES[normalizedLang] || [`${normalizedLang}`];
    const normalizedVoiceEntries = allVoices.map((voice) => ({
      voice,
      voiceLang: (voice.lang || "").toLowerCase(),
      voiceName: (voice.name || "").toLowerCase(),
    }));

    // 1) Exact locale startsWith (e.g., te-IN)
    for (const locale of localeCandidates) {
      const localeLower = locale.toLowerCase();
      const found = normalizedVoiceEntries.find((entry) => entry.voiceLang === localeLower);
      if (found) return found.voice;
    }

    // 2) Prefix language match (e.g., te)
    const prefix = normalizedLang || localeCandidates[0].split("-")[0];
    const prefixMatch = normalizedVoiceEntries.find((entry) => entry.voiceLang.startsWith(prefix));
    if (prefixMatch) return prefixMatch.voice;

    // 3) Closest language family / neighbor language fallback
    const neighbors = TTS_NEIGHBOR_LANGUAGE_FALLBACK[normalizedLang] || [];
    for (const neighbor of neighbors) {
      const candidate = normalizedVoiceEntries.find((entry) => entry.voiceLang.startsWith(neighbor));
      if (candidate) return candidate.voice;
    }

    // 4) Voice name hint fallback (if lang tag is inconsistent)
    const languageNameHints = {
      te: ["telugu", "తెలుగు"],
      ta: ["tamil", "தமிழ்"],
      kn: ["kannada", "ಕನ್ನಡ"],
      ml: ["malayalam", "മലയാളം"],
      hi: ["hindi", "हिन्दी"],
      mr: ["marathi", "मराठी"],
      bn: ["bengali", "bangla", "বাংলা"],
      gu: ["gujarati", "ગુજરાતી"],
      pa: ["punjabi", "gurmukhi", "ਪੰਜਾਬੀ"],
      en: ["english"],
    };
    const hints = languageNameHints[normalizedLang] || [];
    for (const hint of hints) {
      const byName = normalizedVoiceEntries.find((entry) => entry.voiceName.includes(hint));
      if (byName) return byName.voice;
    }

    // 5) English fallback (voice only; text language stays unchanged)
    const englishFallback = normalizedVoiceEntries.find((entry) => entry.voiceLang.startsWith("en"));
    if (englishFallback) return englishFallback.voice;

    // 6) Browser default / first voice
    return allVoices.find((voice) => voice.default) || allVoices[0] || null;
  }

  function removeConsecutiveDuplicateWords(text) {
    const tokens = (text || "").match(/[\p{L}\p{N}]+|[^\s]/gu) || [];
    const deduped = [];

    tokens.forEach((token) => {
      if (deduped.length === 0) {
        deduped.push(token);
        return;
      }

      const prev = deduped[deduped.length - 1];
      const isWord = /[\p{L}\p{N}]/u.test(token);
      const prevIsWord = /[\p{L}\p{N}]/u.test(prev);
      if (isWord && prevIsWord && token.toLowerCase() === prev.toLowerCase()) {
        return;
      }

      deduped.push(token);
    });

    return deduped
      .join(" ")
      .replace(/\s+([,.;:!?])/g, "$1")
      .replace(/([([{])\s+/g, "$1")
      .replace(/\s+([)\]}])/g, "$1")
      .replace(/\s+/g, " ")
      .trim();
  }

  function normalizeUserInput(text) {
    return removeConsecutiveDuplicateWords((text || "").replace(/\s+/g, " ").trim());
  }

  function mergeUniqueTranscript(existingText, newText) {
    const base = normalizeUserInput(existingText || "");
    const incoming = normalizeUserInput(newText || "");

    if (!incoming) return base;
    if (!base) return incoming;

    const baseTokens = base.split(/\s+/);
    const incomingTokens = incoming.split(/\s+/);
    const maxOverlap = Math.min(baseTokens.length, incomingTokens.length, 20);

    let overlap = 0;
    for (let size = maxOverlap; size > 0; size--) {
      const baseSlice = baseTokens.slice(-size).map((w) => w.toLowerCase()).join(" ");
      const incomingSlice = incomingTokens.slice(0, size).map((w) => w.toLowerCase()).join(" ");
      if (baseSlice === incomingSlice) {
        overlap = size;
        break;
      }
    }

    const mergedTokens = [...baseTokens, ...incomingTokens.slice(overlap)];
    return normalizeUserInput(mergedTokens.join(" "));
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
    if (container) {
      container.classList.toggle("visible", isOpen);
    }
    if (toggleBtn) {
      toggleBtn.classList.toggle("open", isOpen);
    }

    if (isOpen) {
      // Show welcome if first time
      if (messagesEl.children.length === 0) {
        showWelcome();
      }
      // Only focus input if it's visible
      if (inputArea && inputArea.style.display !== "none" && inputEl) {
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
      if (container) {
        container.classList.add("visible");
      }
      if (toggleBtn) {
        toggleBtn.classList.add("open");
      }
    }
  }

  /** Close chat */
  function closeChat() {
    if (isOpen) {
      isOpen = false;
      if (container) {
        container.classList.remove("visible");
      }
      if (toggleBtn) {
        toggleBtn.classList.remove("open");
      }
      // Stop speech when closing
      stopSpeech();
    }
  }

  function openFullscreenChat() {
    // Open the full admissions site (chat embedded) in a new tab
    try {
      const target = window.location.origin + '/?fullscreen=true';
      window.open(target, "_blank", "noopener,noreferrer");
    } catch (err) {
      // Fallback to root if constructing origin fails
      window.open('/?fullscreen=true', "_blank", "noopener,noreferrer");
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
      "Management process? (Category-B and NRI)",
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

  async function showWelcome() {
    console.log("showWelcome called, languageSelected:", languageSelected);

    if (!languagesConfigLoaded) {
      await fetchEnabledLanguages();
    }
    
    // Show language selector if not yet selected
    if (!languageSelected) {
      console.log("Showing language selector");
      showLanguageSelector();

    if (micBtn) {
      micBtn.style.display = micEnabled ? "flex" : "none";
      micBtn.disabled = !micEnabled;
      if (!micEnabled) {
        micBtn.title = "Voice input disabled";
      }
    }
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
    hideInputArea();
  }

  /** Show language selector on first interaction */
  function showLanguageSelector() {
    console.log("showLanguageSelector called");
    addBotMessage(t("language_prompt"));
    
    // Hide input area when showing language selector
    hideInputArea();
    
    const wrapper = document.createElement("div");
    wrapper.className = "message bot";

    const grid = document.createElement("div");
    grid.className = "language-buttons";
    grid.style.cssText = "display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; max-width: 300px;";

    // Use enabled languages if available, otherwise fall back to all supported languages
    const langsToShow = enabledLanguagesConfig && Object.keys(enabledLanguagesConfig).length > 0 
      ? enabledLanguagesConfig 
      : SUPPORTED_LANGUAGES;

    Object.entries(langsToShow).forEach(([code, info]) => {
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
    
    console.log("Language selector displayed with", Object.keys(langsToShow).length, "languages");
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
    setTTSButtonVisualState(ttsBtn, false);
    
    // Check if browser supports Speech Synthesis
    if (!('speechSynthesis' in window)) {
      ttsBtn.disabled = true;
      ttsBtn.title = t("tts_not_supported");
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
        // Stop any other speech first, then speak immediately so browser
        // still treats this as a direct user gesture.
        stopSpeech();
        speakText(text, ttsBtn);
      }
    });
    
    return ttsBtn;
  }
  
  /**
   * Convert text to speech with improved error handling and speech-safe normalization.
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
      
      // Normalize response text into a voice-friendly format.
      let cleanText = normalizeSpeechText(text, currentLanguage);
      
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
      
      // Detect language dynamically from response text first.
      const detectedLang = detectLanguageFromText(cleanText);
      const localeCandidates = TTS_LANG_TO_LOCALES[detectedLang] || [];
      const targetLang = localeCandidates[0] || `${detectedLang || "en"}`;
      utterance.lang = targetLang;
      
      console.log("🔊 TTS Details:");
      console.log("  - UI Language:", currentLanguage);
      console.log("  - Detected Text Language:", detectedLang);
      console.log("  - Preferred Utterance Lang:", targetLang);
      console.log("  - Text Preview:", cleanText.substring(0, 50) + "...");
      
      // Get available voices and try to use dynamic language selection.
      const voices = updateAvailableVoices();
      console.log("  - Available voices:", voices.length);
      
      const matchingVoice = getVoiceForLang(detectedLang);
      
      if (matchingVoice) {
        utterance.voice = matchingVoice;
        utterance.lang = matchingVoice.lang || targetLang;
        console.log("  - Using voice:", matchingVoice.name, "(" + matchingVoice.lang + ")");
      } else {
        console.warn("  - ⚠️ No matching voice found for", targetLang);
        console.warn("  - Available voice languages:", voices.map(v => v.lang).join(", "));
        const fallbackVoice = voices.find((voice) => voice.default) || voices[0];
        if (fallbackVoice) {
          utterance.voice = fallbackVoice;
          utterance.lang = fallbackVoice.lang || "en-US";
          console.log("  - Using fallback voice:", fallbackVoice.name, "(" + fallbackVoice.lang + ")");
        } else {
          console.warn("  - No voice list available yet, browser default will be used");
        }
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
          setTTSButtonVisualState(buttonElement, true);
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
        // Some browsers can get stuck in paused state; resume before speaking.
        window.speechSynthesis.resume();
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
   * Reset speech state and button UI
   */
  function resetSpeechState(buttonElement) {
    isSpeaking = false;
    currentSpeech = null;
    
    if (buttonElement && buttonElement.classList) {
      buttonElement.classList.remove("playing");
      setTTSButtonVisualState(buttonElement, false);
    }
    
    // Reset all TTS buttons as safety measure
    try {
      document.querySelectorAll('.tts-button.playing').forEach(btn => {
        btn.classList.remove('playing');
        setTTSButtonVisualState(btn, false);
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
      // Reset state immediately so next click can start speech reliably.
      resetSpeechState(null);
      
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
      console.warn("🎤 Speech Recognition not supported in this browser");
      if (micBtn) {
        micBtn.disabled = true;
        micBtn.title = t("stt_not_supported");
      }
      return;
    }
    
    console.log("🎤 Initializing Speech Recognition...");
    recognition = new SpeechRecognition();
    
    // CRITICAL: Set these to true for continuous listening with real-time feedback
    // Setting to false initially can prevent proper speech capture in some browsers
    recognition.continuous = true;
    recognition.interimResults = true;
    
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
      console.log("🎤 Speech recognition started successfully");
      console.log("🎤 Language:", recognition.lang);
      console.log("🎤 Continuous mode:", recognition.continuous);
      console.log("🎤 Interim results:", recognition.interimResults);
      updateListeningUI(true);
      resetAutoStopTimer();
    };
    
    recognition.onresult = function(event) {
      console.log("🎤 onresult event triggered");
      console.log("🎤 Results count:", event.results.length);
      console.log("🎤 Result index:", event.resultIndex);
      
      let finalTranscript = '';
      let interimTranscript = '';
      
      // Process all results
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcript = result[0].transcript;
        const confidence = result[0].confidence;
        
        console.log(`🎤 Result ${i}: isFinal=${result.isFinal}, confidence=${confidence}, text="${transcript}"`);
        
        if (result.isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }
      
      // Reset auto-stop timer when we get any speech activity
      if (finalTranscript || interimTranscript) {
        resetAutoStopTimer();
      }
      
      console.log("🎤 Final transcript:", finalTranscript || "(none)");
      console.log("🎤 Interim transcript:", interimTranscript || "(none)");
      
      // Update input field with results
      if (inputEl) {
        if (finalTranscript) {
          const normalizedFinal = normalizeUserInput(finalTranscript);
          if (normalizedFinal && normalizedFinal !== lastTranscript) {
            sttCommittedTranscript = mergeUniqueTranscript(sttCommittedTranscript, normalizedFinal);
            inputEl.value = sttCommittedTranscript;
            lastTranscript = normalizedFinal;
          }
          
          // Clear interim styling
          inputEl.style.fontStyle = '';
          inputEl.style.opacity = '';
          
          // Continue listening for more speech
          showListeningStatus(t("stt_listening_more"));
          
        } else if (interimTranscript) {
          // Show interim results with visual indication
          const interimValue = mergeUniqueTranscript(sttCommittedTranscript, interimTranscript);
          inputEl.value = interimValue;
          
          // Style interim text
          inputEl.style.fontStyle = 'italic';
          inputEl.style.opacity = '0.8';
          
          showListeningStatus(t("stt_listening"));
        }
      }
    };
    
    recognition.onerror = function(event) {
      console.error("🎤 Speech recognition error event:", event);
      console.error("🎤 Error type:", event.error);
      console.error("🎤 Error message:", event.message || "No message provided");
      
      let errorMessage = "Speech recognition error";
      
      // Handle specific errors with user-friendly messages
      switch (event.error) {
        case 'no-speech':
          // Don't treat no-speech as error in continuous mode
          console.log("🎤 No speech detected (normal in continuous mode)");
          return; // Don't stop listening
        case 'audio-capture':
          errorMessage = "Microphone not available. Please check your microphone connection.";
          console.error("🎤 Audio capture failed - microphone may not be available or in use");
          break;
        case 'not-allowed':
          errorMessage = "Microphone permission denied. Please allow microphone access.";
          console.error("🎤 Microphone permission denied by user or browser");
          break;
        case 'network':
          errorMessage = "Network error. Check your internet connection.";
          console.error("🎤 Network error - speech recognition requires internet connection");
          break;
        case 'aborted':
          // Normal when user stops
          console.log("🎤 Recognition aborted (normal user action)");
          return;
        case 'service-not-allowed':
          errorMessage = "Speech recognition service not allowed. Check browser settings.";
          console.error("🎤 Speech recognition service not allowed");
          break;
        default:
          errorMessage = `Recognition error: ${event.error}`;
          console.error("🎤 Unhandled error type:", event.error);
      }
      
      console.warn("🎤 Displaying error to user:", errorMessage);
      showListeningStatus("❌ " + errorMessage);
      
      // Stop listening on real errors
      setTimeout(() => stopListening(), 3000);
    };
    
    recognition.onend = function() {
      console.log("🎤 Speech recognition ended");
      console.log("🎤 isListening state:", isListening);
      updateListeningUI(false);
      clearAutoStopTimer();
    };
  }
  
  /**
   * Start/Stop speech recognition with continuous listening and auto-stop
   */
  function toggleSpeechRecognition() {
    console.log("🎤 toggleSpeechRecognition called, current isListening:", isListening);
    
    if (!recognition) {
      console.log("🎤 Recognition not initialized, initializing now...");
      initSpeechRecognition();
      if (!recognition) {
        console.error("🎤 Failed to initialize recognition - browser may not support it");
        return; // Still no support
      }
    }
    
    if (isListening) {
      // Stop listening
      console.log("🎤 Currently listening, stopping...");
      stopListening();
    } else {
      // Start continuous listening
      console.log("🎤 Not listening, starting continuous listening...");
      startContinuousListening();
    }
  }
  
  /**
   * Start continuous speech recognition with auto-stop
   */
  function startContinuousListening() {
    if (!recognition) {
      console.error("🎤 Cannot start: recognition object not initialized");
      return;
    }
    
    console.log("🎤 Starting continuous listening...");
    
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
    
    console.log("🎤 Setting language to:", recognition.lang);
    
    // Configure for continuous listening
    recognition.continuous = true;
    recognition.interimResults = true;
    sttCommittedTranscript = normalizeUserInput(inputEl?.value || "");
    lastTranscript = "";
    
    console.log("🎤 Configuration set - continuous:", recognition.continuous, ", interimResults:", recognition.interimResults);
    
    // Update UI to listening state (without changing icon)
    updateListeningUI(true);
    
    // Start auto-stop timer
    startAutoStopTimer();
    
    // Start recognition
    try {
      console.log("🎤 Calling recognition.start()...");
      recognition.start();
      console.log("🎤 recognition.start() called successfully");
    } catch (error) {
      console.error("🎤 Failed to start recognition:", error);
      console.error("🎤 Error name:", error.name);
      console.error("🎤 Error message:", error.message);
      
      // Recognition might already be running, try to stop and restart
      console.log("🎤 Attempting to stop and restart...");
      recognition.stop();
      setTimeout(() => {
        try {
          console.log("🎤 Retrying recognition.start()...");
          recognition.start();
          console.log("🎤 Retry successful");
        } catch (e) {
          console.error("🎤 Retry failed:", e);
          updateListeningUI(false);
          showListeningStatus(`❌ ${t("stt_error_start")}`);
        }
      }, 100);
    }
  }
  
  /**
   * Stop speech recognition
   */
  function stopListening() {
    if (!recognition) {
      console.warn("🎤 Cannot stop: recognition object not initialized");
      return;
    }
    
    console.log("🎤 Stopping speech recognition...");
    recognition.stop();
    updateListeningUI(false);
    clearAutoStopTimer();
    lastTranscript = "";
    if (inputEl) {
      sttCommittedTranscript = normalizeUserInput(inputEl.value || "");
      inputEl.value = sttCommittedTranscript;
    }
    console.log("🎤 Speech recognition stopped");
  }
  
  /**
   * Auto-stop timer management
   */
  let autoStopTimer = null;
  let lastSpeechTime = null;
  const AUTO_STOP_DELAY = 4000; // 4 seconds of silence
  
  function startAutoStopTimer() {
    lastSpeechTime = Date.now();
    console.log("🎤 Auto-stop timer started");
    
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
      console.log("🎤 Clearing auto-stop timer");
      clearInterval(autoStopTimer);
      autoStopTimer = null;
    }
  }
  
  function resetAutoStopTimer() {
    lastSpeechTime = Date.now();
    console.log("🎤 Auto-stop timer reset");
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
      showListeningStatus(t("stt_listening"));
      
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

  async function returnToHome() {
    // Stop any speech and listening
    stopSpeech();
    stopListening();
    hideTyping();

    const previousSessionId = sessionId;

    const resetPromise = fetch(`${API_BASE}/api/chat/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "home",
        session_id: previousSessionId,
        language: currentLanguage,
      }),
    }).catch((error) => {
      console.error("Failed to reset chat session:", error);
    });

    sessionId = generateId();
    sessionStorage.setItem("chatbot_session", sessionId);
    chatHistory.length = 0;
    
    // Clear visual messages
    messagesEl.innerHTML = "";
    
    // Hide input area
    hideInputArea();
    if (inputEl) {
      inputEl.value = "";
      inputEl.disabled = false;
    }
    if (sendBtn) {
      sendBtn.disabled = false;
    }
    
    // Show welcome screen
    showWelcome();

    await resetPromise;
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
        } else if (enKey === "Fee Structure & Scholarships") {
          // Step 1 of guided fee flow before asking program
          showFeeTypeMenu();
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
      addBotMessage(t("type_question_prompt"));
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
        showProgramMenu((program) => {
          const queryKey = key === "admission_type_process"
            ? "admission_query_process"
            : "admission_query_eligibility";
          const query = t(queryKey).replace("{program}", program);
          sendMessage(query, true);
        });
      });
      qr.appendChild(btn);
    });

    wrapper.appendChild(qr);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
  }

  /**
   * Shared guided flow step
   * Ask which program (B.Tech / M.Tech / MCA), then run the provided callback.
   */
  function showProgramMenu(onProgramSelected) {
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
        onProgramSelected(program);
      });
      qr.appendChild(btn);
    });

    wrapper.appendChild(qr);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
  }

  /**
   * Guided fee flow – Step 1
   * Ask whether user wants Fee Structure or Scholarships.
   */
  function showFeeTypeMenu() {
    addBotMessage(t("fees_sub_prompt"));

    const wrapper = document.createElement("div");
    wrapper.className = "message bot";

    const qr = document.createElement("div");
    qr.className = "quick-replies";

    ["fees_type_structure", "fees_type_scholarships"].forEach((key) => {
      const btn = document.createElement("button");
      btn.textContent = t(key);
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        wrapper.remove();
        addUserMessage(t(key));
        showProgramMenu((program) => {
          const queryKey = key === "fees_type_structure"
            ? "fees_query_structure"
            : "fees_query_scholarships";
          const query = t(queryKey).replace("{program}", program);
          sendMessage(query, true);
        });
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
    if (inputEl) {
      inputEl.disabled = false;
    }
    if (sendBtn) {
      sendBtn.disabled = false;
    }
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
    const guidedBackOptionValue = "__guided_previous_option__";

    options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.className = "option-button";
      btn.textContent = opt.label;

      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        // Remove all option buttons after selection
        optionsContainer.remove();
        // Show friendly user text for back-action while preserving backend token.
        if (opt.value === guidedBackOptionValue) {
          addUserMessage("Back");
          sendMessage(opt.value, true, {
            selectedOptionLabel: opt.label,
            selectedOptionValue: opt.value,
          });
          return;
        }

        // Send the internal value plus visible label so backend can preserve display-language context.
        sendMessage(opt.value, false, {
          selectedOptionLabel: opt.label,
          selectedOptionValue: opt.value,
        });
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
  function hideInputArea() {
    if (inputArea) {
      inputArea.style.display = "none";
    }
  }

  function showInputArea() {
    if (!inputArea) {
      return;
    }

    inputArea.style.display = "";
    if (micBtn) {
      micBtn.style.display = micEnabled ? "flex" : "none";
      micBtn.disabled = !micEnabled;
    }
    // Focus on input field when shown (if chat is open)
    if (isOpen && inputEl) {
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

  async function sendMessage(text, skipAddingUserMessage = false, optionMeta = null) {
    if (!text || !text.trim() || isSending) return;

    const userText = normalizeUserInput(text);
    if (!userText) return;
    
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
      chatHistory.push({ role: "user", content: userText });

      // Use streaming endpoint for ChatGPT-style typing effect
      const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userText,
          session_id: sessionId,
          language: currentLanguage,
          force_language: languageSelected === true && !!optionMeta,
          selected_option_label: optionMeta?.selectedOptionLabel || null,
          selected_option_value: optionMeta?.selectedOptionValue || null,
          chat_history: chatHistory,
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
                if (data.metadata && data.metadata.language && SUPPORTED_LANGUAGES[data.metadata.language]) {
                  // Keep TTS/STT language aligned with backend-resolved response language.
                  if (currentLanguage !== data.metadata.language) {
                    setLanguage(data.metadata.language);
                  }
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

      if (fullReply && fullReply.trim()) {
        chatHistory.push({ role: "assistant", content: fullReply.trim() });
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

  // ── Detect Fullscreen Mode ───────────────────────────────────
  // Check if fullscreen=true parameter is in the URL
  const urlParams = new URLSearchParams(window.location.search);
  const isFullscreenMode = urlParams.get("fullscreen") === "true";

  if (isFullscreenMode) {
    // Hide the floating toggle button in fullscreen mode
    if (toggleBtn) {
      toggleBtn.style.display = "none";
    }
    // Hide the welcome popup in fullscreen mode
    if (welcomePopup) {
      welcomePopup.style.display = "none";
    }
    // Show the chat container immediately in fullscreen mode
    isOpen = true;
    container.classList.add("visible");

    // Keep the original onboarding flow in fullscreen mode.
    // This starts with language selection and category buttons.
    if (messagesEl && messagesEl.children.length === 0) {
      showWelcome();
    }
  }

  // ── Initialize Language Configuration ──────────────────────
  void fetchEnabledLanguages();

  // ── Event Listeners ──────────────────────────────────────────

  if (toggleBtn) {
    toggleBtn.addEventListener("click", toggleChat);
  }
  /* Close button removed — click handling via toggle and outside-click remains */

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
  
  if (homeBtn) {
    homeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      void returnToHome();
    });
  }

  if (fullscreenBtn) {
    fullscreenBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openFullscreenChat();
    });
  }
  
  if (micBtn) {
    if (!micEnabled) {
      micBtn.style.display = "none";
    }
    micBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!micEnabled) return;
      toggleSpeechRecognition();
    });
  }

  if (sendBtn) {
    sendBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      sendMessage(inputEl.value);
    });
  }

  if (inputEl) {
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage(inputEl.value);
      }
    });
  }

  // Close widget when clicking outside (improved to prevent accidental closures)
  document.addEventListener("click", (e) => {
    if (!isOpen) return;
    
    // Check if click is outside both the container and toggle button
    const clickedInsideContainer = container ? container.contains(e.target) : false;
    const clickedToggleBtn = toggleBtn ? toggleBtn.contains(e.target) : false;
    const clickedInsidePopup = welcomePopup && welcomePopup.contains(e.target);
    
    // Only close if click is truly outside all chat-related elements
    if (!clickedInsideContainer && !clickedToggleBtn && !clickedInsidePopup) {
      isOpen = false;
      if (container) {
        container.classList.remove("visible");
      }
      if (toggleBtn) {
        toggleBtn.classList.remove("open");
      }
    }
  });

  // ── Accessibility ────────────────────────────────────────────
  if (toggleBtn) {
    toggleBtn.setAttribute("aria-label", "Open chat");
  }
  /* chat-close element removed from DOM */
  
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
  if (micEnabled) {
    initSpeechRecognition();
  }
  
  // Initialize microphone with simple icon (no state changes)
  if (micBtn) {
    micBtn.innerHTML = '🎤';
    micBtn.title = "Click to start/stop voice input";
  }
  
  // ── Initialize Speech Synthesis Voices ───────────────────────
  // Load all voices on page load (some browsers load lazily)
  if (window.speechSynthesis) {
    updateAvailableVoices();
    console.log("🔊 Initial voices loaded:", availableVoices.length);

    window.speechSynthesis.onvoiceschanged = () => {
      updateAvailableVoices();
      console.log("🔊 Voices updated:", availableVoices.length);
      if (availableVoices.length > 0) {
        console.log("  - Languages available:", [...new Set(availableVoices.map((v) => v.lang))].join(", "));
      }
    };

    // Extra delayed refresh for browsers that populate voices asynchronously.
    setTimeout(() => {
      updateAvailableVoices();
      console.log("🔊 Delayed voice refresh:", availableVoices.length);
    }, 500);
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

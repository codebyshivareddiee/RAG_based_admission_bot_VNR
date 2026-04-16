"""
Language configuration and translation utilities for multilingual chatbot.
Supports English, Hindi, Telugu, Tamil, Marathi, Kannada, and more.
"""

from typing import Dict, List, Optional
import re

# Supported languages configuration
SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "native": "English", "flag": "🇬🇧"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "flag": "🇮🇳"},
    "te": {"name": "Telugu", "native": "తెలుగు", "flag": "🇮🇳"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "flag": "🇮🇳"},
    "mr": {"name": "Marathi", "native": "मराठी", "flag": "🇮🇳"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "flag": "🇮🇳"},
    "bn": {"name": "Bengali", "native": "বাংলা", "flag": "🇮🇳"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "flag": "🇮🇳"},
}

DEFAULT_LANGUAGE = "en"

# UI Translations for all supported languages
TRANSLATIONS = {
    # Welcome messages
    "welcome_title": {
        "en": "Hello! 👋 Welcome to the **VNRVJIET** assistant.",
        "hi": "नमस्ते! 👋 **VNRVJIET** सहायक में आपका स्वागत है।",
        "te": "నమస్కారం! 👋 **VNRVJIET** సహాయకునికి స్వాగతం।",
        "ta": "வணக்கம்! 👋 **VNRVJIET** உதவியாளருக்கு வரவேற்கிறோம்.",
        "mr": "नमस्कार! 👋 **VNRVJIET** सहाय्यकांमध्ये आपले स्वागत आहे.",
        "kn": "ನಮಸ್ಕಾರ! 👋 **VNRVJIET** ಸಹಾಯಕನಿಗೆ ಸ್ವಾಗತ.",
        "bn": "নমস্কার! 👋 **VNRVJIET** সহায়কে স্বাগতম।",
        "gu": "નમસ્તે! 👋 **VNRVJIET** સહાયકમાં આપનું સ્વાગત છે.",
    },
    "welcome_select_topic": {
        "en": "I can help you with the following topics. Please select one:",
        "hi": "मैं निम्नलिखित विषयों में आपकी मदद कर सकता/सकती हूं। कृपया एक चुनें:",
        "te": "నేను ఈ క్రింది అంశాలలో మీకు సహాయం చేయగలను. దయచేసి ఒకదాన్ని ఎంచుకోండి:",
        "ta": "நான் பின்வரும் தலைப்புகளில் உங்களுக்கு உதவ முடியும். தயவுசெய்து ஒன்றைத் தேர்ந்தெடுக்கவும்:",
        "mr": "मी खालील विषयांमध्ये तुमची मदत करू शकतो. कृपया एक निवडा:",
        "kn": "ನಾನು ಈ ಕೆಳಗಿನ ವಿಷಯಗಳಲ್ಲಿ ನಿಮಗೆ ಸಹಾಯ ಮಾಡಬಹುದು. ದಯವಿಟ್ಟು ಒಂದನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
        "bn": "আমি নিম্নলিখিত বিষয়গুলিতে আপনাকে সাহায্য করতে পারি। দয়া করে একটি নির্বাচন করুন:",
        "gu": "હું નીચેના વિષયોમાં તમારી મદદ કરી શકું છું. કૃપા કરીને એક પસંદ કરો:",
    },
    "language_selection_prompt": {
        "en": "Please select your preferred language:",
        "hi": "कृपया अपनी पसंदीदा भाषा चुनें:",
        "te": "దయచేసి మీ ఇష్ట భాషను ఎంచుకోండి:",
        "ta": "உங்களுக்கு விருப்பமான மொழியைத் தேர்ந்தெடுக்கவும்:",
        "mr": "कृपया तुमची पसंतीची भाषा निवडा:",
        "kn": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಆದ್ಯತೆಯ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
        "bn": "দয়া করে আপনার পছন্দের ভাষা নির্বাচন করুন:",
        "gu": "કૃપા કરીને તમારી પસંદગીની ભાષા પસંદ કરો:",
    },
    "language_changed": {
        "en": "Language changed to English. How can I help you?",
        "hi": "भाषा हिन्दी में बदल गई। मैं आपकी कैसे मदद कर सकता/सकती हूं?",
        "te": "భాష తెలుగుకు మార్చబడింది. నేను మీకు ఎలా సహాయపడగలను?",
        "ta": "மொழி தமிழுக்கு மாற்றப்பட்டது. நான் எப்படி உதவ முடியும்?",
        "mr": "भाषा मराठीमध्ये बदलली. मी तुमची कशी मदत करू शकतो?",
        "kn": "ಭಾಷೆಯನ್ನು ಕನ್ನಡಕ್ಕೆ ಬದಲಿಸಲಾಗಿದೆ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
        "bn": "ভাষা বাংলায় পরিবর্তিত হয়েছে। আমি কিভাবে সাহায্য করতে পারি?",
        "gu": "ભાષા ગુજરાતીમાં બદલાઈ છે. હું તમારી કેવી રીતે મદદ કરી શકું?",
    },
    # Category names
    "category_admission": {
        "en": "Admission Process & Eligibility",
        "hi": "प्रवेश प्रक्रिया और पात्रता",
        "te": "ప్రవేశ ప్రక్రియ & అర్హత",
        "ta": "சேர்க்கை செயல்முறை & தகுதி",
        "mr": "प्रवेश प्रक्रिया आणि पात्रता",
        "kn": "ಪ್ರವೇಶ ಪ್ರಕ್ರಿಯೆ ಮತ್ತು ಅರ್ಹತೆ",
        "bn": "ভর্তি প্রক্রিয়া এবং যোগ্যতা",
        "gu": "પ્રવેશ પ્રક્રિયા અને લાયકાત",
    },
    "category_cutoff": {
        "en": "Branch-wise Cutoff Ranks",
        "hi": "शाखा-वार कटऑफ रैंक",
        "te": "బ్రాంచ్-వారీ కటాఫ్ ర్యాంక్‌లు",
        "ta": "கிளை வாரியான கட்ஆஃப் தரவரிசை",
        "mr": "शाखा-निहाय कटऑफ रॅंक",
        "kn": "ಶಾಖೆಯ ಪ್ರಕಾರ ಕಟ್‌ಆಫ್ ಶ್ರೇಣಿಗಳು",
        "bn": "শাখা-ভিত্তিক কাট অফ র‍্যাঙ্ক",
        "gu": "શાખા મુજબ કટઓફ રેન્ક",
    },
    "category_documents": {
        "en": "Required Documents",
        "hi": "आवश्यक दस्तावेज",
        "te": "అవసరమైన పత్రాలు",
        "ta": "தேவையான ஆவணங்கள்",
        "mr": "आवश्यक कागदपत्रे",
        "kn": "ಅಗತ್ಯ ದಾಖಲೆಗಳು",
        "bn": "প্রয়োজনীয় নথিপত্র",
        "gu": "જરૂરી દસ્તાવેજો",
    },
    "category_fees": {
        "en": "Fee Structure & Scholarships",
        "hi": "शुल्क संरचना और छात्रवृत्ति",
        "te": "ఫీజు నిర్మాణం & స్కాలర్‌షిప్‌లు",
        "ta": "கட்டணம் & உதவித்தொகை",
        "mr": "फी रचना आणि शिष्यवृत्ती",
        "kn": "ಶುಲ್ಕ ರಚನೆ ಮತ್ತು ವಿದ್ಯಾರ್ಥಿವೇತನ",
        "bn": "ফি কাঠামো এবং বৃত্তি",
        "gu": "ફી માળખું અને શિષ્યવૃત્તિ",
    },
    "category_others": {
        "en": "Others",
        "hi": "अन्य",
        "te": "ఇతరములు",
        "ta": "மற்றவை",
        "mr": "इतर",
        "kn": "ಇತರೆ",
        "bn": "অন্যান্য",
        "gu": "અન્ય",
    },
    # Input placeholder
    "input_placeholder": {
        "en": "Ask about admissions...",
        "hi": "प्रवेश के बारे में पूछें...",
        "te": "ప్రవేశాల గురించి అడగండి...",
        "ta": "சேர்க்கை பற்றி கேளுங்கள்...",
        "mr": "प्रवेशाबद्दल विचारा...",
        "kn": "ಪ್ರವೇಶದ ಬಗ್ಗೆ ಕೇಳಿ...",
        "bn": "ভর্তি সম্পর্কে জিজ্ঞাসা করুন...",
        "gu": "પ્રવેશ વિશે પૂછો...",
    },
    # Error messages
    "error_connection": {
        "en": "Sorry, I'm having trouble connecting right now. Please try again in a moment.",
        "hi": "क्षमा करें, मुझे अभी कनेक्ट करने में समस्या हो रही है। कृपया कुछ देर बाद पुनः प्रयास करें।",
        "te": "క్షమించండి, నాకు ఇప్పుడు కనెక్ట్ చేయడంలో సమస్య ఉంది. దయచేసి కొద్దిసేపటి తర్వాత మళ్లీ ప్రయత్నించండి।",
        "ta": "மன்னிக்கவும், இப்போது இணைப்பதில் சிக்கல் உள்ளது. சிறிது நேரம் கழித்து மீண்டும் முயற்சிக்கவும்.",
        "mr": "क्षमस्व, मला आत्ता कनेक्ट होण्यात समस्या येत आहे. कृपया काही वेळाने पुन्हा प्रयत्न करा.",
        "kn": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಈಗ ಸಂಪರ್ಕ ಸಾಧಿಸುವಲ್ಲಿ ತೊಂದರೆ ಇದೆ. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
        "bn": "দুঃখিত, আমার এখন সংযোগে সমস্যা হচ্ছে। অনুগ্রহ করে কিছুক্ষণ পরে আবার চেষ্টা করুন।",
        "gu": "માફ કરશો, મને અત્યારે જોડાવામાં મુશ્કેલી આવી રહી છે. કૃપા કરીને થોડીવાર પછી ફરી પ્રયાસ કરો.",
    },
    "rate_limit": {
        "en": "You're sending messages too quickly. Please wait a moment and try again.",
        "hi": "आप बहुत जल्दी संदेश भेज रहे हैं। कृपया प्रतीक्षा करें और पुनः प्रयास करें।",
        "te": "మీరు చాలా త్వరగా సందేశాలు పంపుతున్నారు. దయచేసి కాసేపు వేచి ఉండి మళ్లీ ప్రయత్నించండి।",
        "ta": "நீங்கள் மிக விரைவாக செய்திகளை அனுப்புகிறீர்கள். சிறிது நேரம் காத்திருந்து மீண்டும் முயற்சிக்கவும்.",
        "mr": "तुम्ही खूप वेगाने संदेश पाठवत आहात. कृपया थांबा आणि पुन्हा प्रयत्न करा.",
        "kn": "ನೀವು ತುಂಬಾ ವೇಗವಾಗಿ ಸಂದೇಶಗಳನ್ನು ಕಳುಹಿಸುತ್ತಿದ್ದೀರಿ. ದಯವಿಟ್ಟು ಕಾಯಿರಿ ಮತ್ತು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
        "bn": "আপনি খুব দ্রুত বার্তা পাঠাচ্ছেন। অনুগ্রহ করে অপেক্ষা করুন এবং আবার চেষ্টা করুন।",
        "gu": "તમે ખૂબ ઝડપથી સંદેશા મોકલી રહ્યા છો. કૃપા કરીને રાહ જુઓ અને ફરી પ્રયાસ કરો.",
    },
    # Change language command
    "change_language_text": {
        "en": "🌐 Change Language",
        "hi": "🌐 भाषा बदलें",
        "te": "🌐 భాష మార్చండి",
        "ta": "🌐 மொழியை மாற்றவும்",
        "mr": "🌐 भाषा बदला",
        "kn": "🌐 ಭಾಷೆಯನ್ನು ಬದಲಿಸಿ",
        "bn": "🌐 ভাষা পরিবর্তন করুন",
        "gu": "🌐 ભાષા બદલો",
    },
}

# Cutoff-specific label translations
CUTOFF_LABELS = {
    "branch": {
        "en": "Branch",
        "hi": "शाखा",
        "te": "శాఖ",
        "ta": "கிளை",
        "mr": "शाखा",
        "kn": "ಶಾಖೆ",
        "bn": "শাখা",
        "gu": "શાખા",
    },
    "category": {
        "en": "Category",
        "hi": "श्रेणी",
        "te": "వర్గం",
        "ta": "வகை",
        "mr": "प्रवर्ग",
        "kn": "ವರ್ಗ",
        "bn": "বিভাগ",
        "gu": "શ્રેણી",
    },
    "gender": {
        "en": "Gender",
        "hi": "लिंग",
        "te": "లింగం",
        "ta": "பாலினம்",
        "mr": "लिंग",
        "kn": "ಲಿಂಗ",
        "bn": "লিঙ্গ",
        "gu": "લિંગ",
    },
    "boys": {
        "en": "Boys",
        "hi": "लड़के",
        "te": "అబ్బాయిలు",
        "ta": "ஆண்கள்",
        "mr": "मुले",
        "kn": "ಹುಡುಗರು",
        "bn": "ছেলে",
        "gu": "છોકરાઓ",
    },
    "girls": {
        "en": "Girls",
        "hi": "लड़कियां",
        "te": "అమ్మాయిలు",
        "ta": "பெண்கள்",
        "mr": "मुली",
        "kn": "ಹುಡುಗಿಯರು",
        "bn": "মেয়ে",
        "gu": "છોકરીઓ",
    },
    "quota": {
        "en": "Quota",
        "hi": "कोटा",
        "te": "కోటా",
        "ta": "ஒதுக்கீடு",
        "mr": "कोटा",
        "kn": "ಕೋಟಾ",
        "bn": "কোটা",
        "gu": "કોટા",
    },
    "convenor": {
        "en": "Convenor",
        "hi": "कन्वीनर",
        "te": "కన్వీనర్",
        "ta": "கன்வீனர்",
        "mr": "कन्व्हीनर",
        "kn": "ಸಂಚಾಲಕ",
        "bn": "কনভিনার",
        "gu": "કન્વીનર",
    },
    "management": {
        "en": "Management",
        "hi": "मैनेजमेंट",
        "te": "మేనేజ్‌మెంట్",
        "ta": "நிர்வாகம்",
        "mr": "व्यवस्थापन",
        "kn": "ನಿರ್ವಹಣೆ",
        "bn": "ম্যানেজমেন্ট",
        "gu": "સંચાલન",
    },
    "round": {
        "en": "Round",
        "hi": "राउंड",
        "te": "రౌండ్",
        "ta": "சுற்று",
        "mr": "फेरी",
        "kn": "ಸುತ್ತು",
        "bn": "রাউন্ড",
        "gu": "રાઉન્ડ",
    },
    "first_rank_opening": {
        "en": "First Rank (Opening)",
        "hi": "प्रथम रैंक (ओपनिंग)",
        "te": "మొదటి ర్యాంక్ (ఓపెనింగ్)",
        "ta": "முதல் தரவரிசை (தொடக்கம்)",
        "mr": "प्रारंभिक रँक",
        "kn": "ಮೊದಲ ಶ್ರೇಣಿ (ಪ್ರಾರಂಭ)",
        "bn": "প্রথম র‍্যাঙ্ক (শুরু)",
        "gu": "પ્રથમ રેન્ક (શરૂઆત)",
    },
    "last_rank_closing": {
        "en": "Last Rank (Closing)",
        "hi": "अंतिम रैंक (क्लोजिंग)",
        "te": "చివరి ర్యాంక్ (క్లోజింగ్)",
        "ta": "கடைசி தரவரிசை (இறுதி)",
        "mr": "अंतिम रँक",
        "kn": "ಕೊನೆಯ ಶ್ರೇಣಿ (ಮುಕ್ತಾಯ)",
        "bn": "শেষ র‍্যাঙ্ক (সমাপ্তি)",
        "gu": "છેલ્લું રેન્ક (સમાપ્તિ)",
    },
    "cutoff_ranks": {
        "en": "Cutoff Ranks",
        "hi": "कटऑफ रैंक",
        "te": "కటాఫ్ ర్యాంక్‌లు",
        "ta": "கட்ஆஃப் தரவரிசை",
        "mr": "कटऑफ रँक",
        "kn": "ಕಟ್‌ಆಫ್ ಶ್ರೇಣಿಗಳು",
        "bn": "কাট অফ র‍্যাঙ্ক",
        "gu": "કટઓફ રેન્ક",
    },
    "eapcet_cutoff_ranks": {
        "en": "EAPCET Cutoff Ranks",
        "hi": "EAPCET कटऑफ रैंक",
        "te": "EAPCET కటాఫ్ ర్యాంక్‌లు",
        "ta": "EAPCET கட்ஆஃப் தரவரிசை",
        "mr": "EAPCET कटऑफ रँक",
        "kn": "EAPCET ಕಟ್‌ಆಫ್ ಶ್ರೇಣಿಗಳು",
        "bn": "EAPCET কাট অফ র‍্যাঙ্ক",
        "gu": "EAPCET કટઓફ રેન્ક",
    },
    "year": {
        "en": "Year",
        "hi": "वर्ष",
        "te": "సంవత్సరం",
        "ta": "ஆண்டு",
        "mr": "वर्ष",
        "kn": "ವರ್ಷ",
        "bn": "বছর",
        "gu": "વર્ષ",
    },
    "trend_analysis": {
        "en": "Trend Analysis",
        "hi": "रुझान विश्लेषण",
        "te": "ట్రెండ్ విశ్లేషణ",
        "ta": "போக்கு பகுப்பாய்வு",
        "mr": "ट्रेंड विश्लेषण",
        "kn": "ಪ್ರವೃತ್ತಿ ವಿಶ್ಲೇಷಣೆ",
        "bn": "ট্রেন্ড বিশ্লেষণ",
        "gu": "ટ્રેન્ડ વિશ્લેષણ",
    },
    "warning_previous_year": {
        "en": "WARNING: Based on previous year data. Cutoffs may vary.",
        "hi": "चेतावनी: पिछले वर्ष के डेटा पर आधारित। कटऑफ भिन्न हो सकते हैं।",
        "te": "హెచ్చరిక: మునుపటి సంవత్సర డేటా ఆధారంగా. కటాఫ్‌లు మారవచ్చు.",
        "ta": "எச்சரிக்கை: முந்தைய ஆண்டு தரவின் அடிப்படையில். கட்ஆஃப் மாறுபடலாம்.",
        "mr": "सूचना: मागील वर्षाच्या डेटावर आधारित. कटऑफ बदलू शकतात.",
        "kn": "ಎಚ್ಚರಿಕೆ: ಹಿಂದಿನ ವರ್ಷದ ಡೇಟಾವನ್ನು ಆಧರಿಸಿದೆ. ಕಟ್‌ಆಫ್‌ಗಳು ಬದಲಾಗಬಹುದು.",
        "bn": "সতর্কতা: পূর্ববর্তী বছরের ডেটার উপর ভিত্তি করে। কাট অফ পরিবর্তিত হতে পারে।",
        "gu": "ચેતવણી: પાછલા વર્ષના ડેટા પર આધારિત. કટઓફ બદલાઈ શકે છે.",
    },
    "explore_department": {
        "en": "Explore",
        "hi": "एक्सप्लोर करें",
        "te": "అన్వేషించండి",
        "ta": "ஆராயுங்கள்",
        "mr": "एक्सप्लोर करा",
        "kn": "ಅನ್ವೇಷಿಸಿ",
        "bn": "অন্বেষণ করুন",
        "gu": "અન્વેષણ કરો",
    },
    "department": {
        "en": "Department",
        "hi": "विभाग",
        "te": "విభాగం",
        "ta": "துறை",
        "mr": "विभाग",
        "kn": "ವಿಭಾಗ",
        "bn": "বিভাগ",
        "gu": "વિભાગ",
    },
    "data_not_found": {
        "en": "Data not found in Firestore for the specified filters",
        "hi": "निर्दिष्ट फ़िल्टर के लिए Firestore में डेटा नहीं मिला",
        "te": "పేర్కొన్న ఫిల్టర్‌ల కోసం Firestore లో డేటా కనుగొనబడలేదు",
        "ta": "குறிப்பிட்ட வடிப்பான்களுக்கான தரவு Firestore இல் கிடைக்கவில்லை",
        "mr": "निर्दिष्ट फिल्टरसाठी Firestore मध्ये डेटा आढळला नाही",
        "kn": "ನಿರ್ದಿಷ್ಟಪಡಿಸಿದ ಫಿಲ್ಟರ್‌ಗಳಿಗಾಗಿ Firestore ನಲ್ಲಿ ಡೇಟಾ ಕಂಡುಬಂದಿಲ್ಲ",
        "bn": "নির্দিষ্ট ফিল্টারের জন্য Firestore এ ডেটা পাওয়া যায়নি",
        "gu": "નિર્દિષ્ટ ફિલ્ટર્સ માટે Firestore માં ડેટા મળ્યો નથી",
    },
    "no_allotments": {
        "en": "No allotments recorded",
        "hi": "कोई आवंटन दर्ज नहीं",
        "te": "కేటాయింపులు నమోదు చేయబడలేదు",
        "ta": "ஒதுக்கீடு பதிவு செய்யப்படவில்லை",
        "mr": "कोणतेही वाटप नोंदवलेले नाही",
        "kn": "ಯಾವುದೇ ಹಂಚಿಕೆಗಳು ದಾಖಲಾಗಿಲ್ಲ",
        "bn": "কোনও বরাদ্দ রেকর্ড করা হয়নি",
        "gu": "કોઈ ફાળવણી નોંધાયેલ નથી",
    },
    "across_all_years": {
        "en": "across all available years",
        "hi": "सभी उपलब्ध वर्षों में",
        "te": "అందుబాటులో ఉన్న అన్ని సంవత్సరాలలో",
        "ta": "அனைத்து கிடைக்கக்கூடிய ஆண்டுகளிலும்",
        "mr": "सर्व उपलब्ध वर्षांमध्ये",
        "kn": "ಎಲ್ಲಾ ಲಭ್ಯವಿರುವ ವರ್ಷಗಳಲ್ಲಿ",
        "bn": "সব উপলব্ধ বছরে",
        "gu": "તમામ ઉપલબ્ધ વર્ષોમાં",
    },
}


def get_translation(key: str, language: str = DEFAULT_LANGUAGE) -> str:
    """
    Get translated text for a given key and language.
    Falls back to English if translation not found.
    """
    if key not in TRANSLATIONS:
        return key
    
    translations = TRANSLATIONS[key]
    return translations.get(language, translations.get(DEFAULT_LANGUAGE, key))


def detect_language(text: str) -> str:
    """
    Detect language from text using character ranges and common words.
    Returns language code (e.g., 'en', 'hi', 'te').
    """
    # Define character ranges for each language
    language_patterns = {
        "hi": r'[\u0900-\u097F]',      # Devanagari (Hindi, Marathi)
        "te": r'[\u0C00-\u0C7F]',      # Telugu
        "ta": r'[\u0B80-\u0BFF]',      # Tamil
        "kn": r'[\u0C80-\u0CFF]',      # Kannada
        "bn": r'[\u0980-\u09FF]',      # Bengali
        "gu": r'[\u0A80-\u0AFF]',      # Gujarati
        "mr": r'[\u0900-\u097F]',      # Marathi (shares Devanagari with Hindi)
    }
    
    # Check each language pattern
    for lang, pattern in language_patterns.items():
        if re.search(pattern, text):
            # For Devanagari (Hindi/Marathi), check for common words
            if lang == "hi":
                marathi_words = ["आहे", "आहेत", "आला", "येत", "होत", "काही", "कशी", "कसे"]
                if any(word in text for word in marathi_words):
                    return "mr"
                return "hi"
            return lang
    
    # Check for common language-specific words
    language_keywords = {
        "hi": ["है", "हैं", "के", "का", "की", "में", "को", "से", "पर", "और"],
        "te": ["లో", "కు", "ను", "తో", "యొక్క", "మరియు", "ఉంది", "ఉన్నారు"],
        "ta": ["உள்ளது", "இருக்கிறது", "மற்றும்", "என்று", "இல்லை"],
        "kn": ["ಇದೆ", "ಆಗಿದೆ", "ಮತ್ತು", "ಇಲ್ಲ", "ಹಾಗೂ"],
        "bn": ["আছে", "এবং", "থেকে", "করা", "হয়"],
        "gu": ["છે", "અને", "થી", "માટે", "નથી"],
        "mr": ["आहे", "आणि", "पासून", "साठी", "नाही"],
    }
    
    for lang, keywords in language_keywords.items():
        if any(keyword in text for keyword in keywords):
            return lang
    
    # Default to English
    return DEFAULT_LANGUAGE


def detect_language_change_request(text: str, current_language: str = DEFAULT_LANGUAGE) -> Optional[str]:
    """
    Detect if user is requesting to change language.
    Returns new language code if language change detected, None otherwise.
    """
    text_lower = text.lower().strip()
    
    # Language change keywords in different languages
    change_keywords = {
        "en": ["change language", "switch language", "language", "in hindi", "in telugu", 
               "in tamil", "in english", "speak hindi", "speak english", "speak telugu"],
        "hi": ["भाषा बदलो", "भाषा बदलें", "अंग्रेजी", "तेलुगु", "हिंदी"],
        "te": ["భాష మార్చండి", "ఇంగ్లీష్", "హిందీ", "తెలుగు"],
        "ta": ["மொழி மாற்று", "ஆங்கிலம்", "இந்தி", "தமிழ்"],
    }
    
    # Check if any change keyword is present
    for lang_keywords in change_keywords.values():
        if any(keyword in text_lower for keyword in lang_keywords):
            # Try to detect which language they want
            if any(word in text_lower for word in ["english", "अंग्रेजी", "ఇంగ్లీష్", "ஆங்கிலம்", "ઇંગ્લિશ"]):
                return "en"
            elif any(word in text_lower for word in ["hindi", "हिंदी", "हिन्दी", "హిందీ", "இந்தி"]):
                return "hi"
            elif any(word in text_lower for word in ["telugu", "తెలుగు", "তেলুগু", "తెలుగులో"]):
                return "te"
            elif any(word in text_lower for word in ["tamil", "தமிழ்", "तमिल", "తమిళ్"]):
                return "ta"
            elif any(word in text_lower for word in ["kannada", "ಕನ್ನಡ", "कन्नड़"]):
                return "kn"
            elif any(word in text_lower for word in ["marathi", "मराठी", "మరాఠీ"]):
                return "mr"
            elif any(word in text_lower for word in ["bengali", "বাংলা", "बंगाली"]):
                return "bn"
            elif any(word in text_lower for word in ["gujarati", "ગુજરાતી", "गुजराती"]):
                return "gu"
            # If no specific language mentioned, return None to show language selector
            return "show_selector"
    
    return None


def get_language_instruction(language: str) -> str:
    """
    Get instruction to add to system prompt for the specified language.
    """
    instructions = {
        "en": "Respond in English.",
        "hi": "हिन्दी में उत्तर दें। Respond completely in Hindi language.",
        "te": "తెలుగులో సమాధానం ఇవ్వండి। Respond completely in Telugu language.",
        "ta": "தமிழில் பதிலளிக்கவும். Respond completely in Tamil language.",
        "mr": "मराठीत उत्तर द्या। Respond completely in Marathi language.",
        "kn": "ಕನ್ನಡದಲ್ಲಿ ಉತ್ತರಿಸಿ। Respond completely in Kannada language.",
        "bn": "বাংলায় উত্তর দিন। Respond completely in Bengali language.",
        "gu": "ગુજરાતીમાં જવાબ આપો। Respond completely in Gujarati language.",
    }
    return instructions.get(language, instructions["en"])


def get_language_selector_message(current_language: str = DEFAULT_LANGUAGE) -> str:
    """
    Get the language selector message with options.
    """
    prompt = get_translation("language_selection_prompt", current_language)
    
    # Build language options
    options = []
    for code, info in SUPPORTED_LANGUAGES.items():
        options.append(f"{info['flag']} **{info['native']}** ({info['name']})")
    
    return f"{prompt}\n\n" + "\n".join(options)


def get_greeting_message(language: str = DEFAULT_LANGUAGE) -> str:
    """
    Get the full greeting/welcome message in the specified language.
    """
    greetings = {
        "en": (
            "Hello! 👋 Welcome to the **VNR Vignana Jyothi Institute of Engineering and Technology (VNRVJIET)** "
            "admissions assistant.\n\n"
            "I can help you with:\n"
            "• Admission process & eligibility\n"
            "• Branch-wise cutoff ranks\n"
            "• Required documents\n"
            "• Fee structure & scholarships\n"
            "• Campus & hostel information\n\n"
            "How can I assist you today?"
        ),
        "hi": (
            "नमस्ते! 👋 **VNR विज्ञान ज्योति इंजीनियरिंग और प्रौद्योगिकी संस्थान (VNRVJIET)** "
            "प्रवेश सहायक में आपका स्वागत है।\n\n"
            "मैं आपकी मदद कर सकता/सकती हूं:\n"
            "• प्रवेश प्रक्रिया और पात्रता\n"
            "• शाखा-वार कटऑफ रैंक\n"
            "• आवश्यक दस्तावेज\n"
            "• शुल्क संरचना और छात्रवृत्ति\n"
            "• परिसर और छात्रावास की जानकारी\n\n"
            "मैं आज आपकी कैसे मदद कर सकता/सकती हूं?"
        ),
        "te": (
            "నమస్కారం! 👋 **VNR విజ్ఞాన జ్యోతి ఇంజనీరింగ్ మరియు టెక్నాలజీ ఇన్‌స్టిట్యూట్ (VNRVJIET)** "
            "ప్రవేశ సహాయకునికి స్వాగతం.\n\n"
            "నేను మీకు సహాయం చేయగలను:\n"
            "• ప్రవేశ ప్రక్రియ & అర్హత\n"
            "• బ్రాంచ్-వారీ కటాఫ్ ర్యాంక్‌లు\n"
            "• అవసరమైన పత్రాలు\n"
            "• ఫీజు నిర్మాణం & స్కాలర్‌షిప్‌లు\n"
            "• క్యాంపస్ & హాస్టల్ సమాచారం\n\n"
            "నేను ఈరోజు మీకు ఎలా సహాయపడగలను?"
        ),
        "ta": (
            "வணக்கம்! 👋 **VNR விஞ்ஞான ஜோதி பொறியியல் மற்றும் தொழில்நுட்ப நிறுவனம் (VNRVJIET)** "
            "சேர்க்கை உதவியாளருக்கு வரவேற்கிறோம்.\n\n"
            "நான் உங்களுக்கு உதவ முடியும்:\n"
            "• சேர்க்கை செயல்முறை & தகுதி\n"
            "• கிளை வாரியான கட்ஆஃப் தரவரிசை\n"
            "• தேவையான ஆவணங்கள்\n"
            "• கட்டணம் & உதவித்தொகை\n"
            "• வளாகம் & விடுதி தகவல்\n\n"
            "இன்று நான் உங்களுக்கு எப்படி உதவ முடியும்?"
        ),
        "mr": (
            "नमस्कार! 👋 **VNR विज्ञान ज्योति अभियांत्रिकी आणि तंत्रज्ञान संस्था (VNRVJIET)** "
            "प्रवेश सहाय्यकांमध्ये आपले स्वागत आहे.\n\n"
            "मी तुमची मदत करू शकतो:\n"
            "• प्रवेश प्रक्रिया आणि पात्रता\n"
            "• शाखा-निहाय कटऑफ रॅंक\n"
            "• आवश्यक कागदपत्रे\n"
            "• फी रचना आणि शिष्यवृत्ती\n"
            "• कॅम्पस आणि वसतिगृह माहिती\n\n"
            "आज मी तुमची कशी मदत करू शकतो?"
        ),
        "kn": (
            "ನಮಸ್ಕಾರ! 👋 **VNR ವಿಜ್ಞಾನ ಜ್ಯೋತಿ ಇಂಜಿನಿಯರಿಂಗ್ ಮತ್ತು ತಂತ್ರಜ್ಞಾನ ಸಂಸ್ಥೆ (VNRVJIET)** "
            "ಪ್ರವೇಶ ಸಹಾಯಕನಿಗೆ ಸ್ವಾಗತ.\n\n"
            "ನಾನು ನಿಮಗೆ ಸಹಾಯ ಮಾಡಬಹುದು:\n"
            "• ಪ್ರವೇಶ ಪ್ರಕ್ರಿಯೆ ಮತ್ತು ಅರ್ಹತೆ\n"
            "• ಶಾಖೆಯ ಪ್ರಕಾರ ಕಟ್‌ಆಫ್ ಶ್ರೇಣಿಗಳು\n"
            "• ಅಗತ್ಯ ದಾಖಲೆಗಳು\n"
            "• ಶುಲ್ಕ ರಚನೆ ಮತ್ತು ವಿದ್ಯಾರ್ಥಿವೇತನ\n"
            "• ಕ್ಯಾಂಪಸ್ ಮತ್ತು ಹಾಸ್ಟೆಲ್ ಮಾಹಿತಿ\n\n"
            "ಇಂದು ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?"
        ),
        "bn": (
            "নমস্কার! 👋 **VNR বিজ্ঞান জ্যোতি প্রকৌশল ও প্রযুক্তি ইনস্টিটিউট (VNRVJIET)** "
            "ভর্তি সহায়কে স্বাগতম।\n\n"
            "আমি আপনাকে সাহায্য করতে পারি:\n"
            "• ভর্তি প্রক্রিয়া এবং যোগ্যতা\n"
            "• শাখা-ভিত্তিক কাট অফ র‍্যাঙ্ক\n"
            "• প্রয়োজনীয় নথিপত্র\n"
            "• ফি কাঠামো এবং বৃত্তি\n"
            "• ক্যাম্পাস ও হোস্টেল তথ্য\n\n"
            "আজ আমি আপনাকে কিভাবে সাহায্য করতে পারি?"
        ),
        "gu": (
            "નમસ્તે! 👋 **VNR વિજ્ઞાન જ્યોતિ ઇજનેરી અને ટેક્નોલોજી સંસ્થા (VNRVJIET)** "
            "પ્રવેશ સહાયકમાં આપનું સ્વાગત છે.\n\n"
            "હું તમારી મદદ કરી શકું છું:\n"
            "• પ્રવેશ પ્રક્રિયા અને લાયકાત\n"
            "• શાખા મુજબ કટઓફ રેન્ક\n"
            "• જરૂરી દસ્તાવેજો\n"
            "• ફી માળખું અને શિષ્યવૃત્તિ\n"
            "• કેમ્પસ અને હોસ્ટેલ માહિતી\n\n"
            "આજે હું તમારી કેવી રીતે મદદ કરી શકું?"
        ),
    }
    
    return greetings.get(language, greetings["en"])


def get_out_of_scope_message(language: str = DEFAULT_LANGUAGE) -> str:
    """
    Get the out-of-scope message in the specified language.
    """
    messages = {
        "en": (
            "I can assist only with admissions information related to **VNR Vignana Jyothi Institute of "
            "Engineering and Technology (VNRVJIET)**. "
            "For other colleges, please refer to their official websites or counselling authorities."
        ),
        "hi": (
            "मैं केवल **VNR विज्ञान ज्योति इंजीनियरिंग और प्रौद्योगिकी संस्थान (VNRVJIET)** से संबंधित "
            "प्रवेश जानकारी के लिए सहायता कर सकता/सकती हूं। "
            "अन्य कॉलेजों के लिए, कृपया उनकी आधिकारिक वेबसाइटों या परामर्श प्राधिकरणों को देखें।"
        ),
        "te": (
            "నేను **VNR విజ్ఞాన జ్యోతి ఇంజనీరింగ్ మరియు టెక్నాలజీ ఇన్‌స్టిట్యూట్ (VNRVJIET)** కు సంబంధించిన "
            "ప్రవేశ సమాచారంతో మాత్రమే సహాయం చేయగలను. "
            "ఇతర కళాశాలల కోసం, దయచేసి వారి అధికారిక వెబ్‌సైట్‌లు లేదా కౌన్సెలింగ్ అధికారులను సంప్రదించండి."
        ),
        "ta": (
            "நான் **VNR விஞ்ஞான ஜோதி பொறியியல் மற்றும் தொழில்நுட்ப நிறுவனம் (VNRVJIET)** தொடர்பான "
            "சேர்க்கை தகவல்களுக்கு மட்டுமே உதவ முடியும். "
            "பிற கல்லூரிகளுக்கு, அவர்களின் அதிகாரப்பூர்வ இணையதளங்கள் அல்லது ஆலோசனை அதிகாரிகளை பார்க்கவும்."
        ),
        "mr": (
            "मी फक्त **VNR विज्ञान ज्योति अभियांत्रिकी आणि तंत्रज्ञान संस्था (VNRVJIET)** संबंधित "
            "प्रवेश माहितीसाठी मदत करू शकतो। "
            "इतर महाविद्यालयांसाठी, कृपया त्यांच्या अधिकृत वेबसाइट किंवा समुपदेशन अधिकाऱ्यांना पहा."
        ),
        "kn": (
            "ನಾನು **VNR ವಿಜ್ಞಾನ ಜ್ಯೋತಿ ಇಂಜಿನಿಯರಿಂಗ್ ಮತ್ತು ತಂತ್ರಜ್ಞಾನ ಸಂಸ್ಥೆ (VNRVJIET)** ಗೆ ಸಂಬಂಧಿಸಿದ "
            "ಪ್ರವೇಶ ಮಾಹಿತಿಗೆ ಮಾತ್ರ ಸಹಾಯ ಮಾಡಬಹುದು. "
            "ಇತರ ಕಾಲೇಜುಗಳಿಗೆ, ದಯವಿಟ್ಟು ಅವರ ಅಧಿಕೃತ ವೆಬ್‌ಸೈಟ್‌ಗಳು ಅಥವಾ ಸಲಹಾ ಅಧಿಕಾರಿಗಳನ್ನು ನೋಡಿ."
        ),
        "bn": (
            "আমি শুধুমাত্র **VNR বিজ্ঞান জ্যোতি প্রকৌশল ও প্রযুক্তি ইনস্টিটিউট (VNRVJIET)** সম্পর্কিত "
            "ভর্তি তথ্যের জন্য সাহায্য করতে পারি। "
            "অন্যান্য কলেজের জন্য, অনুগ্রহ করে তাদের সরকারী ওয়েবসাইট বা পরামর্শ কর্তৃপক্ষের সাথে যোগাযোগ করুন।"
        ),
        "gu": (
            "હું માત્ર **VNR વિજ્ઞાન જ્યોતિ ઇજનેરી અને ટેક્નોલોજી સંસ્થા (VNRVJIET)** સંબંધિત "
            "પ્રવેશ માહિતી માટે મદદ કરી શકું છું. "
            "અન્ય કોલેજો માટે, કૃપા કરીને તેમની સત્તાવાર વેબસાઇટ્સ અથવા કાઉન્સેલિંગ સત્તાવાળાઓને જુઓ."
        ),
    }
    
    return messages.get(language, messages["en"])


def get_cutoff_label(label_key: str, language: str = DEFAULT_LANGUAGE) -> str:
    """
    Get translated cutoff label for a given key and language.
    
    Args:
        label_key: Key from CUTOFF_LABELS (e.g., 'branch', 'category', 'first_rank_opening')
        language: Target language code (e.g., 'en', 'hi', 'te', 'ta', 'mr', 'kn')
    
    Returns:
        Translated label string
    """
    if label_key not in CUTOFF_LABELS:
        return label_key  # Return key as-is if not found
    
    return CUTOFF_LABELS[label_key].get(language, CUTOFF_LABELS[label_key].get("en", label_key))


def format_gender_value(gender: str, language: str = DEFAULT_LANGUAGE) -> str:
    """
    Format gender value with translation.
    
    Args:
        gender: Gender value ('Boys', 'Girls', 'Any', etc.)
        language: Target language code
    
    Returns:
        Translated gender value
    """
    gender_lower = gender.lower()
    
    if gender_lower in ["boys", "male", "m"]:
        return get_cutoff_label("boys", language)
    elif gender_lower in ["girls", "female", "f"]:
        return get_cutoff_label("girls", language)
    else:
        return gender  # Return as-is for 'Any' or other values


def format_quota_value(quota: str, language: str = DEFAULT_LANGUAGE) -> str:
    """
    Format quota value with translation.
    
    Args:
        quota: Quota value ('Convenor', 'Management', etc.)
        language: Target language code
    
    Returns:
        Translated quota value
    """
    quota_lower = quota.lower()
    
    if quota_lower == "convenor":
        return get_cutoff_label("convenor", language)
    elif quota_lower == "management":
        return get_cutoff_label("management", language)
    else:
        return quota  # Return as-is for other values

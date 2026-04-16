"""
Chat API endpoint for VNRVJIET Admissions Chatbot.
Handles user queries with proper parameter extraction and intent classification.
"""

from __future__ import annotations

import logging
import re
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import json
import asyncio

from app.classifier.intent_classifier import classify, ClassificationResult, IntentType
from app.logic.cutoff_engine import get_cutoff
from app.rag.retriever import retrieve
from openai import AsyncOpenAI
from app.config import get_settings
from app.utils.languages import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    detect_language,
    detect_language_change_request,
    get_greeting_message,
    get_out_of_scope_message,
)

settings = get_settings()

_async_openai_client: AsyncOpenAI | None = None
_SESSION_LANGUAGE_BY_ID: dict[str, str] = {}

def _get_async_openai() -> AsyncOpenAI:
    global _async_openai_client
    if _async_openai_client is None:
        _async_openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _async_openai_client


def _normalize_admission_category_text(text: str) -> str:
    """Normalize legacy admission category phrases to canonical naming."""
    if not text:
        return text

    normalized = text

    # Merge NRI Sponsored into NRI everywhere
    normalized = re.sub(r"\bNRI\s*Sponsored\b", "NRI", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bNRI\s*(?:and|&)\s*NRI\b", "NRI", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bNRI\s*/\s*NRI\b", "NRI", normalized, flags=re.IGNORECASE)

    # Avoid fragmented wording that treats Management and Category-B as separate top-level groups
    normalized = re.sub(
        r"Management\s+quota\s+and\s+Category-?B\s+quota",
        "Management quota (Category-B)",
        normalized,
        flags=re.IGNORECASE,
    )

    return normalized


_REQUIRED_DOCUMENT_PATTERNS = (
    re.compile(r"\brequired\s+documents?\b", re.IGNORECASE),
    re.compile(r"\bdocuments?\s+needed\s+for\s+admission\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+documents?\s+are\s+required\b", re.IGNORECASE),
    re.compile(r"(అవసరమైన|కావలసిన)\s*పత్ర", re.IGNORECASE),
)

_AVAILABLE_BRANCHES_TEXT = "CSE, ECE, EEE, IT, MECH, CIVIL, CSE (AI & ML), CSE (Data Science)"
_AVAILABLE_CATEGORIES_TEXT = "OC, BC-A, BC-B, BC-D, BC-E, SC, ST, EWS"

_EMPTY_MESSAGE_RESPONSES = {
    "en": "Please ask me something about VNRVJIET admissions!",
    "hi": "कृपया VNRVJIET प्रवेश के बारे में कुछ पूछें!",
    "te": "దయచేసి VNRVJIET ప్రవేశాల గురించి ఏదైనా అడగండి!",
    "ta": "VNRVJIET சேர்க்கை பற்றி ஏதாவது கேளுங்கள்!",
    "mr": "कृपया VNRVJIET प्रवेशाबद्दल काही विचारा!",
    "kn": "ದಯವಿಟ್ಟು VNRVJIET ಪ್ರವೇಶಗಳ ಬಗ್ಗೆ ಏನಾದರೂ ಕೇಳಿ!",
    "bn": "দয়া করে VNRVJIET ভর্তির বিষয়ে কিছু জিজ্ঞাসা করুন!",
    "gu": "કૃપા કરીને VNRVJIET પ્રવેશ વિશે કંઈક પૂછો!",
}

_MISSING_BRANCH_PROMPTS = {
    "en": "Please specify which branch you're asking about.",
    "hi": "कृपया बताएं आप किस branch के बारे में पूछ रहे हैं।",
    "te": "దయచేసి మీరు ఏ branch గురించి అడుగుతున్నారో పేర్కొనండి.",
    "ta": "தயவுசெய்து நீங்கள் எந்த branch பற்றி கேட்கிறீர்கள் என்பதை குறிப்பிடுங்கள்.",
    "mr": "कृपया तुम्ही कोणत्या branch बद्दल विचारत आहात ते सांगा.",
    "kn": "ದಯವಿಟ್ಟು ನೀವು ಯಾವ branch ಬಗ್ಗೆ ಕೇಳುತ್ತಿದ್ದೀರಿ ಎಂದು ತಿಳಿಸಿ.",
    "bn": "দয়া করে আপনি কোন branch সম্পর্কে জিজ্ঞাসা করছেন তা উল্লেখ করুন।",
    "gu": "કૃપા કરીને તમે કયા branch વિશે પૂછો છો તે જણાવો.",
}

_MISSING_CATEGORY_PROMPTS = {
    "en": "Please specify your category.",
    "hi": "कृपया अपनी category बताएं।",
    "te": "దయచేసి మీ category ను పేర్కొనండి.",
    "ta": "தயவுசெய்து உங்கள் category-ஐ குறிப்பிடுங்கள்.",
    "mr": "कृपया तुमची category सांगा.",
    "kn": "ದಯವಿಟ್ಟು ನಿಮ್ಮ category ಅನ್ನು ತಿಳಿಸಿ.",
    "bn": "দয়া করে আপনার category উল্লেখ করুন।",
    "gu": "કૃપા કરીને તમારી category જણાવો.",
}

_AVAILABLE_BRANCHES_LABELS = {
    "en": "Available branches",
    "hi": "उपलब्ध branches",
    "te": "అందుబాటులో ఉన్న branches",
    "ta": "கிடைக்கும் branches",
    "mr": "उपलब्ध branches",
    "kn": "ಲಭ್ಯವಿರುವ branches",
    "bn": "উপলব্ধ branches",
    "gu": "ઉપલબ્ધ branches",
}

_AVAILABLE_CATEGORIES_LABELS = {
    "en": "Available categories",
    "hi": "उपलब्ध categories",
    "te": "అందుబాటులో ఉన్న categories",
    "ta": "கிடைக்கும் categories",
    "mr": "उपलब्ध categories",
    "kn": "ಲಭ್ಯವಿರುವ categories",
    "bn": "উপলব্ধ categories",
    "gu": "ઉપલબ્ધ categories",
}

_EXAMPLE_LABELS = {
    "en": "Example",
    "hi": "उदाहरण",
    "te": "ఉదాహరణ",
    "ta": "எடுத்துக்காட்டு",
    "mr": "उदाहरण",
    "kn": "ಉದಾಹರಣೆ",
    "bn": "উদাহরণ",
    "gu": "ઉદાહરણ",
}

_MISSING_BRANCH_EXAMPLES = {
    "en": "What is the cutoff for CSE branch?",
    "hi": "CSE branch का cutoff क्या है?",
    "te": "CSE branch కి cutoff ఎంత?",
    "ta": "CSE branch-க்கு cutoff என்ன?",
    "mr": "CSE branch साठी cutoff किती आहे?",
    "kn": "CSE branch ಗೆ cutoff ಎಷ್ಟು?",
    "bn": "CSE branch-এর cutoff কত?",
    "gu": "CSE branch માટે cutoff કેટલો છે?",
}

_MISSING_CATEGORY_EXAMPLES = {
    "en": "What is the BC-D cutoff for CSE?",
    "hi": "CSE के लिए BC-D cutoff क्या है?",
    "te": "CSE కి BC-D cutoff ఎంత?",
    "ta": "CSE-க்கு BC-D cutoff என்ன?",
    "mr": "CSE साठी BC-D cutoff किती आहे?",
    "kn": "CSE ಗೆ BC-D cutoff ಎಷ್ಟು?",
    "bn": "CSE-এর জন্য BC-D cutoff কত?",
    "gu": "CSE માટે BC-D cutoff કેટલો છે?",
}

_RETRIEVE_NO_CONTEXT_RESPONSES = {
    "en": "I don't have specific information about that in my knowledge base. Please contact our admissions office for detailed information.",
    "hi": "मेरे नॉलेज बेस में इसके बारे में विशिष्ट जानकारी उपलब्ध नहीं है। विस्तृत जानकारी के लिए कृपया हमारे admissions office से संपर्क करें।",
    "te": "నా knowledge base లో దీనిపై నిర్దిష్ట సమాచారం లేదు. వివరాల కోసం దయచేసి మా admissions office ను సంప్రదించండి.",
    "ta": "என் knowledge base-ல் இதற்கான குறிப்பான தகவல் இல்லை. விரிவான தகவலுக்கு admissions office-ஐ தொடர்புகொள்ளவும்.",
    "mr": "माझ्या knowledge base मध्ये याबद्दल विशिष्ट माहिती उपलब्ध नाही. सविस्तर माहितीसाठी कृपया admissions office शी संपर्क करा.",
    "kn": "ನನ್ನ knowledge base ನಲ್ಲಿ ಇದರ ಕುರಿತು ನಿರ್ದಿಷ್ಟ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ. ವಿವರವಾದ ಮಾಹಿತಿಗಾಗಿ admissions office ಅನ್ನು ಸಂಪರ್ಕಿಸಿ.",
    "bn": "আমার knowledge base-এ এ বিষয়ে নির্দিষ্ট তথ্য নেই। বিস্তারিত তথ্যের জন্য admissions office-এর সাথে যোগাযোগ করুন।",
    "gu": "મારા knowledge base માં આ વિષયની ચોક્કસ માહિતી ઉપલબ્ધ નથી. વિગતવાર માહિતી માટે admissions office નો સંપર્ક કરો.",
}

_CUTOFF_ENGINE_ERROR_RESPONSES = {
    "en": "Sorry, there was an error retrieving cutoff data. Please try again or contact support.",
    "hi": "क्षमा करें, cutoff data प्राप्त करने में त्रुटि हुई। कृपया फिर से प्रयास करें या support से संपर्क करें।",
    "te": "క్షమించండి, cutoff data పొందడంలో లోపం జరిగింది. దయచేసి మళ్లీ ప్రయత్నించండి లేదా support ను సంప్రదించండి.",
    "ta": "மன்னிக்கவும், cutoff data பெறும்போது பிழை ஏற்பட்டது. மீண்டும் முயற்சிக்கவும் அல்லது support-ஐ தொடர்புகொள்ளவும்.",
    "mr": "क्षमस्व, cutoff data मिळवताना त्रुटी आली. कृपया पुन्हा प्रयत्न करा किंवा support शी संपर्क करा.",
    "kn": "ಕ್ಷಮಿಸಿ, cutoff data ಪಡೆಯುವಾಗ ದೋಷವಾಯಿತು. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ ಅಥವಾ support ಅನ್ನು ಸಂಪರ್ಕಿಸಿ.",
    "bn": "দুঃখিত, cutoff data আনতে সমস্যা হয়েছে। আবার চেষ্টা করুন বা support-এর সাথে যোগাযোগ করুন।",
    "gu": "માફ કરશો, cutoff data મેળવવામાં ભૂલ થઈ. કૃપા કરીને ફરી પ્રયાસ કરો અથવા support નો સંપર્ક કરો.",
}

_RAG_ERROR_RESPONSES = {
    "en": "I apologize, but I'm having trouble finding information about that. Please try rephrasing your question or contact our admissions office.",
    "hi": "क्षमा करें, मुझे इसके बारे में जानकारी खोजने में कठिनाई हो रही है। कृपया अपना प्रश्न दोबारा लिखें या admissions office से संपर्क करें।",
    "te": "క్షమించండి, దీనిపై సమాచారం కనుగొనడంలో నాకు సమస్య ఉంది. దయచేసి మీ ప్రశ్నను మరోలా అడగండి లేదా admissions office ను సంప్రదించండి.",
    "ta": "மன்னிக்கவும், இதற்கான தகவலை கண்டுபிடிக்க எனக்கு சிரமமாக உள்ளது. தயவுசெய்து கேள்வியை மாற்றி கேளுங்கள் அல்லது admissions office-ஐ தொடர்புகொள்ளவும்.",
    "mr": "क्षमस्व, याबद्दलची माहिती शोधण्यात मला अडचण येत आहे. कृपया प्रश्न पुन्हा विचारा किंवा admissions office शी संपर्क साधा.",
    "kn": "ಕ್ಷಮಿಸಿ, ಇದರ ಬಗ್ಗೆ ಮಾಹಿತಿ ಹುಡುಕುವಲ್ಲಿ ನನಗೆ ತೊಂದರೆ ಆಗುತ್ತಿದೆ. ದಯವಿಟ್ಟು ಪ್ರಶ್ನೆಯನ್ನು ಮರುಬರೆಯಿರಿ ಅಥವಾ admissions office ಅನ್ನು ಸಂಪರ್ಕಿಸಿ.",
    "bn": "দুঃখিত, এ বিষয়ে তথ্য খুঁজে পেতে আমার সমস্যা হচ্ছে। অনুগ্রহ করে প্রশ্নটি অন্যভাবে করুন বা admissions office-এর সাথে যোগাযোগ করুন।",
    "gu": "માફ કરશો, આ વિષયની માહિતી શોધવામાં મને મુશ્કેલી આવી રહી છે. કૃપા કરીને પ્રશ્નને ફરીથી લખો અથવા admissions office નો સંપર્ક કરો.",
}

_STREAMING_ERROR_RESPONSES = {
    "en": "Sorry, I'm having trouble processing your request. Please try again.",
    "hi": "क्षमा करें, आपके अनुरोध को प्रोसेस करने में समस्या हो रही है। कृपया फिर से प्रयास करें।",
    "te": "క్షమించండి, మీ అభ్యర్థనను ప్రాసెస్ చేయడంలో సమస్య ఉంది. దయచేసి మళ్లీ ప్రయత్నించండి.",
    "ta": "மன்னிக்கவும், உங்கள் கோரிக்கையை செயலாக்குவதில் சிக்கல் உள்ளது. தயவுசெய்து மீண்டும் முயற்சிக்கவும்.",
    "mr": "क्षमस्व, तुमची विनंती प्रक्रिया करताना अडचण येत आहे. कृपया पुन्हा प्रयत्न करा.",
    "kn": "ಕ್ಷಮಿಸಿ, ನಿಮ್ಮ ವಿನಂತಿಯನ್ನು ಸಂಸ್ಕರಿಸುವಲ್ಲಿ ತೊಂದರೆ ಆಗುತ್ತಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
    "bn": "দুঃখিত, আপনার অনুরোধ প্রক্রিয়া করতে সমস্যা হচ্ছে। অনুগ্রহ করে আবার চেষ্টা করুন।",
    "gu": "માફ કરશો, તમારી વિનંતી પ્રોસેસ કરવામાં મુશ્કેલી આવી રહી છે. કૃપા કરીને ફરી પ્રયાસ કરો.",
}

_DOCUMENT_CATEGORY_PROMPTS = {
    "en": "Please select your admission category to view required documents:",
    "hi": "आवश्यक दस्तावेज़ देखने के लिए अपनी admission category चुनें:",
    "te": "అవసరమైన పత్రాలు చూడడానికి మీ admission category ను ఎంచుకోండి:",
    "ta": "தேவையான ஆவணங்களை பார்க்க உங்கள் admission category-ஐத் தேர்ந்தெடுக்கவும்:",
    "mr": "आवश्यक कागदपत्रे पाहण्यासाठी तुमची admission category निवडा:",
    "kn": "ಅಗತ್ಯ ದಾಖಲೆಗಳನ್ನು ನೋಡಲು ನಿಮ್ಮ admission category ಆಯ್ಕೆಮಾಡಿ:",
    "bn": "প্রয়োজনীয় নথি দেখতে আপনার admission category নির্বাচন করুন:",
    "gu": "જરૂરી દસ્તાવેજો જોવા માટે તમારી admission category પસંદ કરો:",
}

_DOCUMENT_CATEGORY_DETAILS = {
    "convener": {
        "canonical_label": "Convener (Category A)",
        "labels": {
            "en": "Convener (Category A)",
            "hi": "कन्वीनर (Category A)",
            "te": "కన్వీనర్ (Category A)",
            "ta": "கன்வீனர் (Category A)",
            "mr": "कन्व्हीनर (Category A)",
            "kn": "ಕನ್ವೀನರ್ (Category A)",
            "bn": "কনভেনার (Category A)",
            "gu": "કન્વીનર (Category A)",
        },
        "prefix": {
            "en": "For Convener (Category A) admission, the required documents are:",
            "hi": "Convener (Category A) admission के लिए आवश्यक दस्तावेज़:",
            "te": "Convener (Category A) admission కు అవసరమైన పత్రాలు ఇవి:",
            "ta": "Convener (Category A) admission-க்கு தேவையான ஆவணங்கள்:",
            "mr": "Convener (Category A) admission साठी आवश्यक कागदपत्रे:",
            "kn": "Convener (Category A) admission ಗೆ ಅಗತ್ಯ ದಾಖಲೆಗಳು:",
            "bn": "Convener (Category A) admission-এর জন্য প্রয়োজনীয় নথি:",
            "gu": "Convener (Category A) admission માટે જરૂરી દસ્તાવેજો:",
        },
    },
    "management": {
        "canonical_label": "Management (Category B / NRI / NRI Sponsored)",
        "labels": {
            "en": "Management (Category B / NRI / NRI Sponsored)",
            "hi": "मैनेजमेंट (Category B / NRI / NRI Sponsored)",
            "te": "మేనేజ్‌మెంట్ (Category B / NRI / NRI Sponsored)",
            "ta": "மேனேஜ்மெண்ட் (Category B / NRI / NRI Sponsored)",
            "mr": "मॅनेजमेंट (Category B / NRI / NRI Sponsored)",
            "kn": "ಮ್ಯಾನೇಜ್ಮೆಂಟ್ (Category B / NRI / NRI Sponsored)",
            "bn": "ম্যানেজমেন্ট (Category B / NRI / NRI Sponsored)",
            "gu": "મેનેજમેન્ટ (Category B / NRI / NRI Sponsored)",
        },
        "prefix": {
            "en": "For Management (Category B / NRI / NRI Sponsored) admission, the required documents are:",
            "hi": "Management (Category B / NRI / NRI Sponsored) admission के लिए आवश्यक दस्तावेज़:",
            "te": "Management (Category B / NRI / NRI Sponsored) admission కు అవసరమైన పత్రాలు ఇవి:",
            "ta": "Management (Category B / NRI / NRI Sponsored) admission-க்கு தேவையான ஆவணங்கள்:",
            "mr": "Management (Category B / NRI / NRI Sponsored) admission साठी आवश्यक कागदपत्रे:",
            "kn": "Management (Category B / NRI / NRI Sponsored) admission ಗೆ ಅಗತ್ಯ ದಾಖಲೆಗಳು:",
            "bn": "Management (Category B / NRI / NRI Sponsored) admission-এর জন্য প্রয়োজনীয় নথি:",
            "gu": "Management (Category B / NRI / NRI Sponsored) admission માટે જરૂરી દસ્તાવેજો:",
        },
    },
    "supernumerary": {
        "canonical_label": "Supernumerary Quota",
        "labels": {
            "en": "Supernumerary Quota",
            "hi": "सुपरन्यूमरेरी कोटा",
            "te": "సూపర్న్యూమరరీ కోటా",
            "ta": "சூப்பர்நியூமரரி ஒதுக்கீடு",
            "mr": "सुपरन्यूमरेरी कोटा",
            "kn": "ಸೂಪರ್‌ನ್ಯೂಮರರಿ ಕೋಟಾ",
            "bn": "সুপারনিউমেরারি কোটা",
            "gu": "સુપરન્યુમરરી ક્વોટા",
        },
        "prefix": {
            "en": "For Supernumerary Quota admission, the required documents are:",
            "hi": "Supernumerary Quota admission के लिए आवश्यक दस्तावेज़:",
            "te": "Supernumerary Quota admission కు అవసరమైన పత్రాలు ఇవి:",
            "ta": "Supernumerary Quota admission-க்கு தேவையான ஆவணங்கள்:",
            "mr": "Supernumerary Quota admission साठी आवश्यक कागदपत्रे:",
            "kn": "Supernumerary Quota admission ಗೆ ಅಗತ್ಯ ದಾಖಲೆಗಳು:",
            "bn": "Supernumerary Quota admission-এর জন্য প্রয়োজনীয় নথি:",
            "gu": "Supernumerary Quota admission માટે જરૂરી દસ્તાવેજો:",
        },
    },
}

_PENDING_DOCUMENT_CATEGORY_SESSIONS: set[str] = set()


def _normalize_language_code(language: Optional[str]) -> str:
    """Return normalized language code with safe fallback."""
    if not language:
        return DEFAULT_LANGUAGE
    normalized = language.strip().lower()
    if normalized in SUPPORTED_LANGUAGES:
        return normalized
    return DEFAULT_LANGUAGE


def _is_ambiguous_language_input(text: str) -> bool:
    """
    Return True for short/technical follow-ups where language is unclear.
    Examples: "1", "ok", "CSE cutoff", "BC-D girls 2024".
    """
    stripped = text.strip()
    if not stripped:
        return True
    if re.fullmatch(r"[\d\W_]+", stripped):
        return True

    has_non_ascii = any(ord(char) > 127 for char in stripped)
    if has_non_ascii:
        return False

    english_words = re.findall(r"[A-Za-z]+", stripped)
    return len(english_words) <= 2


def _resolve_effective_language(session_id: str, user_message: str, requested_language: str) -> str:
    """
    Resolve response language using:
    1) explicit language-change request,
    2) detected input language,
    3) session memory for ambiguous follow-ups,
    4) request language/default fallback.
    """
    normalized_requested = _normalize_language_code(requested_language)
    has_session_language = session_id in _SESSION_LANGUAGE_BY_ID
    session_language = _SESSION_LANGUAGE_BY_ID.get(session_id, normalized_requested)

    change_target = detect_language_change_request(user_message, session_language)
    if change_target and change_target != "show_selector" and change_target in SUPPORTED_LANGUAGES:
        resolved = change_target
    else:
        detected = _normalize_language_code(detect_language(user_message))
        if detected != DEFAULT_LANGUAGE:
            resolved = detected
        elif _is_ambiguous_language_input(user_message):
            resolved = session_language if has_session_language else detected
        else:
            resolved = DEFAULT_LANGUAGE

    _SESSION_LANGUAGE_BY_ID[session_id] = resolved
    return resolved


def _get_localized_text(mapping: dict[str, str], language: str) -> str:
    """Get language-specific string with English fallback."""
    return mapping.get(language, mapping.get(DEFAULT_LANGUAGE, ""))


def _build_missing_branch_response_text(language: str) -> str:
    """Build localized missing-branch guidance message."""
    prompt = _get_localized_text(_MISSING_BRANCH_PROMPTS, language)
    branches_label = _get_localized_text(_AVAILABLE_BRANCHES_LABELS, language)
    example_label = _get_localized_text(_EXAMPLE_LABELS, language)
    example = _get_localized_text(_MISSING_BRANCH_EXAMPLES, language)
    return (
        f"{prompt} "
        f"{branches_label}: {_AVAILABLE_BRANCHES_TEXT}.\n\n"
        f"{example_label}: '{example}'"
    )


def _build_missing_category_response_text(language: str) -> str:
    """Build localized missing-category guidance message."""
    prompt = _get_localized_text(_MISSING_CATEGORY_PROMPTS, language)
    categories_label = _get_localized_text(_AVAILABLE_CATEGORIES_LABELS, language)
    example_label = _get_localized_text(_EXAMPLE_LABELS, language)
    example = _get_localized_text(_MISSING_CATEGORY_EXAMPLES, language)
    return (
        f"{prompt} "
        f"{categories_label}: {_AVAILABLE_CATEGORIES_TEXT}.\n\n"
        f"{example_label}: '{example}'"
    )


def _get_document_category_label(category_key: str, language: str) -> str:
    """Get localized label for document category option."""
    details = _DOCUMENT_CATEGORY_DETAILS[category_key]
    return details["labels"].get(language, details["labels"]["en"])


def _get_document_category_prefix(category_key: str, language: str) -> str:
    """Get localized response prefix for selected document category."""
    details = _DOCUMENT_CATEGORY_DETAILS[category_key]
    return details["prefix"].get(language, details["prefix"]["en"])

_LIST_TOPIC_KEYWORDS = (
    "document",
    "documents",
    "required",
    "requirement",
    "requirements",
    "step",
    "steps",
    "procedure",
    "process",
    "fee",
    "fees",
    "breakdown",
)

_INLINE_NUMBER_MARKER_PATTERN = re.compile(r"(?<!\w)\d{1,2}\.\s+")
_INLINE_BULLET_MARKER_PATTERN = re.compile(r"[•●▪◦]\s+")

async def retrieve_and_respond(query: str, language: str = "en", additional_instructions: str = "") -> str:
    """Generate AI response using RAG pipeline."""
    
    # Retrieve relevant context
    retrieval_result = retrieve(query, top_k=5)
    
    if not retrieval_result.chunks:
        return _get_localized_text(_RETRIEVE_NO_CONTEXT_RESPONSES, language)
    
    # Map language codes to full language names for better LLM understanding
    language_names = {
        "en": "English",
        "hi": "Hindi",
        "te": "Telugu",
        "ta": "Tamil",
        "mr": "Marathi",
        "kn": "Kannada",
        "bn": "Bengali",
        "gu": "Gujarati",
    }
    
    language_name = language_names.get(language, "English")
    
    additional_block = ""
    if additional_instructions.strip():
        additional_block = f"\nAdditional instruction:\n{additional_instructions.strip()}\n"
    
    # Generate response using GPT with retrieved context
    system_prompt = f"""You are a helpful AI assistant for VNRVJIET (VNR Vignana Jyothi Institute of Engineering and Technology) admissions.

Use the provided context to answer questions accurately. If the context doesn't contain the answer, say so clearly.

IMPORTANT: You MUST respond ONLY in {language_name} language. Do NOT use English unless the user selected English.

For Marathi (मराठी), your ENTIRE response must be in Marathi script with NO English sentences.

Keep responses informative but concise. Include specific details like numbers, dates, and procedures when available.

STRICT LIST FORMATTING RULES (MANDATORY):
- Whenever the answer includes documents, steps, requirements, fee breakdowns, or any multi-item information, format it as a clean list.
- Use numbered lists (1., 2., 3.) for ordered items.
- Put each item on a new line.
- Never combine multiple list items in a single paragraph line.
- If context is unstructured, first split into individual items, then present as a numbered list.

Canonical admission category hierarchy (STRICT):
1) Convenor / Category-A
2) Management
    - Category-B
    - NRI
3) Supernumerary Seats

Rules:
- Management is the parent category.
- Category-B and NRI must be nested under Management.
- Never present Category-B or NRI as top-level categories.
- Treat "NRI Sponsored" as "NRI" and never list both separately.

Standard abbreviations (like CSE, ECE, BC-D, OC) can remain as-is.

{additional_block}
Context:
{retrieval_result.context_text}"""

    client = _get_async_openai()
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        temperature=0.3,
        max_tokens=1000
    )
    
    return response.choices[0].message.content
from app.utils.validators import (
    extract_branch, extract_category, extract_gender, 
    extract_year, extract_rank, extract_quota
)

logger = logging.getLogger(__name__)
router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    language: str = "en"

class ChatResponse(BaseModel):
    response: str
    intent: str = "informational"
    metadata: dict = Field(default_factory=dict)
    options: list[dict] = Field(default_factory=list)


def _is_required_documents_query(message: str) -> bool:
    """Return True when user asks required-documents style admission query."""
    normalized = " ".join(message.lower().split())
    return any(pattern.search(normalized) for pattern in _REQUIRED_DOCUMENT_PATTERNS)


def _extract_document_category_selection(message: str) -> Optional[str]:
    """Map user selection to canonical admission document category."""
    normalized = re.sub(r"\s+", " ", message.strip().lower())
    if not normalized:
        return None

    normalized = normalized.strip(" .:-")

    if normalized in {"1", "option 1", "choice 1"}:
        return "convener"
    if normalized in {"2", "option 2", "choice 2"}:
        return "management"
    if normalized in {"3", "option 3", "choice 3"}:
        return "supernumerary"

    if re.search(r"\bconvener\b", normalized) or re.search(r"\bcategory\s*-?\s*a\b", normalized):
        return "convener"
    if re.search(r"కన్వీన", normalized) or re.search(r"కేటగిరీ\s*ఏ", normalized):
        return "convener"

    if (
        re.search(r"\bmanagement\b", normalized)
        or re.search(r"\bcategory\s*-?\s*b\b", normalized)
        or re.search(r"\bnri\b", normalized)
    ):
        return "management"
    if re.search(r"మేనేజ్|మెనేజ్|న్రి|ఎన్ఆర్ఐ|కేటగిరీ\s*బి", normalized):
        return "management"

    if re.search(r"\bsupernumerary\b", normalized):
        return "supernumerary"
    if re.search(r"సూపర్.?న్యూమరరీ", normalized):
        return "supernumerary"

    return None


def _build_document_category_prompt_response(language: str) -> ChatResponse:
    """Build category selection prompt with clickable options for documents flow."""
    prompt_text = _get_localized_text(_DOCUMENT_CATEGORY_PROMPTS, language)
    options: list[dict] = []
    for idx, category_key in enumerate(("convener", "management", "supernumerary"), start=1):
        label = _get_document_category_label(category_key, language)
        value = category_key
        options.append({"label": label, "value": value})

    prompt_lines = [f"{idx}. {option['label']}" for idx, option in enumerate(options, start=1)]
    return ChatResponse(
        response=f"{prompt_text}\n\n" + "\n".join(prompt_lines),
        intent="informational",
        metadata={"awaiting_document_category": True},
        options=options,
    )


async def _handle_required_documents_flow(
    user_message: str,
    session_id: str,
    language: str,
) -> Optional[ChatResponse]:
    """
    Enforce category-selection step before returning required document lists.
    """
    if _is_required_documents_query(user_message):
        _PENDING_DOCUMENT_CATEGORY_SESSIONS.add(session_id)
        return _build_document_category_prompt_response(language)

    if session_id not in _PENDING_DOCUMENT_CATEGORY_SESSIONS:
        return None

    selected_category = _extract_document_category_selection(user_message)
    if not selected_category:
        return _build_document_category_prompt_response(language)

    _PENDING_DOCUMENT_CATEGORY_SESSIONS.discard(session_id)
    category_details = _DOCUMENT_CATEGORY_DETAILS[selected_category]
    localized_label = _get_document_category_label(selected_category, language)
    localized_prefix = _get_document_category_prefix(selected_category, language)

    category_prompt = (
        f"Required documents for {category_details['canonical_label']} admission at VNRVJIET.\n"
        "Return only this selected category's required admission documents."
    )
    additional_instructions = (
        f"Start exactly with: \"{localized_prefix}\". "
        "Then list required documents as a numbered list with one item per line. "
        "Do not include any other category."
    )
    response_text = await retrieve_and_respond(
        category_prompt,
        language=language,
        additional_instructions=additional_instructions,
    )

    if not response_text.strip().lower().startswith(localized_prefix.lower()):
        response_text = f"{localized_prefix}\n\n{response_text}"

    return ChatResponse(
        response=response_text,
        intent="informational",
        metadata={"document_category": selected_category, "document_category_label": localized_label},
    )


def _clean_list_item(item: str) -> str:
    """Normalize whitespace and punctuation around a list item."""
    compact = re.sub(r"\s+", " ", item).strip()
    return compact.strip("-•:; ")


def _has_multiline_list(text: str) -> bool:
    """Check whether text already contains a proper multiline list."""
    numbered_lines = re.findall(r"(?m)^\s*\d+\.\s+\S+", text)
    bullet_lines = re.findall(r"(?m)^\s*[-•]\s+\S+", text)
    return len(numbered_lines) >= 2 or len(bullet_lines) >= 2


def _looks_like_list_topic(text: str) -> bool:
    """Detect topics that should be strongly list-formatted."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in _LIST_TOPIC_KEYWORDS)


def _extract_inline_numbered_items(text: str) -> Optional[tuple[str, list[str]]]:
    """Extract inline '1. ... 2. ...' content into structured list items."""
    matches = list(_INLINE_NUMBER_MARKER_PATTERN.finditer(text))
    if len(matches) < 2:
        return None

    heading = text[:matches[0].start()].strip()
    items: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        candidate = _clean_list_item(text[start:end])
        if candidate:
            items.append(candidate)

    if len(items) < 2:
        return None

    return heading, items


def _extract_inline_bullet_items(text: str) -> Optional[tuple[str, list[str]]]:
    """Extract inline '• ... • ...' content into structured list items."""
    matches = list(_INLINE_BULLET_MARKER_PATTERN.finditer(text))
    if len(matches) < 2:
        return None

    heading = text[:matches[0].start()].strip()
    items: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        candidate = _clean_list_item(text[start:end])
        if candidate:
            items.append(candidate)

    if len(items) < 2:
        return None

    return heading, items


def _build_numbered_list(heading: str, items: list[str]) -> str:
    """Compose a clean numbered list with one item per line."""
    lines = [f"{idx}. {item}" for idx, item in enumerate(items, start=1)]
    if heading:
        return f"{heading}\n\n" + "\n".join(lines)
    return "\n".join(lines)


def _enforce_structured_list_formatting(response_text: str, user_message: str = "") -> str:
    """
    Enforce strict list formatting for multi-item responses.
    Converts inline compact lists into clean multiline numbered lists.
    """
    if not response_text:
        return response_text

    normalized = response_text.replace("\r\n", "\n").strip()
    if not normalized:
        return normalized

    if _has_multiline_list(normalized):
        return normalized

    numbered = _extract_inline_numbered_items(normalized)
    if numbered:
        heading, items = numbered
        return _build_numbered_list(heading, items)

    bullets = _extract_inline_bullet_items(normalized)
    if bullets:
        heading, items = bullets
        return _build_numbered_list(heading, items)

    # Fallback: convert semicolon-separated multi-item text for list-heavy topics.
    if _looks_like_list_topic(user_message) or _looks_like_list_topic(normalized):
        heading = ""
        list_segment = normalized
        if ":" in normalized:
            prefix, suffix = normalized.split(":", 1)
            if suffix.count(";") >= 2:
                heading = prefix.strip() + ":"
                list_segment = suffix

        if list_segment.count(";") >= 2:
            raw_items = [part for part in list_segment.split(";")]
            items = [_clean_list_item(part) for part in raw_items if _clean_list_item(part)]
            if len(items) >= 2:
                return _build_numbered_list(heading, items)

    return normalized


def _finalize_chat_response(response: ChatResponse, user_message: str) -> ChatResponse:
    """Apply final output formatting guarantees before returning to the client."""
    response.response = _enforce_structured_list_formatting(response.response, user_message)
    return response

@router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint that handles all user queries.
    Routes to appropriate engines based on intent classification.
    """
    try:
        user_message = request.message.strip()
        session_id = request.session_id or "default"
        effective_language = _resolve_effective_language(
            session_id=session_id,
            user_message=user_message,
            requested_language=request.language,
        )
        
        if not user_message:
            return _finalize_chat_response(ChatResponse(
                response=_get_localized_text(_EMPTY_MESSAGE_RESPONSES, effective_language),
                intent="greeting"
            ), user_message)
        
        logger.info(f"Processing query: {user_message[:100]}...")

        # Handle mandatory document-category selection flow before generic intent routing.
        document_flow_response = await _handle_required_documents_flow(
            user_message=user_message,
            session_id=session_id,
            language=effective_language,
        )
        if document_flow_response is not None:
            return _finalize_chat_response(document_flow_response, user_message)
        
        # Classify the user's intent
        intent_result = classify(user_message)
        
        if intent_result.intent.value == "cutoff":
            # Handle cutoff/eligibility queries
            return _finalize_chat_response(
                await handle_cutoff_query(user_message, intent_result, effective_language),
                user_message,
            )
        
        elif intent_result.intent.value == "mixed":
            # Handle mixed queries (RAG + cutoff)
            return _finalize_chat_response(
                await handle_mixed_query(user_message, intent_result, effective_language),
                user_message,
            )
        
        elif intent_result.intent.value == "greeting":
            return _finalize_chat_response(ChatResponse(
                response=get_greeting_message(effective_language),
                intent="greeting"
            ), user_message)
        
        elif intent_result.intent.value == "out_of_scope":
            return _finalize_chat_response(ChatResponse(
                response=get_out_of_scope_message(effective_language),
                intent="out_of_scope"
            ), user_message)
        
        else:
            # Default to RAG for informational queries
            return _finalize_chat_response(
                await handle_informational_query(user_message, intent_result, effective_language),
                user_message,
            )
            
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")

async def handle_cutoff_query(user_message: str, intent_result: ClassificationResult, language: str = "en") -> ChatResponse:
    """Handle queries that need cutoff/eligibility data from Firestore."""
    
    # Extract parameters from user message
    branch = extract_branch(user_message)
    category = extract_category(user_message) 
    gender = extract_gender(user_message) or "Any"
    year = extract_year(user_message)
    quota = extract_quota(user_message) or "Convenor"
    rank = extract_rank(user_message)
    
    logger.info(f"Extracted parameters: branch={branch}, category={category}, gender={gender}, year={year}, quota={quota}")
    
    # Validate required parameters
    if not branch:
        return ChatResponse(
            response=_build_missing_branch_response_text(language),
            intent="cutoff",
            metadata={"error": "missing_branch"}
        )
    
    if not category:
        return ChatResponse(
            response=_build_missing_category_response_text(language),
            intent="cutoff", 
            metadata={"error": "missing_category"}
        )
    
    # Call cutoff engine with extracted parameters
    try:
        result = get_cutoff(
            branch=branch,
            category=category, 
            year=year,
            gender=gender,
            quota=quota,
            language=language
        )

        # Be defensive: treat data as found when any concrete cutoff payload exists,
        # even if a legacy engine path forgets to set `found=True`.
        has_data = bool(result.found) or bool(result.all_results) or (result.cutoff_rank is not None)
        
        if has_data:
            response_text = result.message
        else:
            response_text = result.message or _build_missing_category_response_text(language)
        
        return ChatResponse(
            response=response_text,
            intent="cutoff",
            metadata={
                "branch": branch,
                "category": category, 
                "year": year,
                "gender": gender,
                "quota": quota,
                "found": has_data,
                "result": {
                    "branch": result.branch,
                    "category": result.category,
                    "gender": result.gender,
                    "year": result.year,
                    "round": result.round,
                    "quota": result.quota,
                    "cutoff_rank": result.cutoff_rank,
                    "first_rank": result.first_rank,
                    "last_rank": result.last_rank,
                    "rows": result.all_results,
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Cutoff engine error: {e}")
        return ChatResponse(
            response=_get_localized_text(_CUTOFF_ENGINE_ERROR_RESPONSES, language),
            intent="cutoff",
            metadata={"error": str(e)}
        )

async def handle_mixed_query(user_message: str, intent_result: ClassificationResult, language: str = "en") -> ChatResponse:
    """Handle queries that need both RAG context and cutoff data."""
    
    # First get RAG context
    rag_response = await retrieve_and_respond(user_message, language)
    
    # Then try to add cutoff data if relevant
    branch = extract_branch(user_message)
    category = extract_category(user_message)
    
    if branch and category:
        try:
            cutoff_result = get_cutoff(branch=branch, category=category, language=language)
            if cutoff_result.found:
                combined_response = rag_response + "\n\n" + cutoff_result.message
                return ChatResponse(
                    response=combined_response,
                    intent="mixed",
                    metadata={"has_cutoff": True, "branch": branch, "category": category}
                )
        except Exception as e:
            logger.warning(f"Failed to add cutoff data to mixed query: {e}")
    
    return ChatResponse(
        response=rag_response,
        intent="mixed",
        metadata={"has_cutoff": False}
    )

async def handle_informational_query(user_message: str, intent_result: ClassificationResult, language: str = "en") -> ChatResponse:
    """Handle general informational queries using RAG."""
    
    try:
        response_text = await retrieve_and_respond(user_message, language)
        
        return ChatResponse(
            response=response_text,
            intent="informational"
        )
        
    except Exception as e:
        logger.error(f"RAG error: {e}")
        return ChatResponse(
            response=_get_localized_text(_RAG_ERROR_RESPONSES, language),
            intent="informational",
            metadata={"error": str(e)}
        )

def _get_greeting_response(language: str) -> str:
    """Get appropriate greeting response based on language."""
    return get_greeting_message(language)

# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "VNRVJIET Chatbot"}

@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    Streaming chat endpoint that returns Server-Sent Events (SSE).
    This provides a ChatGPT-like typing effect in the frontend.
    """
    session_id = request.session_id or "default"
    effective_language = _resolve_effective_language(
        session_id=session_id,
        user_message=(request.message or "").strip(),
        requested_language=request.language,
    )

    try:
        # Process the chat request normally
        response = await chat_endpoint(request)
        
        # Stream the response token by token
        async def generate_stream():
            """Generate streaming response in SSE format."""
            
            # Split response while preserving whitespace/newlines (critical for list formatting).
            stream_chunks = re.findall(r"\S+|\s+", response.response)
            if not stream_chunks and response.response:
                stream_chunks = [response.response]
            
            for chunk in stream_chunks:
                # Send each chunk as a streaming token
                yield f"data: {json.dumps({'token': chunk, 'done': False})}\n\n"
                # Small delay for typing effect
                await asyncio.sleep(0.05)
            
            # Send completion signal with metadata
            final_data = {
                "done": True,
                "intent": response.intent,
                "metadata": response.metadata,
                "options": response.options or response.metadata.get("options", []),
                "session_id": session_id
            }
            yield f"data: {json.dumps(final_data)}\n\n"
            
        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
        
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        
        # Return error in SSE format
        async def error_stream():
            error_data = {
                "error": _get_localized_text(_STREAMING_ERROR_RESPONSES, effective_language),
                "done": True
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            
        return StreamingResponse(
            error_stream(),
            media_type="text/plain"
        )

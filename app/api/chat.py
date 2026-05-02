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
from app.logic.cutoff_engine import (
    get_cutoff,
    get_available_branches,
    get_cutoffs_flexible,
)
from app.rag.retriever import retrieve
from openai import AsyncOpenAI
from app.config import get_settings
from app.utils.languages import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    detect_language,
    get_greeting_message,
    get_out_of_scope_message,
)

settings = get_settings()

_async_openai_client: AsyncOpenAI | None = None
_SESSION_LANGUAGE_BY_ID: dict[str, str] = {}
_SESSION_CONTEXT_BY_ID: dict[str, str] = {}
_SESSION_CUTOFF_SLOT_MEMORY_BY_SESSION: dict[str, dict[str, str | int]] = {}

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
    re.compile(r"\bdocuments?\b", re.IGNORECASE),
    re.compile(r"\brequired\s+documents?\b", re.IGNORECASE),
    re.compile(r"\bdocuments?\s+needed\s+for\s+admission\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+documents?\s+are\s+required\b", re.IGNORECASE),
    re.compile(r"పత్ర(ాలు)?", re.IGNORECASE),
    re.compile(r"दस्तावेज", re.IGNORECASE),
    re.compile(r"ஆவண", re.IGNORECASE),
    re.compile(r"कागदपत्र", re.IGNORECASE),
    re.compile(r"ದಾಖಲೆ", re.IGNORECASE),
    re.compile(r"নথি|নথিপত্র", re.IGNORECASE),
    re.compile(r"દસ્તાવેજ", re.IGNORECASE),
    re.compile(r"(అవసరమైన|కావలసిన)\s*పత్ర", re.IGNORECASE),
    re.compile(r"आवश्यक\s+दस्तावेज", re.IGNORECASE),
    re.compile(r"தேவையான\s+ஆவண", re.IGNORECASE),
    re.compile(r"आवश्यक\s+कागदपत्र", re.IGNORECASE),
    re.compile(r"ಅಗತ್ಯ\s+ದಾಖಲೆ", re.IGNORECASE),
    re.compile(r"প্রয়োজনীয়\s+নথি", re.IGNORECASE),
    re.compile(r"જરૂરી\s+દસ્તાવેજ", re.IGNORECASE),
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
    "hi": "कृपया बताएं आप किस शाखा के बारे में पूछ रहे हैं।",
    "te": "దయచేసి మీరు ఏ శాఖ గురించి అడుగుతున్నారో పేర్కొనండి.",
    "ta": "தயவுசெய்து நீங்கள் எந்த கிளையை பற்றி கேட்கிறீர்கள் என்பதை குறிப்பிடுங்கள்.",
    "mr": "कृपया तुम्ही कोणत्या शाखेबद्दल विचारत आहात ते सांगा.",
    "kn": "ದಯವಿಟ್ಟು ನೀವು ಯಾವ ಶಾಖೆ ಬಗ್ಗೆ ಕೇಳುತ್ತಿದ್ದೀರಿ ಎಂದು ತಿಳಿಸಿ.",
    "bn": "দয়া করে আপনি কোন শাখা সম্পর্কে জিজ্ঞাসা করছেন তা উল্লেখ করুন।",
    "gu": "કૃપા કરીને તમે કઈ શાખા વિશે પૂછો છો તે જણાવો.",
}

_MISSING_CATEGORY_PROMPTS = {
    "en": "Please specify your category.",
    "hi": "कृपया अपनी श्रेणी बताएं।",
    "te": "దయచేసి మీ వర్గాన్ని పేర్కొనండి.",
    "ta": "தயவுசெய்து உங்கள் வகையை குறிப்பிடுங்கள்.",
    "mr": "कृपया तुमची श्रेणी सांगा.",
    "kn": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ವರ್ಗವನ್ನು ತಿಳಿಸಿ.",
    "bn": "দয়া করে আপনার বিভাগ উল্লেখ করুন।",
    "gu": "કૃપા કરીને તમારી શ્રેણી જણાવો.",
}

_AVAILABLE_BRANCHES_LABELS = {
    "en": "Available branches",
    "hi": "उपलब्ध शाखाएँ",
    "te": "అందుబాటులో ఉన్న శాఖలు",
    "ta": "கிடைக்கும் கிளைகள்",
    "mr": "उपलब्ध शाखा",
    "kn": "ಲಭ್ಯವಿರುವ ಶಾಖೆಗಳು",
    "bn": "উপলব্ধ শাখাসমূহ",
    "gu": "ઉપલબ્ધ શાખાઓ",
}

_AVAILABLE_CATEGORIES_LABELS = {
    "en": "Available categories",
    "hi": "उपलब्ध श्रेणियाँ",
    "te": "అందుబాటులో ఉన్న వర్గాలు",
    "ta": "கிடைக்கும் வகைகள்",
    "mr": "उपलब्ध श्रेणी",
    "kn": "ಲಭ್ಯವಿರುವ ವರ್ಗಗಳು",
    "bn": "উপলব্ধ বিভাগসমূহ",
    "gu": "ઉપલબ્ધ શ્રેણીઓ",
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
    "hi": "CSE शाखा का कटऑफ क्या है?",
    "te": "CSE శాఖకు కట్ ఆఫ్ ఎంత?",
    "ta": "CSE கிளைக்கு கட்ஆஃப் என்ன?",
    "mr": "CSE शाखेसाठी कटऑफ किती आहे?",
    "kn": "CSE ಶಾಖೆಗೆ ಕಟ್‌ಆಫ್ ಎಷ್ಟು?",
    "bn": "CSE শাখার কাট অফ কত?",
    "gu": "CSE શાખા માટે કટઓફ કેટલો છે?",
}

_MISSING_CATEGORY_EXAMPLES = {
    "en": "What is the BC-D cutoff for CSE?",
    "hi": "CSE के लिए BC-D श्रेणी का कटऑफ क्या है?",
    "te": "CSE కి BC-D వర్గం కట్ ఆఫ్ ఎంత?",
    "ta": "CSE க்கு BC-D வகை கட்ஆஃப் என்ன?",
    "mr": "CSE साठी BC-D श्रेणीचा कटऑफ किती आहे?",
    "kn": "CSEಗೆ BC-D ವರ್ಗದ ಕಟ್‌ಆಫ್ ಎಷ್ಟು?",
    "bn": "CSE-এর জন্য BC-D বিভাগের কাট অফ কত?",
    "gu": "CSE માટે BC-D શ્રેણીનો કટઓફ કેટલો છે?",
}

_RETRIEVE_NO_CONTEXT_RESPONSES = {
    "en": "I'm not fully sure about that yet from my current records.",
    "hi": "मुझे अभी अपने रिकॉर्ड से इसका पूरा भरोसेमंद उत्तर नहीं मिल रहा है।",
    "te": "ఇప్పుడున్న నా రికార్డుల ఆధారంగా దీనిపై పూర్తి నిశ్చయంగా చెప్పలేను.",
    "ta": "என் தற்போதைய பதிவுகளின் அடிப்படையில் இதற்கு முழுமையான உறுதியான பதிலை இப்போது சொல்ல முடியவில்லை.",
    "mr": "माझ्या सध्याच्या नोंदींवरून याबद्दल पूर्ण खात्रीने सांगता येत नाही.",
    "kn": "ನನ್ನ ಪ್ರಸ್ತುತ ದಾಖಲೆಗಳ ಆಧಾರದ ಮೇಲೆ ಇದಕ್ಕೆ ಈಗ ಸಂಪೂರ್ಣ ಖಚಿತ ಉತ್ತರ ನೀಡಲು ಸಾಧ್ಯವಾಗುತ್ತಿಲ್ಲ.",
    "bn": "আমার বর্তমান রেকর্ড থেকে এ বিষয়ে পুরোপুরি নিশ্চিতভাবে বলতে পারছি না।",
    "gu": "મારા વર્તમાન રેકોર્ડના આધારે આ વિશે હમણાં સંપૂર્ણ ખાતરીથી કહી શકાતું નથી.",
}

_NO_CONTEXT_WEBSITE_GUIDANCE = {
    "en": "You can find the latest official details here:",
    "hi": "नवीनतम आधिकारिक जानकारी यहां मिल सकती है:",
    "te": "తాజా అధికారిక వివరాలు ఇక్కడ చూడవచ్చు:",
    "ta": "சமீபத்திய அதிகாரப்பூர்வ தகவல்களை இங்கே பார்க்கலாம்:",
    "mr": "ताजी अधिकृत माहिती येथे मिळू शकते:",
    "kn": "ಇತ್ತೀಚಿನ ಅಧಿಕೃತ ಮಾಹಿತಿಯನ್ನು ಇಲ್ಲಿ ಕಾಣಬಹುದು:",
    "bn": "সর্বশেষ অফিসিয়াল তথ্য এখানে পাওয়া যাবে:",
    "gu": "નવીનતમ સત્તાવાર વિગતો અહીં મળશે:",
}

_NO_CONTEXT_FOLLOWUP_QUESTIONS = {
    "en": "If you'd like, I can still help with general guidance. Are you asking about admissions, courses, placements, or campus life?",
    "hi": "अगर आप चाहें, तो मैं सामान्य जानकारी के साथ मदद कर सकता हूं। क्या आप admissions, courses, placements या campus life के बारे में पूछ रहे हैं?",
    "te": "మీకు ఇష్టమైతే, సాధారణ మార్గదర్శకంతో నేను సహాయం చేయగలను. మీరు admissions, courses, placements లేదా campus life గురించి అడుగుతున్నారా?",
    "ta": "நீங்கள் விரும்பினால், பொதுவான வழிகாட்டுதலுடன் நான் உதவ முடியும். admissions, courses, placements அல்லது campus life பற்றி கேட்கிறீர்களா?",
    "mr": "तुम्हाला हवे असल्यास, मी सामान्य मार्गदर्शन करू शकतो. तुम्ही admissions, courses, placements की campus life बद्दल विचारत आहात का?",
    "kn": "ನೀವು ಬಯಸಿದರೆ, ಸಾಮಾನ್ಯ ಮಾರ್ಗದರ್ಶನದೊಂದಿಗೆ ನಾನು ಸಹಾಯ ಮಾಡಬಹುದು. ನೀವು admissions, courses, placements ಅಥವಾ campus life ಬಗ್ಗೆ ಕೇಳುತ್ತಿದ್ದೀರಾ?",
    "bn": "আপনি চাইলে, আমি সাধারণ নির্দেশনা দিয়েও সাহায্য করতে পারি। আপনি কি admissions, courses, placements নাকি campus life সম্পর্কে জানতে চাইছেন?",
    "gu": "જો તમે ઇચ્છો તો હું સામાન્ય માર્ગદર્શન સાથે પણ મદદ કરી શકું. તમે admissions, courses, placements કે campus life વિશે પૂછો છો?",
}

_OFFICIAL_WEBSITE_URL = "https://vnrvjiet.ac.in/"

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

_CUTOFF_SCOPE_NOTE_RESPONSES = {
    "en": "Note: Available cutoff ranks are only for B.Tech admissions under Convener quota.",
    "hi": "नोट: उपलब्ध कटऑफ रैंक केवल B.Tech प्रवेश के लिए, और केवल Convener quota के अंतर्गत हैं।",
    "te": "గమనిక: అందుబాటులో ఉన్న cutoff ranks కేవలం B.Tech admissions లో Convener quota కి మాత్రమే వర్తిస్తాయి.",
    "ta": "குறிப்பு: கிடைக்கும் cutoff ranks, B.Tech சேர்க்கைக்கான Convener quota-க்கு மட்டுமே பொருந்தும்.",
    "mr": "नोंद: उपलब्ध cutoff ranks फक्त B.Tech प्रवेशासाठी आणि केवळ Convener quota साठीच लागू आहेत.",
    "kn": "ಸೂಚನೆ: ಲಭ್ಯ cutoff ranks ಗಳು ಕೇವಲ B.Tech ಪ್ರವೇಶದ Convener quota ಗೆ ಮಾತ್ರ ಅನ್ವಯಿಸುತ್ತವೆ.",
    "bn": "নোট: উপলব্ধ cutoff rank শুধুমাত্র B.Tech ভর্তি এবং Convener quota-এর জন্য প্রযোজ্য।",
    "gu": "નોંધ: ઉપલબ્ધ cutoff ranks માત્ર B.Tech પ્રવેશ માટે અને ફક્ત Convener quota માટે જ લાગુ પડે છે.",
}

_CUTOFF_PROGRAM_UNAVAILABLE_RESPONSES = {
    "en": "Cutoff rank information is available only for B.Tech admissions. No cutoff information is available for the requested program.",
    "hi": "कटऑफ रैंक जानकारी केवल B.Tech प्रवेश के लिए उपलब्ध है। मांगे गए प्रोग्राम के लिए कटऑफ जानकारी उपलब्ध नहीं है।",
    "te": "Cutoff rank సమాచారం కేవలం B.Tech admissions కి మాత్రమే అందుబాటులో ఉంది. మీరు అడిగిన ప్రోగ్రామ్‌కు cutoff సమాచారం లేదు.",
    "ta": "Cutoff rank தகவல் B.Tech சேர்க்கைக்கே மட்டுமே கிடைக்கும். கேட்டுள்ள பிரோகிராமுக்கு cutoff தகவல் இல்லை.",
    "mr": "Cutoff rank माहिती फक्त B.Tech प्रवेशासाठी उपलब्ध आहे. तुम्ही विचारलेल्या प्रोग्रामसाठी cutoff माहिती उपलब्ध नाही.",
    "kn": "Cutoff rank ಮಾಹಿತಿ ಕೇವಲ B.Tech ಪ್ರವೇಶಕ್ಕೆ ಮಾತ್ರ ಲಭ್ಯ. ಕೇಳಿದ ಕಾರ್ಯಕ್ರಮಕ್ಕೆ cutoff ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ.",
    "bn": "Cutoff rank তথ্য শুধুমাত্র B.Tech ভর্তির জন্য উপলব্ধ। অনুরোধ করা প্রোগ্রামের জন্য cutoff তথ্য নেই।",
    "gu": "Cutoff rank માહિતી માત્ર B.Tech પ્રવેશ માટે ઉપલબ્ધ છે. પૂછાયેલા પ્રોગ્રામ માટે cutoff માહિતી ઉપલબ્ધ નથી.",
}

_CUTOFF_QUOTA_UNAVAILABLE_RESPONSES = {
    "en": "Cutoff rank information is available only for Convener quota in B.Tech. No cutoff information is available for the requested quota.",
    "hi": "कटऑफ रैंक जानकारी B.Tech में केवल Convener quota के लिए उपलब्ध है। मांगे गए quota के लिए कटऑफ जानकारी उपलब्ध नहीं है।",
    "te": "Cutoff rank సమాచారం B.Tech లో కేవలం Convener quota కి మాత్రమే అందుబాటులో ఉంది. మీరు అడిగిన quota కు cutoff సమాచారం లేదు.",
    "ta": "Cutoff rank தகவல் B.Tech-இல் Convener quota-க்கு மட்டுமே கிடைக்கும். கேட்டுள்ள quota-க்கு cutoff தகவல் இல்லை.",
    "mr": "Cutoff rank माहिती B.Tech मध्ये फक्त Convener quota साठी उपलब्ध आहे. तुम्ही विचारलेल्या quota साठी cutoff माहिती उपलब्ध नाही.",
    "kn": "Cutoff rank ಮಾಹಿತಿ B.Tech ನಲ್ಲಿ ಕೇವಲ Convener quota ಗಾಗಿ ಮಾತ್ರ ಲಭ್ಯ. ಕೇಳಿದ quota ಗೆ cutoff ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ.",
    "bn": "Cutoff rank তথ্য B.Tech-এ শুধুমাত্র Convener quota-এর জন্য উপলব্ধ। অনুরোধ করা quota-এর জন্য cutoff তথ্য নেই।",
    "gu": "Cutoff rank માહિતી B.Tech માં માત્ર Convener quota માટે ઉપલબ્ધ છે. પૂછાયેલા quota માટે cutoff માહિતી ઉપલબ્ધ નથી.",
}

_AMBIGUOUS_CONTEXT_PROMPTS = {
    "en": "Could you clarify which program or topic you mean (for example, B.Tech fees or hostel information)?",
    "hi": "कृपया बताएं आप किस प्रोग्राम या विषय के बारे में पूछ रहे हैं (जैसे B.Tech की फीस या हॉस्टल जानकारी)?",
    "te": "దయచేసి మీరు ఏ ప్రోగ్రామ్ లేదా అంశం గురించి అడుగుతున్నారో స్పష్టం చేయండి (ఉదాహరణకు B.Tech ఫీజులు లేదా హాస్టల్ సమాచారం).",
    "ta": "நீங்கள் எந்தப் பிரோகிராம் அல்லது தலைப்பைப் பற்றி கேட்கிறீர்கள் என்பதைத் தெளிவுபடுத்த முடியுமா? (உதா: B.Tech கட்டணம் அல்லது விடுதி தகவல்)",
    "mr": "कृपया तुम्ही कोणत्या प्रोग्राम किंवा विषयाबद्दल विचारत आहात ते स्पष्ट करा (उदा. B.Tech फी किंवा वसतिगृह माहिती).",
    "kn": "ದಯವಿಟ್ಟು ನೀವು ಯಾವ ಕಾರ್ಯಕ್ರಮ ಅಥವಾ ವಿಷಯದ ಬಗ್ಗೆ ಕೇಳುತ್ತಿದ್ದೀರಿ ಎಂದು ಸ್ಪಷ್ಟಪಡಿಸಿ (ಉದಾ., B.Tech ಶುಲ್ಕ ಅಥವಾ ವಸತಿ ಗೃಹ ಮಾಹಿತಿ).",
    "bn": "অনুগ্রহ করে বলুন আপনি কোন প্রোগ্রাম বা বিষয় সম্পর্কে জানতে চাইছেন (যেমন B.Tech ফি বা হোস্টেল তথ্য)?",
    "gu": "કૃપા કરીને સ્પષ્ટ કરો કે તમે કયા પ્રોગ્રામ અથવા વિષય વિશે પૂછો છો (ઉદાહરણ તરીકે B.Tech ફી અથવા હોસ્ટેલ માહિતી).",
}

_DEFAULT_LINK_LABELS = {
    "en": "👉 Click here to know more",
    "hi": "👉 अधिक जानने के लिए यहां क्लिक करें",
    "te": "👉 మరింత తెలుసుకోవడానికి ఇక్కడ క్లిక్ చేయండి",
    "ta": "👉 மேலும் அறிய இங்கே கிளிக் செய்யவும்",
    "mr": "👉 अधिक जाणून घेण्यासाठी येथे क्लिक करा",
    "kn": "👉 ಇನ್ನಷ್ಟು ತಿಳಿದುಕೊಳ್ಳಲು ಇಲ್ಲಿ ಕ್ಲಿಕ್ ಮಾಡಿ",
    "bn": "👉 আরও জানতে এখানে ক্লিক করুন",
    "gu": "👉 વધુ જાણવા અહીં ક્લિક કરો",
}

_CLUB_LINK_LABELS = {
    "en": "👉 Explore club details",
    "hi": "👉 क्लब की जानकारी देखें",
    "te": "👉 క్లబ్ వివరాలు చూడండి",
    "ta": "👉 கிளப் விவரங்களை பார்க்கவும்",
    "mr": "👉 क्लबची माहिती पहा",
    "kn": "👉 ಕ್ಲಬ್ ವಿವರಗಳನ್ನು ನೋಡಿ",
    "bn": "👉 ক্লাবের তথ্য দেখুন",
    "gu": "👉 ક્લબની માહિતી જુઓ",
}

_TRANSPORT_FEE_TRIGGER_PHRASES = (
    "transport fee",
    "bus fee",
    "transportation charges",
    "college bus fee",
    "travel fee",
)

_TRANSPORT_FEE_INTRO_TEXT = {
    "en": "For the transport fee structure, you can check the official documents below:",
}

_TRANSPORT_FIRST_YEAR_LABELS = {
    "en": "BTech First Year Transport Fee",
}

_TRANSPORT_OTHER_YEARS_LABELS = {
    "en": "BTech 2nd, 3rd & 4th Year Transport Fee",
}

_TRANSPORT_ADDITIONAL_LABELS = {
    "en": "Transport Fee Document",
}

_TRANSPORT_CTA_TEXT = {
    "en": "Click here to view",
}

_TRANSPORT_LINK_TEXT = {
    "en": "Open document",
}

_TRANSPORT_FEE_OUTRO_TEXT = {
    "en": "These links will take you directly to the detailed fee structure.",
}

_TRANSPORT_FEE_FOLLOWUP_TEXT = {
    "en": "Do you want hostel fee details as well?",
}

_TRANSPORT_FEE_FALLBACK_TEXT = {
    "en": "I'm not able to fetch the transport fee document right now, but you can check the official website here:",
}

_TRANSPORT_FALLBACK_WEBSITE_CTA_TEXT = {
    "en": "Click here to know more",
}

_TRANSPORT_FEE_FALLBACK_FOLLOWUP_TEXT = {
    "en": "Would you like me to help with approximate fee details?",
}

_SHORT_FOLLOWUP_HINTS = (
    "fee",
    "fees",
    "hostel",
    "placement",
    "placements",
    "scholarship",
    "scholarships",
    "cutoff",
    "rank",
    "ranks",
    "campus",
    "club",
    "clubs",
    "document",
    "documents",
    "eligibility",
    "process",
    "procedure",
    "admission",
    "फीस",
    "शुल्क",
    "हॉस्टल",
    "छात्रावास",
    "दस्तावेज",
    "कटऑफ",
    "ఫీజు",
    "ఫీజులు",
    "హాస్టల్",
    "పత్రాలు",
    "కట్",
)

_INTERROGATIVE_TOKENS = {
    "what",
    "how",
    "when",
    "where",
    "which",
    "who",
    "why",
    "can",
    "could",
    "please",
    "tell",
    "give",
    "show",
    "बताओ",
    "बताएं",
    "कौन",
    "क्या",
    "कैसे",
    "कब",
    "कहाँ",
    "చెప్పు",
    "చెప్పండి",
    "ఏది",
    "ఎలా",
    "ఎప్పుడు",
    "ఎక్కడ",
}

_RAW_URL_PATTERN = re.compile(r"(?<!\]\()(?P<url>(?:https?://|www\.)[^\s<>\]\)]+)", re.IGNORECASE)
_MARKDOWN_URL_PATTERN = re.compile(r"\[[^\]]+\]\((?P<url>(?:https?://|www\.)[^\s\)]+)\)", re.IGNORECASE)
_TRANSPORT_FIRST_YEAR_PATTERN = re.compile(r"\b(first|1st)\s*[- ]*year\b|\byear\s*1\b", re.IGNORECASE)
_TRANSPORT_OTHER_YEARS_PATTERN = re.compile(
    r"\b(2nd|second|3rd|third|4th|fourth)\b|\b2nd\s*/\s*3rd\s*/\s*4th\b|\bother\s+years?\b",
    re.IGNORECASE,
)
_MAX_SESSION_CONTEXT_CHARS = 700
_MAX_HISTORY_TURNS_FOR_CONTEXT = 12

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

_DOCUMENT_PROGRAM_PROMPTS = {
    "en": "Please select your program:",
    "hi": "कृपया अपना प्रोग्राम चुनें:",
    "te": "దయచేసి మీ ప్రోగ్రామ్‌ను ఎంచుకోండి:",
    "ta": "தயவுசெய்து உங்கள் பிரோகிராமை தேர்ந்தெடுக்கவும்:",
    "mr": "कृपया तुमचा प्रोग्राम निवडा:",
    "kn": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಪ್ರೋಗ್ರಾಂ ಆಯ್ಕೆಮಾಡಿ:",
    "bn": "অনুগ্রহ করে আপনার প্রোগ্রাম নির্বাচন করুন:",
    "gu": "કૃપા કરીને તમારો પ્રોગ્રામ પસંદ કરો:",
}

_DOCUMENT_PROGRAM_DETAILS = {
    "btech": {
        "canonical_label": "B.Tech",
        "labels": {
            "en": "B.Tech",
            "hi": "बी.टेक",
            "te": "బి.టెక్",
            "ta": "பி.டெக்",
            "mr": "बी.टेक",
            "kn": "ಬಿ.ಟೆಕ್",
            "bn": "বি.টেক",
            "gu": "બી.ટેક",
        },
    },
    "mtech": {
        "canonical_label": "M.Tech",
        "labels": {
            "en": "M.Tech",
            "hi": "एम.टेक",
            "te": "ఎం.టెక్",
            "ta": "எம்.டெக்",
            "mr": "एम.टेक",
            "kn": "ಎಂ.ಟೆಕ್",
            "bn": "এম.টেক",
            "gu": "એમ.ટેક",
        },
    },
    "mba_mca": {
        "canonical_label": "MBA / MCA",
        "labels": {
            "en": "MBA / MCA",
            "hi": "एमबीए/एमसीए",
            "te": "ఎంబీఏ/ఎంసీఏ",
            "ta": "எம்பிஏ / எம்சிஏ",
            "mr": "एमबीए/एमसीए",
            "kn": "ಎಂಬಿಎ / ಎಂಸಿಎ",
            "bn": "এমবিএ / এমসিএ",
            "gu": "એમબીએ / એમસીએ",
        },
    },
}

_DOCUMENT_CATEGORY_PROMPTS = {
    "en": "Please select your admission category:",
    "hi": "कृपया अपनी प्रवेश श्रेणी चुनें:",
    "te": "దయచేసి మీ ప్రవేశ కోటాను ఎంచుకోండి:",
    "ta": "தயவுசெய்து உங்கள் சேர்க்கை ஒதுக்கீட்டை தேர்ந்தெடுக்கவும்:",
    "mr": "कृपया तुमची प्रवेश श्रेणी निवडा:",
    "kn": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಪ್ರವೇಶ ಕೋಟಾವನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
    "bn": "অনুগ্রহ করে আপনার ভর্তি বিভাগ নির্বাচন করুন:",
    "gu": "કૃપા કરીને તમારી પ્રવેશ શ્રેણી પસંદ કરો:",
}

_DOCUMENT_PROGRAM_ACKNOWLEDGEMENTS = {
    "en": "Okay, for {program}:",
    "hi": "ठीक है, {program} के लिए:",
    "te": "సరే, {program} కోసం:",
    "ta": "சரி, {program}க்கு:",
    "mr": "ठीक आहे, {program} साठी:",
    "kn": "ಸರಿ, {program}ಗಾಗಿ:",
    "bn": "ঠিক আছে, {program} এর জন্য:",
    "gu": "બરાબર, {program} માટે:",
}

_DOCUMENT_CATEGORY_DETAILS = {
    "convener": {
        "canonical_label": "Convener (Category A)",
        "labels": {
            "en": "Convener (Category A)",
            "hi": "कन्वीनर कोटा",
            "te": "కన్వీనర్ కోటా",
            "ta": "கன்வீனர் ஒதுக்கீடு",
            "mr": "कन्व्हीनर कोटा",
            "kn": "ಕನ್ವೀನರ್ ಕೋಟಾ",
            "bn": "কনভেনার কোটা",
            "gu": "કન્વીનર ક્વોટા",
        },
        "prefix": {
            "en": "For Convener (Category A) admission, the required documents are:",
            "hi": "कन्वीनर कोटा के लिए आवश्यक दस्तावेज़:",
            "te": "కన్వీనర్ కోటాకు అవసరమైన పత్రాలు:",
            "ta": "கன்வீனர் ஒதுக்கீட்டிற்கான தேவையான ஆவணங்கள்:",
            "mr": "कन्व्हीनर कोट्यासाठी आवश्यक कागदपत्रे:",
            "kn": "ಕನ್ವೀನರ್ ಕೋಟಾಗೆ ಅಗತ್ಯ ದಾಖಲೆಗಳು:",
            "bn": "কনভেনার কোটার জন্য প্রয়োজনীয় নথি:",
            "gu": "કન્વીનર ક્વોટા માટે જરૂરી દસ્તાવેજો:",
        },
    },
    "management": {
        "canonical_label": "Management (Category B / NRI)",
        "labels": {
            "en": "Management (Category B / NRI)",
            "hi": "मैनेजमेंट कोटा",
            "te": "మేనేజ్మెంట్ కోటా",
            "ta": "மேனேஜ்மெண்ட் ஒதுக்கீடு",
            "mr": "मॅनेजमेंट कोटा",
            "kn": "ಮ್ಯಾನೇಜ್ಮೆಂಟ್ ಕೋಟಾ",
            "bn": "ম্যানেজমেন্ট কোটা",
            "gu": "મેનેજમેન્ટ ક્વોટા",
        },
        "prefix": {
            "en": "For Management (Category B / NRI) admission, the required documents are:",
            "hi": "मैनेजमेंट कोटा के लिए आवश्यक दस्तावेज़:",
            "te": "మేనేజ్మెంట్ కోటాకు అవసరమైన పత్రాలు:",
            "ta": "மேனேஜ்மெண்ட் ஒதுக்கீட்டிற்கான தேவையான ஆவணங்கள்:",
            "mr": "मॅनेजमेंट कोट्यासाठी आवश्यक कागदपत्रे:",
            "kn": "ಮ್ಯಾನೇಜ್ಮೆಂಟ್ ಕೋಟಾಗೆ ಅಗತ್ಯ ದಾಖಲೆಗಳು:",
            "bn": "ম্যানেজমেন্ট কোটার জন্য প্রয়োজনীয় নথি:",
            "gu": "મેનેજમેન્ટ ક્વોટા માટે જરૂરી દસ્તાવેજો:",
        },
    },
    "supernumerary": {
        "canonical_label": "Supernumerary Quota",
        "labels": {
            "en": "Supernumerary Quota",
            "hi": "सुपरन्यूमरेरी कोटा",
            "te": "సూపర్న్యూమరరీ కోటా",
            "ta": "சூப்பர்நியூமரரி கோட்டா",
            "mr": "सुपरन्यूमरेरी कोटा",
            "kn": "ಸೂಪರ್‌ನ್ಯೂಮರರಿ ಕೋಟಾ",
            "bn": "সুপারনিউমেরারি কোটা",
            "gu": "સુપરન્યુમરરી ક્વોટા",
        },
        "prefix": {
            "en": "For Supernumerary Quota admission, the required documents are:",
            "hi": "सुपरन्यूमरेरी कोटा के लिए आवश्यक दस्तावेज़:",
            "te": "సూపర్న్యూమరరీ కోటాకు అవసరమైన పత్రాలు:",
            "ta": "சூப்பர்நியூமரரி கோட்டாவிற்கான தேவையான ஆவணங்கள்:",
            "mr": "सुपरन्यूमरेरी कोट्यासाठी आवश्यक कागदपत्रे:",
            "kn": "ಸೂಪರ್‌ನ್ಯೂಮರರಿ ಕೋಟಾಗೆ ಅಗತ್ಯ ದಾಖಲೆಗಳು:",
            "bn": "সুপারনিউমেরারি কোটার জন্য প্রয়োজনীয় নথি:",
            "gu": "સુપરન્યુમરરી ક્વોટા માટે જરૂરી દસ્તાવેજો:",
        },
    },
}

_DOCUMENT_FLOW_STATE_BY_SESSION: dict[str, dict[str, str]] = {}
_DOCUMENT_SLOT_MEMORY_BY_SESSION: dict[str, dict[str, str]] = {}
_CUTOFF_FLOW_STATE_BY_SESSION: dict[str, dict[str, str]] = {}

_GUIDED_BACK_OPTION_VALUE = "__guided_previous_option__"
_GUIDED_BACK_OPTION_LABEL = "Change Previous Option (Back)"


def _reset_guided_session_state(session_id: str) -> None:
    """Clear all per-session guided flow memory."""
    _DOCUMENT_FLOW_STATE_BY_SESSION.pop(session_id, None)
    _CUTOFF_FLOW_STATE_BY_SESSION.pop(session_id, None)
    _SESSION_LANGUAGE_BY_ID.pop(session_id, None)


def _with_guided_back_option(options: list[dict]) -> list[dict]:
    """Append the in-flow back action as a single navigation button."""
    return [*options, {"label": _GUIDED_BACK_OPTION_LABEL, "value": _GUIDED_BACK_OPTION_VALUE}]


def _is_guided_back_option_message(user_message: str) -> bool:
    selected = _resolve_selected_option(
        user_message,
        [{"label": _GUIDED_BACK_OPTION_LABEL, "value": _GUIDED_BACK_OPTION_VALUE}],
    )
    return selected == _GUIDED_BACK_OPTION_VALUE


def _apply_guided_back_action(state: dict[str, str], current_step: str) -> None:
    """Move one step back in the guided cutoff flow."""
    if current_step == "result":
        state.pop("step", None)
        state.pop("gender", None)
        return

    if current_step == "year":
        state.clear()
        return

    if current_step == "gender":
        state.pop("step", None)
        state.pop("category", None)
        state.pop("gender", None)
        return

    if current_step == "category":
        state.pop("step", None)
        state.pop("year", None)
        state.pop("category", None)
        state.pop("gender", None)
        return

    state.pop("step", None)

# Guided branch display map: canonical value -> user-facing label.
# Values are used internally for cutoff lookup; labels are shown on buttons.
_GUIDED_BRANCH_DISPLAY_BY_CANONICAL = {
    "CSE": "CSE",
    "ECE": "ECE",
    "EEE": "EEE",
    "IT": "IT",
    "ME": "MECH",
    "CIV": "CIVIL",
    "CSE-CSM": "CSE (AI & ML)",
    "CSE-CSD": "CSE (Data Science)",
    "CSE-CSC": "Cyber Security (CYS)",
    "CSE-CSO": "IoT (CSO)",
    "AID": "AI & Data Science (AID)",
    "AUT": "Automobile Engineering (AUT)",
    "BIO": "Biotechnology (BIO)",
    "RAI": "Robotics & AI (RAI)",
    "CSB": "Computer Science & Business Systems (CSB)",
    "EIE": "Electronics & Instrumentation Engineering (EIE)",
    "VLSI": "VLSI Design (VLSI)",
}

# Raw dataset aliases -> canonical guided branch values.
_GUIDED_BRANCH_ALIAS_TO_CANONICAL = {
    "CSE": "CSE",
    "ECE": "ECE",
    "EEE": "EEE",
    "IT": "IT",
    "ME": "ME",
    "MECH": "ME",
    "CIV": "CIV",
    "CIVIL": "CIV",
    "CSE-CSM": "CSE-CSM",
    "CSM": "CSE-CSM",
    "CSE (AI & ML)": "CSE-CSM",
    "CSE-CSD": "CSE-CSD",
    "CSD": "CSE-CSD",
    "CSE (Data Science)": "CSE-CSD",
    "AID": "AID",
    "CSE-CSC": "CSE-CSC",
    "CSE- CSC": "CSE-CSC",
    "CSE - CSC": "CSE-CSC",
    "CYS": "CSE-CSC",
    "CSE-CSO": "CSE-CSO",
    "CSO": "CSE-CSO",
    "AUT": "AUT",
    "BIO": "BIO",
    "RAI": "RAI",
    "CSB": "CSB",
    "EIE": "EIE",
    "VLSI": "VLSI",
}


def _branch_alias_key(value: str) -> str:
    """Normalize branch alias text for robust canonical mapping."""
    compact_hyphen = re.sub(r"\s*-\s*", "-", value.strip())
    compact_spaces = re.sub(r"\s+", " ", compact_hyphen)
    return compact_spaces.upper()


_GUIDED_BRANCH_ALIAS_KEY_TO_CANONICAL = {
    _branch_alias_key(alias): canonical
    for alias, canonical in _GUIDED_BRANCH_ALIAS_TO_CANONICAL.items()
}


def _to_guided_canonical_branch(raw_value: str) -> str | None:
    """Map raw branch value to canonical guided branch code."""
    cleaned = (raw_value or "").strip()
    if not cleaned:
        return None
    if cleaned.lower().startswith("estd"):
        return None

    alias_key = _branch_alias_key(cleaned)
    canonical = _GUIDED_BRANCH_ALIAS_KEY_TO_CANONICAL.get(alias_key)
    if canonical:
        return canonical

    # Keep unknown-but-valid dataset values visible rather than dropping them.
    return re.sub(r"\s+", " ", re.sub(r"\s*-\s*", "-", cleaned)).upper()

_GUIDED_BRANCH_PREFERRED_ORDER = [
    "CSE",
    "ECE",
    "EEE",
    "IT",
    "ME",
    "CIV",
    "CSE-CSM",
    "CSE-CSD",
    "CSE-CSC",
    "CSE-CSO",
    "AID",
    "CSB",
    "EIE",
    "AUT",
    "BIO",
    "RAI",
    "VLSI",
]

_GUIDED_MAIN_CATEGORIES_ORDER = [
    "OC",
    "BC-A",
    "BC-B",
    "BC-C",
    "BC-D",
    "BC-E",
    "SC",
    "SC-I",
    "SC-II",
    "SC-III",
    "ST",
    "EWS",
]

_GUIDED_GENDER_OPTIONS = ["Boys", "Girls", "Both"]

# Dataset raw category aliases mapped to student-facing UI categories.
_GUIDED_CATEGORY_ALIAS_TO_CANONICAL = {
    "OC": "OC",
    "BC-A": "BC-A",
    "BC-B": "BC-B",
    "BC-C": "BC-C",
    "BC-D": "BC-D",
    "BC-E": "BC-E",
    "SC": "SC",
    "SC-I": "SC-I",
    "SC-II": "SC-II",
    "SC-III": "SC-III",
    "ST": "ST",
    "EWS": "EWS",
}

_GUIDED_SPECIAL_OR_INTERNAL_CATEGORIES = {"CAP", "NCC", "SPORTS", "OTHERS"}
_GUIDED_ALLOWED_CATEGORIES = set(_GUIDED_MAIN_CATEGORIES_ORDER)

# Year-specific SC category rules.
# 2025: use SC-I, SC-II, SC-III
# 2024, 2023, earlier: use SC only
_YEAR_SPECIFIC_SC_CATEGORIES = {
    2025: ["SC-I", "SC-II", "SC-III"],
    2024: ["SC"],
    2023: ["SC"],
}

# Canonical guided category -> raw dataset categories used for lookup.
_GUIDED_CATEGORY_LOOKUP_VALUES = {
    "SC": ["SC"],
    "SC-I": ["SC-I"],
    "SC-II": ["SC-II"],
    "SC-III": ["SC-III"],
}


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


def _is_sentence_like_input(text: str) -> bool:
    """Heuristic: detect user-typed sentence vs short option-like input."""
    stripped = text.strip()
    if not stripped:
        return False

    word_like_tokens = re.findall(
        r"[A-Za-z]+|[\u0900-\u097F]+|[\u0C00-\u0C7F]+|[\u0B80-\u0BFF]+|[\u0C80-\u0CFF]+|[\u0980-\u09FF]+|[\u0A80-\u0AFF]+",
        stripped,
    )
    return len(word_like_tokens) >= 3


def _is_internal_option_value_input(text: str) -> bool:
    """
    Detect internal/canonical option values coming from button clicks.
    These should never force a language switch.
    """
    normalized = re.sub(r"\s+", " ", text.strip().lower()).strip(" .:-")
    if not normalized:
        return False

    if normalized in {"1", "2", "3", "option 1", "option 2", "option 3", "choice 1", "choice 2", "choice 3"}:
        return True

    canonical_values = {
        "btech",
        "mtech",
        "mba_mca",
        "convener",
        "management",
        "supernumerary",
    }
    if normalized in canonical_values:
        return True

    normalized_selection = _normalize_selection_text(normalized)
    for details in _DOCUMENT_PROGRAM_DETAILS.values():
        if normalized_selection == _normalize_selection_text(details["canonical_label"]):
            return True
    for details in _DOCUMENT_CATEGORY_DETAILS.values():
        if normalized_selection == _normalize_selection_text(details["canonical_label"]):
            return True

    return False


def _should_pivot_language(session_language: str, detected_language: str, user_message: str) -> bool:
    """
    Allow automatic language pivot for native-script input while keeping
    internal option values language-locked.
    """
    if detected_language == session_language:
        return False
    if detected_language not in SUPPORTED_LANGUAGES:
        return False
    if _is_internal_option_value_input(user_message):
        return False
    # Any visible native script should pivot immediately (e.g., Marathi/Telugu words).
    if any(ord(char) > 127 for char in user_message):
        return True
    if _is_ambiguous_language_input(user_message):
        return False
    return _is_sentence_like_input(user_message)


def _resolve_effective_language(
    session_id: str,
    user_message: str,
    requested_language: str,
    force_language: bool = False,
) -> str:
    """
    Resolve response language with latest-message priority:
    1) internal button values never force language changes,
    2) visible native-script input pivots immediately to that script,
    3) short ASCII snippets keep current session language.
    4) explicit force-language is applied only for internal option inputs.
    """
    stripped_message = (user_message or "").strip()
    requested = _normalize_language_code(requested_language)
    if (
        force_language
        and requested in SUPPORTED_LANGUAGES
        and _is_internal_option_value_input(stripped_message)
    ):
        _SESSION_LANGUAGE_BY_ID[session_id] = requested
        return requested

    has_session_language = session_id in _SESSION_LANGUAGE_BY_ID
    session_language = _SESSION_LANGUAGE_BY_ID.get(session_id, requested)

    if _is_internal_option_value_input(stripped_message):
        # Hard-lock rule: internal button values (e.g., btech/convener/1/2/3)
        # must never drive language detection.
        # Prefer existing session language; if unavailable, honor requested language.
        resolved = session_language if has_session_language else requested
    else:
        detected = _normalize_language_code(detect_language(stripped_message))

        if not has_session_language:
            resolved = detected if detected in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        elif _should_pivot_language(
            session_language=session_language,
            detected_language=detected,
            user_message=stripped_message,
        ):
            resolved = detected
        elif (
            detected == DEFAULT_LANGUAGE
            and session_language != DEFAULT_LANGUAGE
            and _is_sentence_like_input(stripped_message)
            and not _is_ambiguous_language_input(stripped_message)
        ):
            resolved = DEFAULT_LANGUAGE
        else:
            resolved = session_language

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


def _get_document_program_label(program_key: str, language: str) -> str:
    """Get localized label for document program option."""
    details = _DOCUMENT_PROGRAM_DETAILS[program_key]
    return details["labels"].get(language, details["labels"]["en"])


def _get_document_category_label(category_key: str, language: str) -> str:
    """Get localized label for document category option."""
    details = _DOCUMENT_CATEGORY_DETAILS[category_key]
    return details["labels"].get(language, details["labels"]["en"])


def _get_document_category_prefix(category_key: str, language: str) -> str:
    """Get localized response prefix for selected document category."""
    details = _DOCUMENT_CATEGORY_DETAILS[category_key]
    return details["prefix"].get(language, details["prefix"]["en"])


def _normalize_selection_text(text: str) -> str:
    """Normalize button/typed selection text for robust matching."""
    lowered = text.strip().lower()
    # Normalize common unicode dashes to ascii hyphen before cleanup.
    lowered = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", lowered)
    lowered = lowered.replace("&", " and ").replace("/", " ")
    lowered = lowered.replace("_", "-")
    lowered = re.sub(r"[()\-.:]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def _resolve_user_visible_input(
    user_message: str,
    selected_option_label: Optional[str] = None,
    selected_option_value: Optional[str] = None,
) -> str:
    """
    Prefer user-visible option label over internal option values.
    If a UI sends hidden value (e.g., "btech"), use the visible label text.
    """
    raw_message = (user_message or "").strip()
    visible_label = (selected_option_label or "").strip()
    option_value = (selected_option_value or "").strip()

    if not visible_label:
        return raw_message
    if not raw_message:
        return visible_label

    if option_value:
        raw_normalized = _normalize_selection_text(raw_message)
        value_normalized = _normalize_selection_text(option_value)
        if raw_normalized == value_normalized:
            return visible_label

    if _is_internal_option_value_input(raw_message):
        return visible_label

    return raw_message


def _replace_raw_url_with_markdown_link(match: re.Match[str], link_label: str) -> str:
    """Replace a raw URL with a localized clickable markdown link."""
    raw_url = match.group("url")
    trimmed_url = raw_url.rstrip(".,;:!?")
    trailing = raw_url[len(trimmed_url):]
    normalized_url = trimmed_url
    if normalized_url.lower().startswith("www."):
        normalized_url = f"https://{normalized_url}"
    return f"[{link_label}]({normalized_url}){trailing}"


def _format_raw_urls_as_clickable_markdown(response_text: str, language: str) -> str:
    """Ensure raw URLs are rendered as clean clickable markdown links."""
    if not response_text:
        return response_text

    default_label = _get_localized_text(_DEFAULT_LINK_LABELS, language)
    club_label = _get_localized_text(_CLUB_LINK_LABELS, language)
    formatted_lines: list[str] = []
    for line in response_text.splitlines():
        if not _RAW_URL_PATTERN.search(line):
            formatted_lines.append(line)
            continue
        if re.search(r"\[[^\]]+\]\((?:https?://|www\.)[^\s\)]+\)", line, flags=re.IGNORECASE):
            formatted_lines.append(line)
            continue

        line_without_url = _RAW_URL_PATTERN.sub("", line)
        link_label = club_label if re.search(r"\bclub\b", line_without_url, flags=re.IGNORECASE) else default_label
        formatted_lines.append(_RAW_URL_PATTERN.sub(lambda m: _replace_raw_url_with_markdown_link(m, link_label), line))

    return "\n".join(formatted_lines)


def _is_transport_fee_query(user_message: str) -> bool:
    """Detect transport-fee intent from common user phrasings."""
    normalized = " ".join((user_message or "").lower().split())
    if not normalized:
        return False
    if any(phrase in normalized for phrase in _TRANSPORT_FEE_TRIGGER_PHRASES):
        return True

    has_transport_term = any(term in normalized for term in ("transport", "transportation", "bus", "travel"))
    has_fee_term = any(term in normalized for term in ("fee", "fees", "charge", "charges", "fare"))
    return has_transport_term and has_fee_term


def _normalize_link_url(raw_url: str) -> str:
    trimmed_url = (raw_url or "").rstrip(".,;:!?")
    if trimmed_url.lower().startswith("www."):
        return f"https://{trimmed_url}"
    return trimmed_url


def _extract_links_with_line_context(source_text: str) -> list[tuple[str, str]]:
    """Extract links while preserving their source line for label inference."""
    if not source_text:
        return []

    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in source_text.splitlines():
        for match in _MARKDOWN_URL_PATTERN.finditer(line):
            normalized_url = _normalize_link_url(match.group("url"))
            if normalized_url and normalized_url not in seen:
                links.append((normalized_url, line))
                seen.add(normalized_url)

        for match in _RAW_URL_PATTERN.finditer(line):
            normalized_url = _normalize_link_url(match.group("url"))
            if normalized_url and normalized_url not in seen:
                links.append((normalized_url, line))
                seen.add(normalized_url)

    return links


def _build_transport_fee_fallback_response(language: str) -> str:
    fallback_intro = _get_localized_text(_TRANSPORT_FEE_FALLBACK_TEXT, language)
    follow_up = _get_localized_text(_TRANSPORT_FEE_FALLBACK_FOLLOWUP_TEXT, language)
    website_label = _get_localized_text(_TRANSPORT_FALLBACK_WEBSITE_CTA_TEXT, language)
    return (
        f"{fallback_intro}\n"
        f"👉 [{website_label}]({_OFFICIAL_WEBSITE_URL})\n\n"
        f"{follow_up}"
    )


def _build_transport_fee_cta_response(source_text: str, language: str) -> str:
    """Build transport-fee CTA response from extracted links or fallback when unavailable."""
    extracted_links = _extract_links_with_line_context(source_text)
    if not extracted_links:
        return _build_transport_fee_fallback_response(language)

    first_year_url: Optional[str] = None
    other_years_url: Optional[str] = None
    additional_urls: list[str] = []

    for url, line in extracted_links:
        if _TRANSPORT_FIRST_YEAR_PATTERN.search(line) and first_year_url is None:
            first_year_url = url
            continue
        if _TRANSPORT_OTHER_YEARS_PATTERN.search(line) and other_years_url is None:
            other_years_url = url
            continue

        if first_year_url is None:
            first_year_url = url
        elif other_years_url is None:
            other_years_url = url
        else:
            additional_urls.append(url)

    intro = _get_localized_text(_TRANSPORT_FEE_INTRO_TEXT, language)
    first_year_label = _get_localized_text(_TRANSPORT_FIRST_YEAR_LABELS, language)
    other_years_label = _get_localized_text(_TRANSPORT_OTHER_YEARS_LABELS, language)
    additional_label = _get_localized_text(_TRANSPORT_ADDITIONAL_LABELS, language)
    cta_text = _get_localized_text(_TRANSPORT_CTA_TEXT, language)
    link_text = _get_localized_text(_TRANSPORT_LINK_TEXT, language)
    outro = _get_localized_text(_TRANSPORT_FEE_OUTRO_TEXT, language)
    follow_up = _get_localized_text(_TRANSPORT_FEE_FOLLOWUP_TEXT, language)

    lines: list[str] = [intro, ""]
    if first_year_url:
        lines.extend(
            [
                f"👉 **{first_year_label}**",
                f"{cta_text}: [{link_text}]({first_year_url})",
                "",
            ]
        )
    if other_years_url:
        lines.extend(
            [
                f"👉 **{other_years_label}**",
                f"{cta_text}: [{link_text}]({other_years_url})",
                "",
            ]
        )

    for index, url in enumerate(additional_urls, start=1):
        lines.extend(
            [
                f"👉 **{additional_label} {index}**",
                f"{cta_text}: [{link_text}]({url})",
                "",
            ]
        )

    lines.extend([outro, "", follow_up])
    return "\n".join(lines).strip()


def _is_context_dependent_followup(user_message: str) -> bool:
    """
    Detect short follow-up turns like "fees?" / "hostel?" that need prior context.
    """
    stripped = (user_message or "").strip()
    if not stripped:
        return False
    if _is_transport_fee_query(stripped):
        return False
    if _is_internal_option_value_input(stripped):
        return False
    if _extract_document_program_selection(stripped, allow_numeric=False):
        return False
    if _extract_document_category_selection(stripped, allow_numeric=False):
        return False
    if extract_branch(stripped):
        return False

    tokens = re.findall(
        r"[A-Za-z]+|[\u0900-\u097F]+|[\u0C00-\u0C7F]+|[\u0B80-\u0BFF]+|[\u0C80-\u0CFF]+|[\u0980-\u09FF]+|[\u0A80-\u0AFF]+",
        stripped.lower(),
    )
    if not tokens or len(tokens) > 4:
        return False
    if any(token in _INTERROGATIVE_TOKENS for token in tokens):
        return False

    lowered = stripped.lower()
    if len(tokens) <= 2:
        return stripped.endswith("?") or any(hint in lowered for hint in _SHORT_FOLLOWUP_HINTS)
    return any(hint in lowered for hint in _SHORT_FOLLOWUP_HINTS)


def _build_contextual_query(
    session_id: str,
    user_message: str,
    chat_history: Optional[list[ChatTurn]] = None,
) -> str:
    """Attach previous turn context for short follow-up questions."""
    history_block = _build_history_context_block(chat_history or [])
    if history_block:
        if _is_context_dependent_followup(user_message):
            return f"{history_block}\n\nCurrent follow-up question: {user_message}"
        return f"{history_block}\n\nCurrent user question: {user_message}"

    previous_query = (_SESSION_CONTEXT_BY_ID.get(session_id) or "").strip()
    if previous_query and _is_context_dependent_followup(user_message):
        return f"{previous_query}\n\nFollow-up question: {user_message}"
    return user_message


def _remember_session_context(session_id: str, context_text: str) -> None:
    """Persist bounded session context for short follow-up inference."""
    cleaned = (context_text or "").strip()
    if not cleaned:
        return
    if len(cleaned) > _MAX_SESSION_CONTEXT_CHARS:
        cleaned = cleaned[-_MAX_SESSION_CONTEXT_CHARS:]
    _SESSION_CONTEXT_BY_ID[session_id] = cleaned

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
_USER_TEXT_TOKEN_PATTERN = re.compile(
    r"[A-Za-z0-9]+|[\u0900-\u097F]+|[\u0C00-\u0C7F]+|[\u0B80-\u0BFF]+|[\u0C80-\u0CFF]+|[\u0980-\u09FF]+|[\u0A80-\u0AFF]+|[^\s]"
)

_LEAKED_ENGLISH_TERM_REPLACEMENTS = {
    "hi": [
        (r"\bb\.?\s*tech\b", "बी टेक"),
        (r"\bm\.?\s*tech\b", "एम टेक"),
        (r"\bm\.?\s*b\.?\s*a\b|\bmba\b", "एम बी ए"),
        (r"\bm\.?\s*c\.?\s*a\b|\bmca\b", "एम सी ए"),
        (r"\bmigration\s*certificate\b", "प्रवासन प्रमाणपत्र"),
        (r"\boriginal\s*\+\s*(\d+)\s*photocopies\b", r"मूल + \1 छायाप्रतियां"),
        (r"\boriginal\s*\+\s*photocopies\b", "मूल + छायाप्रतियां"),
        (r"\boriginal\s*\+\s*photocopy\b", "मूल + छायाप्रति"),
        (r"\bdocuments?\b", "दस्तावेज"),
        (r"\boriginal\b", "मूल"),
        (r"\bphotocopies\b", "छायाप्रतियां"),
        (r"\bphotocopy\b", "छायाप्रति"),
        (r"\brank\s*card\b", "रैंक कार्ड"),
        (r"\bintermediate\s*\(\s*10\+2\s*\)\s*marks\s*memo\b", "10+2 अंक ज्ञापन"),
        (r"\bmarks\s*memo\b", "अंक ज्ञापन"),
        (r"\bcategory\s*-?\s*a\b", "श्रेणी A"),
        (r"\bcategory\s*-?\s*b\b", "श्रेणी B"),
        (r"\btransfer\s*certificate\b", "स्थानांतरण प्रमाणपत्र"),
        (r"\bstudy\s*certificate\b", "अध्ययन प्रमाणपत्र"),
    ],
    "mr": [
        (r"\bb\.?\s*tech\b", "बी टेक"),
        (r"\bm\.?\s*tech\b", "एम टेक"),
        (r"\bm\.?\s*b\.?\s*a\b|\bmba\b", "एम बी ए"),
        (r"\bm\.?\s*c\.?\s*a\b|\bmca\b", "एम सी ए"),
        (r"\bdocuments?\b", "कागदपत्रे"),
        (r"\boriginal\b", "मूळ"),
        (r"\bphotocopies\b", "छायाप्रती"),
        (r"\bphotocopy\b", "छायाप्रत"),
        (r"\brank\s*card\b", "रँक कार्ड"),
        (r"\bintermediate\s*\(\s*10\+2\s*\)\s*marks\s*memo\b", "10+2 गुणपत्रक"),
        (r"\bmarks\s*memo\b", "गुणपत्रक"),
        (r"\bcategory\s*-?\s*a\b", "प्रवर्ग A"),
        (r"\bcategory\s*-?\s*b\b", "प्रवर्ग B"),
        (r"\btransfer\s*certificate\b", "स्थानांतरण प्रमाणपत्र"),
        (r"\bstudy\s*certificate\b", "अभ्यास प्रमाणपत्र"),
    ],
    "te": [
        (r"\bb\.?\s*tech\b", "బి టెక్"),
        (r"\bm\.?\s*tech\b", "ఎం టెక్"),
        (r"\bm\.?\s*b\.?\s*a\b|\bmba\b", "ఎం బి ఏ"),
        (r"\bm\.?\s*c\.?\s*a\b|\bmca\b", "ఎం సి ఏ"),
        (r"\bmigration\s*certificate\b", "వలస ధృవీకరణ పత్రం"),
        (r"\boriginal\s*\+\s*(\d+)\s*photocopies\b", r"అసలు + \1 నకలు"),
        (r"\boriginal\s*\+\s*photocopies\b", "అసలు + నకలు"),
        (r"\boriginal\s*\+\s*photocopy\b", "అసలు + నకలు"),
        (r"\bdocuments?\b", "పత్రాలు"),
        (r"\boriginal\b", "అసలు"),
        (r"\bphotocopies\b", "ఫోటోకాపీలు"),
        (r"\bphotocopy\b", "ఫోటోకాపీ"),
        (r"\brank\s*card\b", "ర్యాంక్ కార్డు"),
        (r"\btransfer\s*certificate\b", "బదిలీ ధ్రువపత్రం"),
        (r"\bstudy\s*certificate\b", "అధ్యయన ధ్రువపత్రం"),
    ],
    "ta": [
        (r"\boriginal\b", "அசல்"),
        (r"\bphotocopies\b", "நகல்கள்"),
        (r"\bphotocopy\b", "நகல்"),
        (r"\brank\s*card\b", "தரவரிசை அட்டை"),
        (r"\btransfer\s*certificate\b", "மாற்றுச் சான்றிதழ்"),
        (r"\bstudy\s*certificate\b", "படிப்பு சான்றிதழ்"),
    ],
    "kn": [
        (r"\boriginal\b", "ಮೂಲ"),
        (r"\bphotocopies\b", "ಛಾಯಾಪ್ರತಿಗಳು"),
        (r"\bphotocopy\b", "ಛಾಯಾಪ್ರತಿ"),
        (r"\brank\s*card\b", "ಶ್ರೇಣಿ ಕಾರ್ಡ್"),
        (r"\btransfer\s*certificate\b", "ಸ್ಥಳಾಂತರ ಪ್ರಮಾಣಪತ್ರ"),
        (r"\bstudy\s*certificate\b", "ಅಧ್ಯಯನ ಪ್ರಮಾಣಪತ್ರ"),
    ],
    "bn": [
        (r"\boriginal\b", "মূল"),
        (r"\bphotocopies\b", "ফটোকপি"),
        (r"\bphotocopy\b", "ফটোকপি"),
        (r"\brank\s*card\b", "র‍্যাঙ্ক কার্ড"),
        (r"\btransfer\s*certificate\b", "স্থানান্তর সনদ"),
        (r"\bstudy\s*certificate\b", "অধ্যয়ন সনদ"),
    ],
    "gu": [
        (r"\boriginal\b", "મૂળ"),
        (r"\bphotocopies\b", "ફોટોકોપીઓ"),
        (r"\bphotocopy\b", "ફોટોકોપી"),
        (r"\brank\s*card\b", "રેન્ક કાર્ડ"),
        (r"\btransfer\s*certificate\b", "સ્થાનાંતરણ પ્રમાણપત્ર"),
        (r"\bstudy\s*certificate\b", "અભ્યાસ પ્રમાણપત્ર"),
    ],
}


def _sanitize_non_english_response_leakage(response_text: str, language: str) -> str:
    """
    Replace common leaked English admission terms for selected native languages.
    This is a safety net after generation, especially for RAG content originally in English.
    """
    if not response_text or language == DEFAULT_LANGUAGE:
        return response_text

    replacements = _LEAKED_ENGLISH_TERM_REPLACEMENTS.get(language)
    if not replacements:
        return response_text

    sanitized = response_text
    for pattern, replacement in replacements:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    return sanitized


def _build_no_context_fallback_response(language: str) -> str:
    """Build graceful fallback response when retrieval has no relevant context."""
    acknowledgement = _get_localized_text(_RETRIEVE_NO_CONTEXT_RESPONSES, language)
    website_guidance = _get_localized_text(_NO_CONTEXT_WEBSITE_GUIDANCE, language)
    follow_up = _get_localized_text(_NO_CONTEXT_FOLLOWUP_QUESTIONS, language)
    return (
        f"{acknowledgement}\n\n"
        f"{website_guidance}\n"
        f"{_OFFICIAL_WEBSITE_URL}\n\n"
        f"{follow_up}"
    )


async def retrieve_and_respond(query: str, language: str = "en", additional_instructions: str = "") -> str:
    """Generate AI response using RAG pipeline."""
    
    # Retrieve relevant context
    retrieval_result = retrieve(query, top_k=5)

    if _is_transport_fee_query(query):
        context_for_links = retrieval_result.context_text if retrieval_result.chunks else ""
        return _build_transport_fee_cta_response(context_for_links, language)
    
    if not retrieval_result.chunks:
        return _build_no_context_fallback_response(language)
    
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
    system_prompt = f"""You are an intelligent conversational college assistant for VNRVJIET (VNR Vignana Jyothi Institute of Engineering and Technology).

Core behavior:
- Be natural, friendly, and counselor-like. Maintain conversation context and guide the user forward.
- Do not sound robotic. Keep answers concise but useful.
- Never use abrupt lines such as "No context found."

Response policy based on available context:
1) If relevant context is available:
   - Give a clear, structured, accurate answer grounded in context.
   - Summarize when helpful; do not dump raw chunks.
2) If context is partial:
   - Combine available context with cautious general reasoning.
   - Do not hallucinate specifics that are not supported.
   - Clearly keep uncertain parts general.
3) If answer is not available from context:
   - Politely acknowledge the limitation.
   - Suggest the official website and include this exact URL on its own line: {_OFFICIAL_WEBSITE_URL}
   - Optionally guide where to look (for example Administration/Announcements/Admissions pages).

Follow-up strategy:
- Continue the conversation naturally until the user query is fully resolved.
- If critical details are missing, ask a concise clarifying follow-up question.
- If the answer is complete, you may end with one relevant next-step question.
- Avoid repeating the same follow-up question unless the user has not provided the required detail.

For abstract or opinion-based queries (for example "Why should I join?", "What are disadvantages?", "Is it good for sports?"):
- Give a balanced summary using academics, infrastructure, placements, and extracurriculars.
- Avoid extreme positive/negative bias.

Link handling:
- If social media or external links are available in context, present them clearly with a short lead-in line and include the raw URL.
- Keep links uncluttered and easy to click.

Clarity handling:
- If user intent is ambiguous, ask a clarification question instead of guessing.

IMPORTANT language rule:
- You MUST respond ONLY in {language_name}.
- Do NOT switch to English unless the selected language is English.
- For non-English responses, avoid English words except mandatory acronyms such as TS EAPCET and JEE.
- For Marathi (मराठी), write the full response in Marathi script only.

Formatting rules:
- For steps/documents/requirements/fees or other multi-item details, use clean numbered lists (1., 2., 3.) with one item per line.
- Never merge multiple list items into one paragraph line.

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

Standard abbreviations (CSE, ECE, BC-D, OC) can remain as-is.

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

class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    language: str = "en"
    force_language: bool = False
    selected_option_label: Optional[str] = None
    selected_option_value: Optional[str] = None
    chat_history: list[ChatTurn] = Field(default_factory=list)

class ChatResponse(BaseModel):
    response: str
    intent: str = "informational"
    metadata: dict = Field(default_factory=dict)
    options: list[dict] = Field(default_factory=list)


def _is_required_documents_query(message: str) -> bool:
    """Return True when user asks required-documents style admission query."""
    normalized = " ".join(message.lower().split())
    return any(pattern.search(normalized) for pattern in _REQUIRED_DOCUMENT_PATTERNS)


def _remove_consecutive_duplicate_words(text: str) -> str:
    """Collapse repeated consecutive words from noisy speech-to-text input."""
    if not text:
        return text

    tokens = _USER_TEXT_TOKEN_PATTERN.findall(text)
    if not tokens:
        return text.strip()

    deduped_tokens: list[str] = []
    for token in tokens:
        if not deduped_tokens:
            deduped_tokens.append(token)
            continue

        previous = deduped_tokens[-1]
        if token.isalnum() and previous.isalnum() and token.casefold() == previous.casefold():
            continue
        deduped_tokens.append(token)

    joined = " ".join(deduped_tokens)
    joined = re.sub(r"\s+([,.;:!?])", r"\1", joined)
    joined = re.sub(r"([\(\[\{])\s+", r"\1", joined)
    joined = re.sub(r"\s+([\)\]\}])", r"\1", joined)
    return re.sub(r"\s+", " ", joined).strip()


def _normalize_user_message_text(text: str) -> str:
    """Normalize user input text while keeping semantic intent."""
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    return _remove_consecutive_duplicate_words(normalized)


def _build_history_context_block(chat_history: list[ChatTurn]) -> str:
    """Build compact dialogue context block from recent turns."""
    if not chat_history:
        return ""

    lines: list[str] = []
    for turn in chat_history[-_MAX_HISTORY_TURNS_FOR_CONTEXT:]:
        role = (turn.role or "").strip().lower()
        content = re.sub(r"\s+", " ", (turn.content or "").strip())
        if role not in {"user", "assistant"} or not content:
            continue

        speaker = "User" if role == "user" else "Assistant"
        if speaker == "User":
            content = _normalize_user_message_text(content)
        lines.append(f"{speaker}: {content}")

    if not lines:
        return ""

    return "Conversation history:\n" + "\n".join(lines)


def _extract_document_program_selection(message: str, allow_numeric: bool = True) -> Optional[str]:
    """Map user selection to canonical admission program."""
    normalized = re.sub(r"\s+", " ", message.strip().lower())
    if not normalized:
        return None

    normalized = normalized.strip(" .:-")
    normalized_selection = _normalize_selection_text(normalized)

    if allow_numeric and normalized in {"1", "option 1", "choice 1"}:
        return "btech"
    if allow_numeric and normalized in {"2", "option 2", "choice 2"}:
        return "mtech"
    if allow_numeric and normalized in {"3", "option 3", "choice 3"}:
        return "mba_mca"

    if normalized in _DOCUMENT_PROGRAM_DETAILS:
        return normalized

    for program_key, program_details in _DOCUMENT_PROGRAM_DETAILS.items():
        canonical_label = _normalize_selection_text(program_details["canonical_label"])
        if normalized_selection == canonical_label:
            return program_key

        for localized_label in program_details["labels"].values():
            label_candidate = _normalize_selection_text(localized_label)
            if normalized_selection == label_candidate:
                return program_key

    if normalized in {"btech", "b.tech", "b tech"} or re.search(r"\bb\.?\s*tech\b", normalized):
        return "btech"
    if normalized in {"mtech", "m.tech", "m tech"} or re.search(r"\bm\.?\s*tech\b", normalized):
        return "mtech"
    if (
        normalized in {"mba", "mca", "mba / mca", "mba/mca", "mba mca", "mba or mca"}
        or re.search(r"\bmba\b", normalized)
        or re.search(r"\bmca\b", normalized)
    ):
        return "mba_mca"

    if re.search(r"బి\.?\s*టెక్|బిటెక్", normalized):
        return "btech"
    if re.search(r"ఎం\.?\s*టెక్|ఎంటెక్", normalized):
        return "mtech"
    if re.search(r"ఎంబిఏ|ఎంసీఏ|ఎం\.?\s*బి\.?\s*ఏ|ఎం\.?\s*సి\.?\s*ఏ", normalized):
        return "mba_mca"

    if re.search(r"बी\.?\s*टेक|बिटेक", normalized):
        return "btech"
    if re.search(r"एम\.?\s*टेक|एमटेक", normalized):
        return "mtech"
    if re.search(r"एमबीए|एमसीए|एम\.?\s*बी\.?\s*ए|एम\.?\s*सी\.?\s*ए", normalized):
        return "mba_mca"

    return None


def _extract_document_category_selection(message: str, allow_numeric: bool = True) -> Optional[str]:
    """Map user selection to canonical admission document category."""
    normalized = re.sub(r"\s+", " ", message.strip().lower())
    if not normalized:
        return None

    normalized = normalized.strip(" .:-")
    normalized_selection = _normalize_selection_text(normalized)

    if allow_numeric and normalized in {"1", "option 1", "choice 1"}:
        return "convener"
    if allow_numeric and normalized in {"2", "option 2", "choice 2"}:
        return "management"
    if allow_numeric and normalized in {"3", "option 3", "choice 3"}:
        return "supernumerary"

    if normalized in _DOCUMENT_CATEGORY_DETAILS:
        return normalized

    for category_key, category_details in _DOCUMENT_CATEGORY_DETAILS.items():
        canonical_label = _normalize_selection_text(category_details["canonical_label"])
        if normalized_selection == canonical_label:
            return category_key

        for localized_label in category_details["labels"].values():
            label_candidate = _normalize_selection_text(localized_label)
            if normalized_selection == label_candidate:
                return category_key

    if re.search(r"\bconvener\b", normalized) or re.search(r"\bcategory\s*-?\s*a\b", normalized):
        return "convener"
    if re.search(r"కన్వీన", normalized) or re.search(r"కేటగిరీ\s*ఏ", normalized) or re.search(r"कन्वीन", normalized):
        return "convener"

    if (
        re.search(r"\bmanagement\b", normalized)
        or re.search(r"\bcategory\s*-?\s*b\b", normalized)
        or re.search(r"\bnri\b", normalized)
    ):
        return "management"
    if re.search(r"మేనేజ్|మెనేజ్|న్రి|ఎన్ఆర్ఐ|కేటగిరీ\s*బి", normalized) or re.search(r"मैनेज|एनआरआई", normalized):
        return "management"

    if re.search(r"\bsupernumerary\b", normalized):
        return "supernumerary"
    if re.search(r"సూపర్.?న్యూమరరీ", normalized) or re.search(r"सुपरन्यूमरेरी", normalized):
        return "supernumerary"

    return None


def _extract_cutoff_program_scope(message: str) -> Optional[str]:
    """Detect explicit program mention for cutoff queries (btech/mtech/mba_mca/other)."""
    program = _extract_document_program_selection(message, allow_numeric=False)
    if program:
        return program

    normalized = re.sub(r"\s+", " ", (message or "").strip().lower())
    if re.search(r"\bb\.?\s*e\b|\bbachelor\s+of\s+engineering\b", normalized):
        return "btech"
    if re.search(r"\bm\.?\s*e\b|\bmasters?\b|\bpost\s*graduate\b|\bpg\b", normalized):
        return "other"
    if re.search(r"\bph\.?d\b|\bdoctorate\b|\bdiploma\b", normalized):
        return "other"
    return None


def _is_non_convenor_quota_request(message: str, extracted_quota: Optional[str]) -> bool:
    """Return True if user explicitly asks cutoff for non-convener quota."""
    if extracted_quota and extracted_quota != "Convenor":
        return True

    normalized = re.sub(r"\s+", " ", (message or "").strip().lower())
    return bool(
        re.search(
            r"\b(management|category\s*-?\s*b|nri|sports|cap|ncc|supernumerary|quota\s*-?\s*b)\b",
            normalized,
        )
    )


def _build_document_program_prompt_response(language: str) -> ChatResponse:
    """Build program selection prompt with clickable options for documents flow."""
    prompt_text = _get_localized_text(_DOCUMENT_PROGRAM_PROMPTS, language)
    options: list[dict] = []
    for program_key in ("btech", "mtech", "mba_mca"):
        label = _get_document_program_label(program_key, language)
        options.append({"label": label, "value": program_key})

    prompt_lines = [f"{idx}. {option['label']}" for idx, option in enumerate(options, start=1)]
    return ChatResponse(
        response=f"{prompt_text}\n\n" + "\n".join(prompt_lines),
        intent="informational",
        metadata={"awaiting_document_program": True, "language": language},
        options=options,
    )


def _build_document_category_prompt_response(language: str, selected_program: str) -> ChatResponse:
    """Build category selection prompt with clickable options for documents flow."""
    program_label = _get_document_program_label(selected_program, language)
    prompt_template = _get_localized_text(_DOCUMENT_CATEGORY_PROMPTS, language)
    prompt_text = prompt_template.format(program=program_label)
    acknowledgement_template = _get_localized_text(_DOCUMENT_PROGRAM_ACKNOWLEDGEMENTS, language)
    acknowledgement = acknowledgement_template.format(program=program_label)
    options: list[dict] = []
    for category_key in ("convener", "management", "supernumerary"):
        label = _get_document_category_label(category_key, language)
        options.append({"label": label, "value": category_key})

    prompt_lines = [f"{idx}. {option['label']}" for idx, option in enumerate(options, start=1)]
    return ChatResponse(
        response=f"{acknowledgement}\n{prompt_text}\n\n" + "\n".join(prompt_lines),
        intent="informational",
        metadata={
            "awaiting_document_category": True,
            "document_program": selected_program,
            "document_program_label": program_label,
            "language": language,
        },
        options=options,
    )


async def _handle_required_documents_flow(
    user_message: str,
    session_id: str,
    language: str,
) -> Optional[ChatResponse]:
    """
    Context-aware required-documents flow:
    - capture program/category from the current message,
    - reuse known slots from session memory,
    - ask only for missing slots,
    - answer immediately when both slots are known.
    """
    flow_state = _DOCUMENT_FLOW_STATE_BY_SESSION.get(session_id)
    slot_state = _DOCUMENT_SLOT_MEMORY_BY_SESSION.get(session_id, {})
    is_documents_query = _is_required_documents_query(user_message)
    flow_active = bool(flow_state and flow_state.get("step") in {"awaiting_program", "awaiting_category"})

    if not is_documents_query and not flow_active:
        return None

    current_step = (flow_state or {}).get("step", "")
    allow_program_numeric = current_step == "awaiting_program"
    allow_category_numeric = current_step == "awaiting_category"

    extracted_program = _extract_document_program_selection(
        user_message,
        allow_numeric=allow_program_numeric,
    )
    extracted_category = _extract_document_category_selection(
        user_message,
        allow_numeric=allow_category_numeric,
    )

    if extracted_program:
        slot_state["program"] = extracted_program
    if extracted_category:
        slot_state["category"] = extracted_category

    selected_program = slot_state.get("program")
    selected_category = slot_state.get("category")

    if selected_program and selected_program not in _DOCUMENT_PROGRAM_DETAILS:
        slot_state.pop("program", None)
        selected_program = None
    if selected_category and selected_category not in _DOCUMENT_CATEGORY_DETAILS:
        slot_state.pop("category", None)
        selected_category = None

    _DOCUMENT_SLOT_MEMORY_BY_SESSION[session_id] = slot_state

    if not selected_program:
        _DOCUMENT_FLOW_STATE_BY_SESSION[session_id] = {"step": "awaiting_program"}
        return _build_document_program_prompt_response(language)

    if not selected_category:
        _DOCUMENT_FLOW_STATE_BY_SESSION[session_id] = {
            "step": "awaiting_category",
            "program": selected_program,
        }
        return _build_document_category_prompt_response(language, selected_program)

    _DOCUMENT_FLOW_STATE_BY_SESSION.pop(session_id, None)
    category_details = _DOCUMENT_CATEGORY_DETAILS[selected_category]
    program_details = _DOCUMENT_PROGRAM_DETAILS[selected_program]
    localized_label = _get_document_category_label(selected_category, language)
    localized_program = _get_document_program_label(selected_program, language)
    localized_prefix = _get_document_category_prefix(selected_category, language)

    category_prompt = (
        f"Required documents for {program_details['canonical_label']} program under "
        f"{category_details['canonical_label']} admission at VNRVJIET.\n"
        "Return only this selected program and category required admission documents."
    )
    additional_instructions = (
        f"The selected program is {localized_program}. "
        f"Start exactly with: \"{localized_prefix}\". "
        "Then list required documents as a clean bulleted list with one item per line. "
        "Do not include any other program or category. "
        "Keep wording speech-friendly for text-to-speech: short clear sentences, no emojis."
    )
    if language != DEFAULT_LANGUAGE:
        additional_instructions += (
            " Use only the selected language for the final response. "
            "Do not include English words or English translations in parentheses."
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
        metadata={
            "language": language,
            "document_program": selected_program,
            "document_program_label": localized_program,
            "document_category": selected_category,
            "document_category_label": localized_label,
        },
    )


def _is_cutoff_like_query(message: str) -> bool:
    """Return True when user likely wants branch-wise cutoff flow."""
    lowered = message.lower().strip()
    cutoff_keywords = (
        "cutoff",
        "cut off",
        "closing rank",
        "opening rank",
        "last rank",
        "branch-wise cutoff",
        "branch wise cutoff",
        "eapcet",
        "eamcet",
    )
    return any(keyword in lowered for keyword in cutoff_keywords)


def _build_branch_options() -> list[dict]:
    """
    Build branch options from full dataset values.
    Button value must be exact dataset branch key; label may be user-friendly.
    """
    available_raw = get_available_branches(quota="Convenor")
    if not available_raw:
        return []

    canonical_values: set[str] = set()
    for raw in available_raw:
        canonical = _to_guided_canonical_branch(str(raw or ""))
        if not canonical:
            continue
        canonical_values.add(canonical)

    ordered: list[str] = [code for code in _GUIDED_BRANCH_PREFERRED_ORDER if code in canonical_values]
    ordered.extend(sorted(code for code in canonical_values if code not in ordered))

    return [
        {
            "label": _GUIDED_BRANCH_DISPLAY_BY_CANONICAL.get(code, code),
            "value": code,
        }
        for code in ordered
    ]


def _build_category_options(branch: str, year: int = None) -> list[dict]:
    """Build category options for branch and optional year. SC variants are year-dependent."""
    rows = get_cutoffs_flexible(branch=branch, quota="Convenor", limit=0)

    canonical_found: set[str] = set()
    for row in rows:
        if not _row_has_valid_cutoff_data(row):
            continue
        value = str(row.get("category") or row.get("caste") or "").strip()
        if not value:
            continue
        canonical = _GUIDED_CATEGORY_ALIAS_TO_CANONICAL.get(value)
        if not canonical:
            continue
        if canonical in _GUIDED_SPECIAL_OR_INTERNAL_CATEGORIES:
            continue
        if canonical not in _GUIDED_ALLOWED_CATEGORIES:
            continue
        
        # Filter SC categories based on year if specified
        if year is not None:
            if canonical.startswith("SC"):
                # Get allowed SC categories for this year
                allowed_sc_cats = _YEAR_SPECIFIC_SC_CATEGORIES.get(year, ["SC"])
                if canonical not in allowed_sc_cats:
                    continue
        
        canonical_found.add(canonical)

    ordered = [cat for cat in _GUIDED_MAIN_CATEGORIES_ORDER if cat in canonical_found]
    ordered.extend(sorted(cat for cat in canonical_found if cat not in ordered))
    return [{"label": category, "value": category} for category in ordered]


def _get_lookup_categories_for_guided(category: str) -> list[str]:
    """Expand canonical guided category to one or more raw dataset categories."""
    return _GUIDED_CATEGORY_LOOKUP_VALUES.get(category, [category])


def _to_int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_has_valid_cutoff_data(row: dict) -> bool:
    """Treat rows with a positive closing/cutoff rank as valid guided data."""
    cutoff_rank = _to_int_or_none(row.get("cutoff_rank"))
    if cutoff_rank is not None and cutoff_rank > 0:
        return True

    last_rank = _to_int_or_none(row.get("last_rank"))
    if last_rank is not None and last_rank > 0:
        return True

    first_rank = _to_int_or_none(row.get("first_rank"))
    return first_rank is not None and first_rank > 0


def _build_gender_options(branch: str, year: int, category: str) -> list[dict]:
    raw_genders = {
        str(row.get("gender") or "").strip()
        for lookup_category in _get_lookup_categories_for_guided(category)
        for row in get_cutoffs_flexible(
            branch=branch,
            category=lookup_category,
            year=year,
            quota="Convenor",
            limit=0,
        )
        if _row_has_valid_cutoff_data(row)
    }

    has_any = "Any" in raw_genders
    has_boys = "Boys" in raw_genders or has_any
    has_girls = "Girls" in raw_genders or has_any

    available: list[str] = []
    if has_boys:
        available.append("Boys")
    if has_girls:
        available.append("Girls")
    if has_boys and has_girls:
        available.append("Both")

    ordered = [gender for gender in _GUIDED_GENDER_OPTIONS if gender in available]
    return [{"label": gender, "value": gender} for gender in ordered]


def _build_year_options(branch: str, category: str = None, gender: str = None) -> list[dict]:
    """Build year options. After branch selection, shows all available years.
    When called with category and gender, filters to years with data for that combination."""
    years_set: set[int] = set()
    
    if category is not None and gender is not None:
        # Filtered year options for specific category/gender combination
        if gender == "Both":
            genders_to_query = ["Boys", "Girls", "Any"]
        elif gender in {"Boys", "Girls"}:
            genders_to_query = [gender, "Any"]
        elif gender == "Any":
            genders_to_query = ["Any", "Boys", "Girls"]
        else:
            genders_to_query = [gender]

        for lookup_category in _get_lookup_categories_for_guided(category):
            for lookup_gender in genders_to_query:
                rows = get_cutoffs_flexible(
                    branch=branch,
                    category=lookup_category,
                    gender=lookup_gender,
                    quota="Convenor",
                    limit=0,
                )
                for row in rows:
                    if not _row_has_valid_cutoff_data(row):
                        continue
                    parsed_year = _to_int_or_none(row.get("year"))
                    if parsed_year is None:
                        continue
                    years_set.add(parsed_year)
    else:
        # All available years for branch (called right after branch selection)
        rows = get_cutoffs_flexible(branch=branch, quota="Convenor", limit=0)
        for row in rows:
            if not _row_has_valid_cutoff_data(row):
                continue
            parsed_year = _to_int_or_none(row.get("year"))
            if parsed_year is None:
                continue
            years_set.add(parsed_year)

    years = sorted(years_set, reverse=True)
    return [{"label": str(year), "value": str(year)} for year in years]


def _build_guided_prompt(prompt: str, options: list[dict], intent: str = "cutoff", metadata: Optional[dict] = None) -> ChatResponse:
    message = prompt
    return ChatResponse(
        response=message,
        intent=intent,
        metadata=metadata or {},
        options=options,
    )


def _resolve_selected_option(user_message: str, options: list[dict]) -> str | None:
    """Resolve selected option value from click payload or typed label/value text."""
    raw_candidate = user_message.strip()
    candidate = raw_candidate.lower()
    candidate_normalized = _normalize_selection_text(raw_candidate)
    if not candidate:
        return None

    for option in options:
        value = str(option.get("value", ""))
        label = str(option.get("label", ""))
        if candidate == value.lower() or candidate == label.lower():
            return value

        value_normalized = _normalize_selection_text(value)
        label_normalized = _normalize_selection_text(label)
        if candidate_normalized == value_normalized or candidate_normalized == label_normalized:
            return value
    return None


def _guided_cutoff_next_step(state: dict[str, str]) -> str:
    """Determine next missing step in branch -> year -> category -> gender order."""
    if not state.get("branch"):
        return "branch"
    if not state.get("year"):
        return "year"
    if not state.get("category"):
        return "category"
    if not state.get("gender"):
        return "gender"
    return "done"


def _build_cutoff_step_response(language: str, state: dict[str, str]) -> ChatResponse:
    """Build the next guided-flow response based on missing step.
    Flow order: branch -> year -> category -> gender."""
    _ = language
    step = _guided_cutoff_next_step(state)

    if step == "branch":
        options = _build_branch_options()
        return _build_guided_prompt(
            "Please select a branch:",
            options,
            metadata={"awaiting_cutoff_step": "branch"},
        )

    if step == "year":
        year_options = _build_year_options(state["branch"])
        if not year_options:
            return _build_guided_prompt(
                "No years available for this branch.",
                _build_branch_options(),
                metadata={"awaiting_cutoff_step": "branch"},
            )
        options = _with_guided_back_option(year_options)
        return _build_guided_prompt(
            "Please select year:",
            options,
            metadata={
                "awaiting_cutoff_step": "year",
                "branch": state["branch"],
            },
        )

    if step == "category":
        year = int(state["year"]) if state.get("year") else None
        category_options = _build_category_options(state["branch"], year)
        if not category_options:
            alt_year_options = _build_year_options(state["branch"])
            return _build_guided_prompt(
                "No categories available for this branch and year. Please select a different year:",
                alt_year_options,
                metadata={
                    "awaiting_cutoff_step": "year",
                    "branch": state["branch"],
                },
            )
        options = _with_guided_back_option(category_options)
        return _build_guided_prompt(
            "Please select your category/caste:",
            options,
            metadata={
                "awaiting_cutoff_step": "category",
                "branch": state["branch"],
                "year": state["year"],
            },
        )

    if step == "gender":
        gender_options = _build_gender_options(state["branch"], int(state["year"]), state["category"])
        if not gender_options:
            year = int(state["year"]) if state.get("year") else None
            alt_category_options = _build_category_options(state["branch"], year)
            return _build_guided_prompt(
                "No gender data available for this combination. Please select a different category:",
                alt_category_options,
                metadata={
                    "awaiting_cutoff_step": "category",
                    "branch": state["branch"],
                    "year": state["year"],
                },
            )
        options = _with_guided_back_option(gender_options)
        return _build_guided_prompt(
            "Please select gender:",
            options,
            metadata={
                "awaiting_cutoff_step": "gender",
                "branch": state["branch"],
                "year": state["year"],
                "category": state["category"],
            },
        )

    return ChatResponse(response="Please continue.", intent="cutoff")


async def _handle_guided_cutoff_flow(
    user_message: str,
    session_id: str,
    language: str,
) -> Optional[ChatResponse]:
    """Guided cutoff flow: branch -> year -> category -> gender -> final response."""
    state = _CUTOFF_FLOW_STATE_BY_SESSION.get(session_id)

    # Policy: cutoff ranks are only for B.Tech + Convener quota.
    scoped_program = _extract_cutoff_program_scope(user_message)
    if scoped_program and scoped_program != "btech":
        _CUTOFF_FLOW_STATE_BY_SESSION.pop(session_id, None)
        return ChatResponse(
            response=_get_localized_text(_CUTOFF_PROGRAM_UNAVAILABLE_RESPONSES, language),
            intent="cutoff",
            metadata={"language": language, "scope_restricted": True, "program": scoped_program},
        )

    if _is_non_convenor_quota_request(user_message, extract_quota(user_message)):
        _CUTOFF_FLOW_STATE_BY_SESSION.pop(session_id, None)
        return ChatResponse(
            response=_get_localized_text(_CUTOFF_QUOTA_UNAVAILABLE_RESPONSES, language),
            intent="cutoff",
            metadata={"language": language, "scope_restricted": True, "quota": "non-convenor"},
        )

    if state is None:
        if not _is_cutoff_like_query(user_message):
            return None
        state = {}
    elif state.get("step") == "result":
        if _is_guided_back_option_message(user_message):
            _apply_guided_back_action(state, "result")
            _CUTOFF_FLOW_STATE_BY_SESSION[session_id] = state
            return _build_cutoff_step_response(language, state)

        if not _is_cutoff_like_query(user_message):
            _CUTOFF_FLOW_STATE_BY_SESSION.pop(session_id, None)
            return None

        # New cutoff query after result starts a fresh guided attempt.
        state = {}

    current_step = _guided_cutoff_next_step(state)

    if current_step in {"year", "category", "gender"}:
        if _is_guided_back_option_message(user_message):
            _apply_guided_back_action(state, current_step)
            if _guided_cutoff_next_step(state) != "done":
                _CUTOFF_FLOW_STATE_BY_SESSION[session_id] = state
                return _build_cutoff_step_response(language, state)
            _CUTOFF_FLOW_STATE_BY_SESSION.pop(session_id, None)
            return _build_cutoff_step_response(language, state)

    if current_step == "branch":
        selected = _resolve_selected_option(user_message, _build_branch_options())
        if selected:
            state["branch"] = selected
    elif current_step == "year" and state.get("branch"):
        selected = _resolve_selected_option(user_message, _build_year_options(state["branch"]))
        if selected:
            state["year"] = selected
    elif current_step == "category" and state.get("branch") and state.get("year"):
        year = int(state["year"])
        selected = _resolve_selected_option(user_message, _build_category_options(state["branch"], year))
        if selected:
            state["category"] = selected
    elif current_step == "gender" and state.get("branch") and state.get("category"):
        gender_options = _build_gender_options(state["branch"], int(state["year"]), state["category"])
        selected = _resolve_selected_option(user_message, gender_options)
        if not selected:
            candidate = user_message.strip().lower()
            if candidate in {"any", "both"}:
                selected = "Both"
        if selected:
            state["gender"] = selected

    detected_branch = extract_branch(user_message)
    detected_category = extract_category(user_message)
    detected_gender = extract_gender(user_message)
    detected_year = extract_year(user_message)

    if detected_branch:
        if not state.get("branch"):
            state["branch"] = _to_guided_canonical_branch(detected_branch) or detected_branch
    if detected_year:
        state["year"] = str(detected_year)
    if detected_category and detected_category != "ALL":
        state["category"] = _GUIDED_CATEGORY_ALIAS_TO_CANONICAL.get(detected_category, detected_category)
    if detected_gender == "ALL":
        state["gender"] = "Both"
    elif detected_gender in {"Boys", "Girls"}:
        state["gender"] = detected_gender

    if _guided_cutoff_next_step(state) != "done":
        _CUTOFF_FLOW_STATE_BY_SESSION[session_id] = state
        return _build_cutoff_step_response(language, state)

    branch = state["branch"]
    category = state["category"]
    gender = state["gender"]
    year = int(state["year"])

    try:
        def _has_rank_data(candidate_result) -> bool:
            if candidate_result is None:
                return False
            if candidate_result.cutoff_rank is not None:
                return True
            if candidate_result.first_rank is not None or candidate_result.last_rank is not None:
                return True
            message = (candidate_result.message or "")
            return "**Last Rank" in message or "**First Rank" in message or "Closing" in message

        def _pick_best_result_for_gender(target_gender: str):
            result = None
            best_score = -1
            for lookup_category in _get_lookup_categories_for_guided(category):
                candidate = get_cutoff(
                    branch=branch,
                    category=lookup_category,
                    year=year,
                    gender=target_gender,
                    quota="Convenor",
                    language=language,
                )
                if not _has_rank_data(candidate) and target_gender in {"Boys", "Girls"}:
                    candidate_any = get_cutoff(
                        branch=branch,
                        category=lookup_category,
                        year=year,
                        gender="Any",
                        quota="Convenor",
                        language=language,
                    )
                    if _has_rank_data(candidate_any):
                        candidate = candidate_any

                if not _has_rank_data(candidate):
                    continue

                score = 0
                if candidate.cutoff_rank is not None:
                    score += 3
                if candidate.first_rank is not None:
                    score += 2
                if candidate.last_rank is not None:
                    score += 2
                if candidate.all_results:
                    score += 1
                if "**Branch:**" in (candidate.message or "") and "**Last Rank" in (candidate.message or ""):
                    score += 4

                if score > best_score:
                    best_score = score
                    result = candidate

            return result

        def _build_rank_block(label: str, candidate_result) -> str:
            if candidate_result is None or not _has_rank_data(candidate_result):
                return f"**{label}:** No cutoff data available."

            fr = candidate_result.first_rank
            lr = candidate_result.last_rank if candidate_result.last_rank is not None else candidate_result.cutoff_rank
            fr_str = f"{fr:,}" if fr is not None else "N/A"
            lr_str = f"{lr:,}" if lr is not None else "N/A"

            return (
                f"**{label}**\n"
                f"**Branch:** {candidate_result.branch or branch}\n"
                f"**Category:** {candidate_result.category or category}\n"
                f"**Gender:** {label}\n"
                f"**Quota:** {candidate_result.quota or 'Convenor'}\n"
                f"**Round:** {candidate_result.round if candidate_result.round is not None else '—'}\n"
                f"**First Rank (Opening):** {fr_str}\n"
                f"**Last Rank (Closing):** {lr_str}"
            )

        if gender == "Both":
            boys_result = _pick_best_result_for_gender("Boys")
            girls_result = _pick_best_result_for_gender("Girls")

            if _has_rank_data(boys_result) or _has_rank_data(girls_result):
                state["step"] = "result"
                _CUTOFF_FLOW_STATE_BY_SESSION[session_id] = state
                combined_message = (
                    f"**EAPCET Cutoff Ranks — {year}**\n\n"
                    f"{_build_rank_block('Boys', boys_result)}\n\n"
                    f"{'─' * 36}\n\n"
                    f"{_build_rank_block('Girls', girls_result)}\n\n"
                    "WARNING: Based on previous year data. Cutoffs may vary."
                )
                return ChatResponse(
                    response=combined_message,
                    intent="cutoff",
                    options=[{"label": _GUIDED_BACK_OPTION_LABEL, "value": _GUIDED_BACK_OPTION_VALUE}],
                    metadata={
                        "branch": branch,
                        "category": category,
                        "gender": gender,
                        "year": year,
                        "found": True,
                        "guided_flow": True,
                    },
                )

            alt_year_options = _build_year_options(branch, category, gender)
            state.pop("year", None)
            state.pop("step", None)
            _CUTOFF_FLOW_STATE_BY_SESSION[session_id] = state
            return _build_guided_prompt(
                "No cutoff data found for that selection. Please pick one of the available years:",
                alt_year_options,
                metadata={
                    "awaiting_cutoff_step": "year",
                    "branch": branch,
                    "category": category,
                    "gender": gender,
                    "guided_flow": True,
                },
            )

        result = _pick_best_result_for_gender(gender)
        has_data = _has_rank_data(result)

        if result is None:
            # Keep old behavior shape when no candidate returned data.
            result = get_cutoff(
                branch=branch,
                category=category,
                year=year,
                gender=gender,
                quota="Convenor",
                language=language,
            )
            has_data = _has_rank_data(result)
        if has_data:
            state["step"] = "result"
            _CUTOFF_FLOW_STATE_BY_SESSION[session_id] = state
            return ChatResponse(
                response=result.message,
                intent="cutoff",
                options=[{"label": _GUIDED_BACK_OPTION_LABEL, "value": _GUIDED_BACK_OPTION_VALUE}],
                metadata={
                    "branch": branch,
                    "category": category,
                    "gender": gender,
                    "year": year,
                    "found": True,
                    "guided_flow": True,
                },
            )

        alt_year_options = _build_year_options(branch, category, gender)
        state.pop("year", None)
        state.pop("step", None)
        _CUTOFF_FLOW_STATE_BY_SESSION[session_id] = state
        return _build_guided_prompt(
            "No cutoff data found for that selection. Please pick one of the available years:",
            alt_year_options,
            metadata={
                "awaiting_cutoff_step": "year",
                "branch": branch,
                "category": category,
                "gender": gender,
                "guided_flow": True,
            },
        )
    except Exception as e:
        logger.error(f"Guided cutoff flow failed: {e}")
        return ChatResponse(
            response=_get_localized_text(_CUTOFF_ENGINE_ERROR_RESPONSES, language),
            intent="cutoff",
            metadata={"error": str(e), "guided_flow": True},
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
    language = _normalize_language_code(response.metadata.get("language", DEFAULT_LANGUAGE))
    response.response = _sanitize_non_english_response_leakage(response.response, language)
    response.response = _normalize_admission_category_text(response.response)
    response.response = _enforce_structured_list_formatting(response.response, user_message)
    response.response = _format_raw_urls_as_clickable_markdown(response.response, language)
    return response


@router.post("/chat/reset")
async def reset_chat_session(request: ChatRequest):
    """Clear guided flow state so Home returns to a fresh main menu."""
    session_id = request.session_id or "default"
    _reset_guided_session_state(session_id)
    return {"ok": True}

@router.get("/config/languages")
async def get_enabled_languages():
    """Return list of enabled languages for the chatbot."""
    enabled = settings.get_enabled_languages()
    language_names = settings.get_enabled_language_names()
    return {
        "languages": enabled,
        "language_names": language_names,
        "mic_enabled": settings.ENABLE_MICROPHONE,
        "disclaimer": f"⚠️ Official assistant for VNRVJIET. Information is for guidance only. Multilingual chatbot - Available in {', '.join(language_names)} & more." if language_names else "⚠️ Official assistant for VNRVJIET. Information is for guidance only."
    }

@router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint that handles all user queries.
    Routes to appropriate engines based on intent classification.
    """
    try:
        raw_user_message = _normalize_user_message_text(request.message or "")
        session_id = request.session_id or "default"
        user_message = _resolve_user_visible_input(
            raw_user_message,
            request.selected_option_label,
            request.selected_option_value,
        )
        user_message = _normalize_user_message_text(user_message)
        effective_language = _resolve_effective_language(
            session_id=session_id,
            user_message=user_message,
            requested_language=request.language,
            force_language=request.force_language,
        )
        
        if not user_message:
            return _finalize_chat_response(ChatResponse(
                response=_get_localized_text(_EMPTY_MESSAGE_RESPONSES, effective_language),
                intent="greeting",
                metadata={"language": effective_language},
            ), user_message)
        
        logger.info(f"Processing query: {user_message[:100]}...")

        # Handle mandatory document program/category selection flow before generic intent routing.
        document_flow_response = await _handle_required_documents_flow(
            user_message=user_message,
            session_id=session_id,
            language=effective_language,
        )
        if document_flow_response is not None:
            _remember_session_context(session_id, user_message)
            return _finalize_chat_response(document_flow_response, user_message)

        cutoff_flow_response = await _handle_guided_cutoff_flow(
            user_message=user_message,
            session_id=session_id,
            language=effective_language,
        )
        if cutoff_flow_response is not None:
            return _finalize_chat_response(cutoff_flow_response, user_message)
        
        # Classify the user's intent
        intent_result = classify(user_message)

        if (
            intent_result.intent.value in {"informational", "mixed"}
            and _is_context_dependent_followup(user_message)
            and not (_SESSION_CONTEXT_BY_ID.get(session_id) or "").strip()
        ):
            return _finalize_chat_response(
                ChatResponse(
                    response=_get_localized_text(_AMBIGUOUS_CONTEXT_PROMPTS, effective_language),
                    intent="informational",
                    metadata={"language": effective_language, "needs_clarification": True},
                ),
                user_message,
            )
        
        if intent_result.intent.value == "cutoff":
            # Handle cutoff/eligibility queries
            return _finalize_chat_response(
                await handle_cutoff_query(
                    user_message,
                    intent_result,
                    effective_language,
                    session_id=session_id,
                ),
                user_message,
            )
        
        elif intent_result.intent.value == "mixed":
            # Handle mixed queries (RAG + cutoff)
            return _finalize_chat_response(
                await handle_mixed_query(
                    user_message,
                    intent_result,
                    effective_language,
                    session_id=session_id,
                    chat_history=request.chat_history,
                ),
                user_message,
            )
        
        elif intent_result.intent.value == "greeting":
            return _finalize_chat_response(ChatResponse(
                response=get_greeting_message(effective_language),
                intent="greeting",
                metadata={"language": effective_language},
            ), user_message)
        
        elif intent_result.intent.value == "out_of_scope":
            return _finalize_chat_response(ChatResponse(
                response=get_out_of_scope_message(effective_language),
                intent="out_of_scope",
                metadata={"language": effective_language},
            ), user_message)
        
        else:
            # Default to RAG for informational queries
            return _finalize_chat_response(
                await handle_informational_query(
                    user_message,
                    intent_result,
                    effective_language,
                    session_id=session_id,
                    chat_history=request.chat_history,
                ),
                user_message,
            )
            
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")

async def handle_cutoff_query(
    user_message: str,
    intent_result: ClassificationResult,
    language: str = "en",
    session_id: str = "default",
) -> ChatResponse:
    """Handle queries that need cutoff/eligibility data from Firestore."""
    
    # Extract parameters with session-slot inheritance for follow-up queries.
    slot_state = dict(_SESSION_CUTOFF_SLOT_MEMORY_BY_SESSION.get(session_id, {}))

    extracted_branch = extract_branch(user_message)
    extracted_category = extract_category(user_message)
    extracted_gender = extract_gender(user_message)
    extracted_year = extract_year(user_message)
    extracted_quota = extract_quota(user_message)
    scoped_program = _extract_cutoff_program_scope(user_message)

    # Policy: only B.Tech + Convener quota cutoff data is supported.
    if scoped_program and scoped_program != "btech":
        return ChatResponse(
            response=_get_localized_text(_CUTOFF_PROGRAM_UNAVAILABLE_RESPONSES, language),
            intent="cutoff",
            metadata={"language": language, "scope_restricted": True, "program": scoped_program},
        )

    if _is_non_convenor_quota_request(user_message, extracted_quota):
        return ChatResponse(
            response=_get_localized_text(_CUTOFF_QUOTA_UNAVAILABLE_RESPONSES, language),
            intent="cutoff",
            metadata={"language": language, "scope_restricted": True, "quota": "non-convenor"},
        )

    branch = extracted_branch or slot_state.get("branch")
    category = extracted_category or slot_state.get("category")
    gender = extracted_gender or slot_state.get("gender", "Any")
    year = extracted_year if extracted_year is not None else slot_state.get("year")
    quota = extracted_quota or slot_state.get("quota", "Convenor")
    rank = extract_rank(user_message)

    if branch:
        slot_state["branch"] = branch
    if category:
        slot_state["category"] = category
    if extracted_gender:
        slot_state["gender"] = extracted_gender
    if year is not None:
        slot_state["year"] = year
    if quota:
        slot_state["quota"] = quota
    _SESSION_CUTOFF_SLOT_MEMORY_BY_SESSION[session_id] = slot_state
    _remember_session_context(session_id, user_message)
    
    logger.info(f"Extracted parameters: branch={branch}, category={category}, gender={gender}, year={year}, quota={quota}")
    
    # Validate required parameters
    if not branch:
        return ChatResponse(
            response=_build_missing_branch_response_text(language),
            intent="cutoff",
            metadata={"error": "missing_branch", "language": language}
        )
    
    if not category:
        return ChatResponse(
            response=_build_missing_category_response_text(language),
            intent="cutoff", 
            metadata={"error": "missing_category", "language": language}
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
            scope_note = _get_localized_text(_CUTOFF_SCOPE_NOTE_RESPONSES, language)
            response_text = f"{scope_note}\n\n{result.message}"
        else:
            response_text = result.message or _build_missing_category_response_text(language)
        
        return ChatResponse(
            response=response_text,
            intent="cutoff",
            metadata={
                "language": language,
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
            metadata={"error": str(e), "language": language}
        )

async def handle_mixed_query(
    user_message: str,
    intent_result: ClassificationResult,
    language: str = "en",
    session_id: str = "default",
    chat_history: Optional[list[ChatTurn]] = None,
) -> ChatResponse:
    """Handle queries that need both RAG context and cutoff data."""

    # Policy guard for cutoff mentions in mixed queries.
    if _is_cutoff_like_query(user_message):
        scoped_program = _extract_cutoff_program_scope(user_message)
        if scoped_program and scoped_program != "btech":
            return ChatResponse(
                response=_get_localized_text(_CUTOFF_PROGRAM_UNAVAILABLE_RESPONSES, language),
                intent="mixed",
                metadata={"has_cutoff": False, "language": language, "scope_restricted": True},
            )
        if _is_non_convenor_quota_request(user_message, extract_quota(user_message)):
            return ChatResponse(
                response=_get_localized_text(_CUTOFF_QUOTA_UNAVAILABLE_RESPONSES, language),
                intent="mixed",
                metadata={"has_cutoff": False, "language": language, "scope_restricted": True},
            )
    
    contextual_query = _build_contextual_query(session_id, user_message, chat_history)
    _remember_session_context(session_id, contextual_query)

    # First get RAG context
    rag_response = await retrieve_and_respond(contextual_query, language)
    
    # Then try to add cutoff data if relevant
    branch = extract_branch(user_message)
    category = extract_category(user_message)
    
    if branch and category:
        try:
            cutoff_result = get_cutoff(branch=branch, category=category, language=language)
            if cutoff_result.found:
                scope_note = _get_localized_text(_CUTOFF_SCOPE_NOTE_RESPONSES, language)
                combined_response = rag_response + "\n\n" + scope_note + "\n\n" + cutoff_result.message
                return ChatResponse(
                    response=combined_response,
                    intent="mixed",
                    metadata={"has_cutoff": True, "branch": branch, "category": category, "language": language}
                )
        except Exception as e:
            logger.warning(f"Failed to add cutoff data to mixed query: {e}")
    
    return ChatResponse(
        response=rag_response,
        intent="mixed",
        metadata={"has_cutoff": False, "language": language}
    )

async def handle_informational_query(
    user_message: str,
    intent_result: ClassificationResult,
    language: str = "en",
    session_id: str = "default",
    chat_history: Optional[list[ChatTurn]] = None,
) -> ChatResponse:
    """Handle general informational queries using RAG."""
    
    try:
        contextual_query = _build_contextual_query(session_id, user_message, chat_history)
        _remember_session_context(session_id, contextual_query)
        response_text = await retrieve_and_respond(contextual_query, language)
        
        return ChatResponse(
            response=response_text,
            intent="informational",
            metadata={"language": language}
        )
        
    except Exception as e:
        logger.error(f"RAG error: {e}")
        return ChatResponse(
            response=_get_localized_text(_RAG_ERROR_RESPONSES, language),
            intent="informational",
            metadata={"error": str(e), "language": language}
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
    effective_language = _SESSION_LANGUAGE_BY_ID.get(session_id, _normalize_language_code(request.language))

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

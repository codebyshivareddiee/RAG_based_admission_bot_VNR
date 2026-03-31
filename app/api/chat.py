"""
Chat API endpoint for VNRVJIET Admissions Chatbot.
Handles user queries with proper parameter extraction and intent classification.
"""

from __future__ import annotations

import logging
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import asyncio

from app.classifier.intent_classifier import classify, ClassificationResult, IntentType
from app.logic.cutoff_engine import get_cutoff
from app.rag.retriever import retrieve
from openai import AsyncOpenAI
from app.config import get_settings

settings = get_settings()

_async_openai_client: AsyncOpenAI | None = None

def _get_async_openai() -> AsyncOpenAI:
    global _async_openai_client
    if _async_openai_client is None:
        _async_openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _async_openai_client

async def retrieve_and_respond(query: str, language: str = "en") -> str:
    """Generate AI response using RAG pipeline."""
    
    # Retrieve relevant context
    retrieval_result = retrieve(query, top_k=5)
    
    if not retrieval_result.chunks:
        return "I don't have specific information about that in my knowledge base. Please contact our admissions office for detailed information."
    
    # Generate response using GPT with retrieved context
    system_prompt = f"""You are a helpful AI assistant for VNRVJIET (VNR Vignana Jyothi Institute of Engineering and Technology) admissions.

Use the provided context to answer questions accurately. If the context doesn't contain the answer, say so clearly.

Respond in {language} language if requested, otherwise use English.

Keep responses informative but concise. Include specific details like numbers, dates, and procedures when available.

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
    metadata: dict = {}

@router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint that handles all user queries.
    Routes to appropriate engines based on intent classification.
    """
    try:
        user_message = request.message.strip()
        
        if not user_message:
            return ChatResponse(
                response="Please ask me something about VNRVJIET admissions!",
                intent="greeting"
            )
        
        logger.info(f"Processing query: {user_message[:100]}...")
        
        # Classify the user's intent
        intent_result = classify(user_message)
        
        if intent_result.intent.value == "cutoff":
            # Handle cutoff/eligibility queries
            return await handle_cutoff_query(user_message, intent_result)
        
        elif intent_result.intent.value == "mixed":
            # Handle mixed queries (RAG + cutoff)
            return await handle_mixed_query(user_message, intent_result)
        
        elif intent_result.intent.value == "greeting":
            return ChatResponse(
                response=_get_greeting_response(request.language),
                intent="greeting"
            )
        
        elif intent_result.intent.value == "out_of_scope":
            return ChatResponse(
                response="I can only help with VNRVJIET admissions queries. Please ask about our college programs, cutoffs, or admission procedures.",
                intent="out_of_scope"
            )
        
        else:
            # Default to RAG for informational queries
            return await handle_informational_query(user_message, intent_result)
            
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")

async def handle_cutoff_query(user_message: str, intent_result: ClassificationResult) -> ChatResponse:
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
            response=(
                "Please specify which branch you're asking about. "
                "Available branches: CSE, ECE, EEE, IT, MECH, CIVIL, CSE (AI & ML), CSE (Data Science), etc.\n\n"
                "Example: 'What is the cutoff for CSE branch?'"
            ),
            intent="cutoff",
            metadata={"error": "missing_branch"}
        )
    
    if not category:
        return ChatResponse(
            response=(
                "Please specify your category. "
                "Available categories: OC, BC-A, BC-B, BC-D, BC-E, SC, ST, EWS.\n\n"
                "Example: 'What is the BC-D cutoff for CSE?'"
            ),
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
            quota=quota
        )

        # Be defensive: treat data as found when any concrete cutoff payload exists,
        # even if a legacy engine path forgets to set `found=True`.
        has_data = bool(result.found) or bool(result.all_results) or (result.cutoff_rank is not None)
        
        if has_data:
            response_text = result.message
        else:
            # Data not found - provide helpful suggestions
            response_text = (
                f"No cutoff data found for **{branch}** branch, **{category}** category"
                + (f", **{year}**" if year else "")
                + (f", **{gender}**" if gender != "Any" else "")
                + f", {quota} quota.\n\n"
                "**Possible reasons:**\n"
                "• Data for this specific combination may not be available\n"
                "• Try different year (2024, 2025) or category\n"
                "• Check if branch name is correct (CSE, ECE, IT, etc.)\n\n"
                "**Available branches:** CSE, ECE, EEE, IT, MECH, CIVIL, CSE (AI & ML), CSE (Data Science)\n"
                "**Available categories:** OC, BC-A, BC-B, BC-D, BC-E, SC, ST, EWS"
            )
        
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
            response=f"Sorry, there was an error retrieving cutoff data. Please try again or contact support.",
            intent="cutoff",
            metadata={"error": str(e)}
        )

async def handle_mixed_query(user_message: str, intent_result: ClassificationResult) -> ChatResponse:
    """Handle queries that need both RAG context and cutoff data."""
    
    # First get RAG context
    rag_response = await retrieve_and_respond(user_message, "en")
    
    # Then try to add cutoff data if relevant
    branch = extract_branch(user_message)
    category = extract_category(user_message)
    
    if branch and category:
        try:
            cutoff_result = get_cutoff(branch=branch, category=category)
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

async def handle_informational_query(user_message: str, intent_result: ClassificationResult) -> ChatResponse:
    """Handle general informational queries using RAG."""
    
    try:
        response_text = await retrieve_and_respond(user_message, "en")
        
        return ChatResponse(
            response=response_text,
            intent="informational"
        )
        
    except Exception as e:
        logger.error(f"RAG error: {e}")
        return ChatResponse(
            response="I apologize, but I'm having trouble finding information about that. Please try rephrasing your question or contact our admissions office.",
            intent="informational",
            metadata={"error": str(e)}
        )

def _get_greeting_response(language: str) -> str:
    """Get appropriate greeting response based on language."""
    
    greetings = {
        "en": "Hello! I'm the VNRVJIET Admissions Assistant. I can help you with information about our programs, admission procedures, cutoff ranks, and eligibility criteria. What would you like to know?",
        "hi": "नमस्ते! मैं VNRVJIET प्रवेश सहायक हूं। मैं आपको हमारे कार्यक्रमों, प्रवेश प्रक्रियाओं, कटऑफ रैंक और पात्रता मानदंडों के बारे में जानकारी देने में मदद कर सकता हूं। आप क्या जानना चाहते हैं?",
        "te": "హలో! నేను VNRVJIET అడ్మిషన్స్ అసిస్టెంట్. మా ప్రోగ్రామ్స్, అడ్మిషన్ విధానాలు, కట్‌ఆఫ్ ర్యాంకులు మరియు అర్హత ప్రమాణాల గురించి మీకు సమాచారం అందించగలను. మీరు ఏమి తెలుసుకోవాలనుకుంటున్నారు?",
        "ta": "வணக்கம்! நான் VNRVJIET சேர்க்கை உதவியாளர். எங்கள் நிகழ்ச்சிகள், சேர்க்கை முறைகள், கட் ஆஃப் தரவரிசைகள் மற்றும் தகுதி அளவுகோல்கள் பற்றிய தகவல்களை உங்களுக்கு வழங்க முடியும். நீங்கள் என்ன தெரிந்துகொள்ள விரும்புகிறீர்கள்?",
        "mr": "नमस्कार! मी VNRVJIET प्रवेश सहाय्यक आहे. मी आमच्या कार्यक्रम, प्रवेश प्रक्रिया, कटऑफ रँक आणि पात्रता निकषांबद्दल माहिती देऊ शकतो. तुम्हाला काय जाणून घ्यायचे आहे?",
        "kn": "ನಮಸ್ಕಾರ! ನಾನು VNRVJIET ಪ್ರವೇಶ ಸಹಾಯಕ. ನಮ್ಮ ಕಾರ್ಯಕ್ರಮಗಳು, ಪ್ರವೇಶ ವಿಧಾನಗಳು, ಕಟ್‌ಆಫ್ ಶ್ರೇಣಿಗಳು ಮತ್ತು ಅರ್ಹತಾ ಮಾನದಂಡಗಳ ಬಗ್ಗೆ ಮಾಹಿತಿ ನೀಡಬಲ್ಲೆ. ನೀವು ಏನು ತಿಳಿಯಲು ಬಯಸುತ್ತೀರಿ?"
    }
    
    return greetings.get(language, greetings["en"])

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
    try:
        # Process the chat request normally
        response = await chat_endpoint(request)
        
        # Stream the response token by token
        async def generate_stream():
            """Generate streaming response in SSE format."""
            
            # Split response into tokens (words) for streaming effect
            words = response.response.split()
            
            for i, word in enumerate(words):
                # Send each word as a streaming token
                yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                # Small delay for typing effect
                await asyncio.sleep(0.05)
            
            # Send completion signal with metadata
            final_data = {
                "done": True,
                "intent": response.intent,
                "metadata": response.metadata,
                "session_id": request.session_id
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
                "error": "Sorry, I'm having trouble processing your request. Please try again.",
                "done": True
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            
        return StreamingResponse(
            error_stream(),
            media_type="text/plain"
        )
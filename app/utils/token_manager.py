"""
Token management utilities for OpenAI API calls.

Handles:
- Token counting with tiktoken
- Smart context trimming
- Conversation history summarization
- Warning logs when approaching limits
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import tiktoken

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)

# Token limits for different models (leaving safety margin)
MODEL_LIMITS = {
    "gpt-4o-mini": 128000,
    "gpt-4o": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
}

# Safety thresholds
WARNING_THRESHOLD = 0.8  # Warn at 80% of limit
SUMMARY_THRESHOLD = 0.7  # Start summarizing at 70%
MAX_RESPONSE_TOKENS = 600  # Reserve for response


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """
    Count the number of tokens in a text string for a specific model.
    
    Args:
        text: The text to count tokens for
        model: The OpenAI model name
        
    Returns:
        Number of tokens
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to cl100k_base encoding (used by gpt-4, gpt-3.5-turbo, etc)
        encoding = tiktoken.get_encoding("cl100k_base")
    
    return len(encoding.encode(text))


def count_messages_tokens(messages: list[dict], model: str = "gpt-4o-mini") -> int:
    """
    Count tokens for a list of messages (OpenAI chat format).
    
    This accounts for message formatting overhead.
    Based on: https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        model: The OpenAI model name
        
    Returns:
        Total token count including formatting
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    
    tokens_per_message = 3  # every message follows <|start|>{role/name}\n{content}<|end|>\n
    tokens_per_name = 1
    
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(str(value)))
            if key == "name":
                num_tokens += tokens_per_name
    
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens


def get_available_tokens(
    model: str = "gpt-4o-mini",
    reserve_for_response: int = MAX_RESPONSE_TOKENS
) -> int:
    """
    Get the number of tokens available for context.
    
    Args:
        model: The OpenAI model name
        reserve_for_response: Tokens to reserve for the response
        
    Returns:
        Available tokens for context
    """
    model_limit = MODEL_LIMITS.get(model, 128000)
    return model_limit - reserve_for_response


def should_warn(current_tokens: int, model: str = "gpt-4o-mini") -> bool:
    """Check if we should log a warning about token usage."""
    limit = MODEL_LIMITS.get(model, 128000)
    return current_tokens >= (limit * WARNING_THRESHOLD)


def should_summarize(current_tokens: int, model: str = "gpt-4o-mini") -> bool:
    """Check if we should summarize history to reduce tokens."""
    limit = MODEL_LIMITS.get(model, 128000)
    return current_tokens >= (limit * SUMMARY_THRESHOLD)


def summarize_conversation(
    history: list[dict],
    client: OpenAI,
    model: str = "gpt-4o-mini"
) -> dict:
    """
    Summarize a conversation history into a single context message.
    
    Args:
        history: List of conversation messages
        client: OpenAI client instance
        model: Model to use for summarization
        
    Returns:
        A single message dict with the summary
    """
    if not history:
        return {"role": "system", "content": ""}
    
    # Build prompt for summarization
    conversation_text = "\n".join([
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in history
    ])
    
    summary_prompt = f"""Summarize this conversation between a user and an admissions assistant. 
Preserve all important details like:
- Specific ranks, cutoffs, or eligibility mentioned
- Branch, category, gender preferences discussed
- Key questions asked and answers given
- Any pending information requests

Be concise but complete.

CONVERSATION:
{conversation_text}

SUMMARY:"""
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        
        summary = response.choices[0].message.content.strip()
        logger.info(f"Summarized {len(history)} messages into {count_tokens(summary)} tokens")
        
        return {
            "role": "system",
            "content": f"Previous conversation summary: {summary}"
        }
    except Exception as e:
        logger.error(f"Failed to summarize conversation: {e}")
        # Return a simple summary as fallback
        return {
            "role": "system",
            "content": f"Previous conversation included {len(history)} messages."
        }


def trim_history_smart(
    history: list[dict],
    system_prompt: str,
    user_message: str,
    context: str,
    cutoff_info: str,
    client: OpenAI,
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """
    Smart trimming that preserves important context and uses summarization.
    
    Strategy:
    1. Count total tokens
    2. If over SUMMARY_THRESHOLD, summarize old messages
    3. Keep recent messages intact for continuity
    4. Always preserve system prompt and current query
    
    Args:
        history: Conversation history
        system_prompt: System prompt text
        user_message: Current user message
        context: RAG context
        cutoff_info: Cutoff data
        client: OpenAI client
        model: Model name
        
    Returns:
        Optimally trimmed history
    """
    if not history:
        return []
    
    # Calculate token counts for fixed components
    system_tokens = count_tokens(system_prompt, model)
    user_tokens = count_tokens(user_message, model)
    context_tokens = count_tokens(context, model) if context else 0
    cutoff_tokens = count_tokens(cutoff_info, model) if cutoff_info else 0
    
    fixed_tokens = system_tokens + user_tokens + context_tokens + cutoff_tokens
    available_for_history = get_available_tokens(model) - fixed_tokens
    
    logger.debug(f"Token budget: fixed={fixed_tokens}, available_for_history={available_for_history}")
    
    # Count history tokens
    history_tokens = count_messages_tokens(history, model)
    
    if history_tokens <= available_for_history:
        # No trimming needed
        return history
    
    logger.info(f"History tokens ({history_tokens}) exceed available budget ({available_for_history})")
    
    # Strategy: Keep last N messages, summarize the rest
    RECENT_MESSAGES_TO_KEEP = 4  # Keep last 2 exchanges (4 messages)
    
    if len(history) <= RECENT_MESSAGES_TO_KEEP:
        # If history is already small, just return it
        return history
    
    # Split history
    old_history = history[:-RECENT_MESSAGES_TO_KEEP]
    recent_history = history[-RECENT_MESSAGES_TO_KEEP:]
    
    # Summarize old history
    logger.info(f"Summarizing {len(old_history)} old messages")
    summary_msg = summarize_conversation(old_history, client, model)
    
    # Build new history: [summary, recent messages]
    new_history = [summary_msg] + recent_history if summary_msg["content"] else recent_history
    
    # Verify it fits
    new_history_tokens = count_messages_tokens(new_history, model)
    
    if new_history_tokens > available_for_history:
        # Still too large, keep only recent messages
        logger.warning(f"Even after summarization, history too large. Keeping only recent messages.")
        return recent_history[-2:]  # Keep only last exchange
    
    logger.info(f"History optimized: {history_tokens} -> {new_history_tokens} tokens")
    return new_history


def log_token_usage(
    messages: list[dict],
    model: str,
    session_id: str = "unknown"
) -> None:
    """
    Log token usage statistics and warnings.
    
    Args:
        messages: Messages being sent to OpenAI
        model: Model name
        session_id: Session identifier for logging
    """
    total_tokens = count_messages_tokens(messages, model)
    limit = MODEL_LIMITS.get(model, 128000)
    percentage = (total_tokens / limit) * 100
    
    logger.debug(
        f"Session {session_id}: {total_tokens} tokens ({percentage:.1f}% of {limit} limit)"
    )
    
    if should_warn(total_tokens, model):
        logger.warning(
            f"⚠️  Session {session_id}: High token usage! "
            f"{total_tokens}/{limit} tokens ({percentage:.1f}%)"
        )

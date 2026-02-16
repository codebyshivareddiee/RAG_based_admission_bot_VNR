# Token Management System

## Overview

The chatbot now includes comprehensive token management to handle OpenAI API context limits efficiently.

## Features

### 1. **Token Counting with tiktoken**
- Accurate token counts for all models
- Real-time monitoring of token usage
- Model-specific encoding support

### 2. **Smart Context Trimming**
- Automatically trims conversation history when approaching limits
- Preserves recent messages for context continuity
- Summarizes older messages to reduce token count

### 3. **Warning System**
- **80% threshold**: Logs warning when token usage reaches 80% of model limit
- **70% threshold**: Automatically triggers summarization
- Helps prevent unexpected API failures

### 4. **Error Recovery**
- Catches token limit errors from OpenAI
- Automatically retries with minimal context
- Provides helpful error messages to users

### 5. **Conversation Summarization**
- Uses GPT-4o-mini to summarize old messages
- Preserves important details (ranks, cutoffs, preferences)
- Reduces token count while maintaining context

## Token Limits by Model

| Model | Context Window | Reserved for Response | Available for Context |
|-------|---------------|----------------------|----------------------|
| gpt-4o-mini | 128,000 | 600 | 127,400 |
| gpt-4o | 128,000 | 600 | 127,400 |
| gpt-4 | 8,192 | 600 | 7,592 |
| gpt-3.5-turbo | 16,385 | 600 | 15,785 |

## How It Works

### Normal Operation (< 70% of limit)
```
User message → History (last 10 messages) → OpenAI → Response
```

### High Usage (70-80% of limit)
```
User message → Summarize old history → Keep recent 4 messages → OpenAI → Response
```

### Very High Usage (> 80% of limit)
```
⚠️ Warning logged
User message → Aggressive trimming → OpenAI → Response
```

### Overflow (> 100% of limit)
```
Error caught → Retry with minimal context (no history) → OpenAI → Response
```

## Summarization Strategy

When history exceeds 70% of token budget:

1. **Split History**:
   - Old messages: Everything except last 4 messages
   - Recent messages: Last 4 messages (2 exchanges)

2. **Summarize Old Messages**:
   - Creates concise summary preserving key details
   - Uses GPT-4o-mini for efficiency
   - Typically reduces to < 300 tokens

3. **Build New History**:
   - `[Summary Message, Recent Message 1, Recent Message 2, Recent Message 3, Recent Message 4]`

4. **Verify & Adjust**:
   - If still too large, keeps only last 2 messages
   - Ensures context always fits

## Implementation Details

### File: `app/utils/token_manager.py`

**Key Functions:**

- `count_tokens(text, model)` - Count tokens in text
- `count_messages_tokens(messages, model)` - Count tokens in message list
- `trim_history_smart(...)` - Smart history trimming with summarization
- `summarize_conversation(history, client, model)` - Summarize old messages
- `log_token_usage(messages, model, session_id)` - Log usage statistics

### File: `app/api/chat.py`

**Updated Function:**

- `_generate_llm_response(...)` - Now includes:
  - Token-aware history trimming
  - Usage logging
  - Error recovery
  - Automatic summarization

## Configuration

**Constants in `token_manager.py`:**

```python
WARNING_THRESHOLD = 0.8    # Warn at 80% of limit
SUMMARY_THRESHOLD = 0.7    # Summarize at 70% of limit
MAX_RESPONSE_TOKENS = 600  # Reserve for response
```

**Adjust these values to fine-tune behavior.**

## Logs

### Debug Logs
```
Session abc123: 5234 tokens (4.1% of 128000 limit)
Token budget: fixed=2340, available_for_history=125060
```

### Info Logs
```
Summarizing 12 old messages
Summarized 12 messages into 287 tokens
History optimized: 8234 -> 3456 tokens
```

### Warning Logs
```
⚠️  Session abc123: High token usage! 102400/128000 tokens (80.0%)
History tokens (45000) exceed available budget (40000)
```

### Error Recovery
```
Token limit exceeded for session abc123. Attempting recovery with minimal context.
```

## Benefits

✅ **Never hit token limits** - Automatic handling prevents errors
✅ **Maintain context** - Recent messages always preserved
✅ **Cost efficient** - Summarization reduces token usage
✅ **Transparent** - Detailed logs for monitoring
✅ **User-friendly** - Seamless experience, no errors to users

## Installation

1. **Install tiktoken**:
   ```bash
   pip install -r requirements.txt
   ```

2. **No configuration needed** - Works automatically!

## Monitoring

Check logs for token usage:
```bash
# Look for patterns
grep "tokens" logs/app.log

# Find warnings
grep "⚠️" logs/app.log

# Track summarization
grep "Summarized" logs/app.log
```

## Testing

Test scenarios:
1. **Long conversation** - Keep chatting to trigger summarization
2. **Large context** - Ask complex questions with lots of RAG data
3. **Edge cases** - Try to overflow context intentionally

## Future Enhancements

Potential improvements:
- Per-user token budgets
- Dynamic adjustment of RECENT_MESSAGES_TO_KEEP
- Alternative summarization strategies
- Token usage analytics dashboard
- Cost tracking and reporting

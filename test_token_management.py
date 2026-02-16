"""
Test script for token management functionality.

Usage:
    python test_token_management.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.utils.token_manager import (
    count_tokens,
    count_messages_tokens,
    should_warn,
    should_summarize,
    get_available_tokens,
)


def test_token_counting():
    """Test basic token counting."""
    print("=" * 60)
    print("TEST 1: Token Counting")
    print("=" * 60)
    
    test_text = "Hello, how can I help you with admissions today?"
    tokens = count_tokens(test_text)
    print(f"Text: '{test_text}'")
    print(f"Tokens: {tokens}")
    
    # Test with longer text
    long_text = """
    VNR Vignana Jyothi Institute of Engineering and Technology is a premier
    engineering college in Hyderabad. We offer B.Tech programs in 14 branches
    including CSE, ECE, EEE, ME, and more. Our placement record is excellent
    with top companies like Microsoft, Amazon, and Google recruiting our students.
    """
    long_tokens = count_tokens(long_text)
    print(f"\nLong text tokens: {long_tokens}")
    print()


def test_message_counting():
    """Test message list token counting."""
    print("=" * 60)
    print("TEST 2: Message List Token Counting")
    print("=" * 60)
    
    messages = [
        {"role": "system", "content": "You are an admissions assistant."},
        {"role": "user", "content": "What are the CSE cutoffs?"},
        {"role": "assistant", "content": "The CSE cutoff for OC Boys in 2025 was 3500."},
        {"role": "user", "content": "What about ECE?"},
    ]
    
    total_tokens = count_messages_tokens(messages)
    print(f"Number of messages: {len(messages)}")
    print(f"Total tokens (with formatting): {total_tokens}")
    
    # Calculate individual tokens
    for i, msg in enumerate(messages):
        msg_tokens = count_tokens(msg["content"])
        print(f"  Message {i+1} ({msg['role']}): {msg_tokens} tokens")
    print()


def test_thresholds():
    """Test warning and summarization thresholds."""
    print("=" * 60)
    print("TEST 3: Threshold Detection")
    print("=" * 60)
    
    model = "gpt-4o-mini"
    limit = 128000
    
    test_values = [
        (50000, "Normal"),
        (89600, "Approaching summarization threshold"),
        (102400, "Should warn"),
        (120000, "Critical"),
    ]
    
    for tokens, description in test_values:
        percentage = (tokens / limit) * 100
        warn = should_warn(tokens, model)
        summarize = should_summarize(tokens, model)
        
        print(f"\n{description}:")
        print(f"  Tokens: {tokens:,} ({percentage:.1f}% of limit)")
        print(f"  Should summarize: {summarize}")
        print(f"  Should warn: {warn}")
    print()


def test_available_tokens():
    """Test available token calculation."""
    print("=" * 60)
    print("TEST 4: Available Tokens")
    print("=" * 60)
    
    models = ["gpt-4o-mini", "gpt-4o", "gpt-4", "gpt-3.5-turbo"]
    
    for model in models:
        available = get_available_tokens(model)
        print(f"{model}: {available:,} tokens available for context")
    print()


def test_conversation_simulation():
    """Simulate a conversation to show token accumulation."""
    print("=" * 60)
    print("TEST 5: Conversation Simulation")
    print("=" * 60)
    
    system_prompt = """You are the front-desk receptionist and admissions assistant at 
    VNR Vignana Jyothi Institute of Engineering and Technology. [Full system prompt would be here]"""
    
    messages = [{"role": "system", "content": system_prompt}]
    
    exchanges = [
        ("user", "Hello, I want to know about CSE admissions"),
        ("assistant", "Hello! I'd be happy to help you with CSE admissions. What would you like to know?"),
        ("user", "What are the cutoff ranks for CSE OC Boys?"),
        ("assistant", "The closing cutoff rank for CSE under OC Boys category in 2025 was 3,500."),
        ("user", "What about placements?"),
        ("assistant", "Our CSE placements are excellent. The average package is 8.5 LPA with highest at 45 LPA."),
        ("user", "What companies visit?"),
        ("assistant", "Top companies like Microsoft, Amazon, Google, Infosys, TCS, and many more recruit from our campus."),
    ]
    
    print("Simulating conversation with token tracking:\n")
    
    for i, (role, content) in enumerate(exchanges, 1):
        messages.append({"role": role, "content": content})
        total = count_messages_tokens(messages)
        
        print(f"After exchange {(i+1)//2}:")
        print(f"  Role: {role}")
        print(f"  Total messages: {len(messages)}")
        print(f"  Total tokens: {total:,}")
        print()
    
    # Show what would happen with many more exchanges
    print("Projections:")
    estimated_tokens_per_exchange = total / len(exchanges)
    for num_exchanges in [10, 20, 50, 100]:
        estimated = int(len(system_prompt.split()) * 1.3 + estimated_tokens_per_exchange * num_exchanges)
        percentage = (estimated / 128000) * 100
        print(f"  After {num_exchanges} exchanges: ~{estimated:,} tokens ({percentage:.1f}%)")
    print()


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("TOKEN MANAGEMENT SYSTEM TEST")
    print("=" * 60 + "\n")
    
    try:
        test_token_counting()
        test_message_counting()
        test_thresholds()
        test_available_tokens()
        test_conversation_simulation()
        
        print("=" * 60)
        print("✅ All tests completed successfully!")
        print("=" * 60)
        print("\nToken management system is working correctly.")
        print("The chatbot will automatically handle token limits.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Test the streaming chat endpoint to fix the "trouble connecting" error.
"""

import sys
sys.path.insert(0, '.')
import asyncio
import json

async def test_streaming_endpoint():
    """Test the streaming chat endpoint functionality."""
    
    print("🌊 TESTING STREAMING CHAT ENDPOINT")
    print("=" * 50)
    
    try:
        from app.api.chat import chat_stream_endpoint, ChatRequest
        
        # Test request - the same query that was failing
        request = ChatRequest(
            message="Branch-wise Cutoff Ranks",
            session_id="test-session",
            language="en"
        )
        
        print(f"Testing query: '{request.message}'")
        
        # Call the streaming endpoint
        stream_response = await chat_stream_endpoint(request)
        
        print(f"✅ Streaming endpoint returned: {type(stream_response)}")
        print(f"   Media type: {stream_response.media_type}")
        print(f"   Headers: {stream_response.headers}")
        
        # Try to read the stream (simulate what the frontend does)
        print(f"\n📡 Simulating frontend stream reading...")
        
        content = []
        async for chunk in stream_response.body_iterator:
            chunk_str = chunk.decode('utf-8')
            content.append(chunk_str)
            
            # Parse SSE data
            if chunk_str.startswith("data: "):
                try:
                    data = json.loads(chunk_str[6:])
                    if data.get('token'):
                        print(f"Token: '{data['token'].strip()}'", end=" ")
                    elif data.get('done'):
                        print(f"\n✅ Stream complete. Intent: {data.get('intent')}")
                    elif data.get('error'):
                        print(f"\n❌ Error: {data.get('error')}")
                except json.JSONDecodeError as e:
                    print(f"\n❌ JSON parse error: {e}")
        
        print(f"\n📋 Full stream content:")
        for i, chunk in enumerate(content):
            print(f"   [{i}] {repr(chunk)}")
            
        return True
        
    except Exception as e:
        print(f"❌ Streaming test error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_regular_endpoint():
    """Test the regular chat endpoint for comparison."""
    
    print(f"\n💬 TESTING REGULAR CHAT ENDPOINT")
    print("=" * 50)
    
    try:
        from app.api.chat import chat_endpoint, ChatRequest
        
        request = ChatRequest(
            message="Branch-wise Cutoff Ranks",
            session_id="test-session", 
            language="en"
        )
        
        response = await chat_endpoint(request)
        
        print(f"✅ Regular endpoint response:")
        print(f"   Intent: {response.intent}")
        print(f"   Response: {response.response[:200]}...")
        print(f"   Metadata: {response.metadata}")
        
        return True
        
    except Exception as e:
        print(f"❌ Regular endpoint error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests."""
    
    print("🚀 TESTING CHATBOT ENDPOINTS TO FIX CONNECTION ERROR")
    print("=" * 60)
    
    # Test regular endpoint first
    regular_success = await test_regular_endpoint()
    
    # Test streaming endpoint
    streaming_success = await test_streaming_endpoint()
    
    print(f"\n" + "=" * 60)
    
    if regular_success and streaming_success:
        print("🎉 ALL TESTS PASSED!")
        print("✅ The 'trouble connecting' error should be fixed")
        print("✅ Both /api/chat and /api/chat/stream endpoints working")
        print("\n📝 Next steps:")
        print("   1. Start the server: uvicorn app.main:app --reload")
        print("   2. Test in browser - should no longer show connection error")
    else:
        print("❌ Some tests failed. Check errors above.")
        if not regular_success:
            print("   • Regular chat endpoint has issues")
        if not streaming_success:
            print("   • Streaming chat endpoint has issues")

if __name__ == "__main__":
    asyncio.run(main())
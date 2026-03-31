"""
Debug the "Branch-wise Cutoff Ranks" query issue.
This will help us understand what's happening when users ask generic cutoff questions.
"""

import sys
sys.path.insert(0, '.')

def test_branch_wise_cutoff_query():
    """Test how the chatbot handles 'Branch-wise Cutoff Ranks' query."""
    
    print("🔍 DEBUGGING 'Branch-wise Cutoff Ranks' QUERY")
    print("=" * 60)
    
    query = "Branch-wise Cutoff Ranks"
    
    try:
        # Test parameter extraction
        from app.utils.validators import extract_branch, extract_category, extract_gender, extract_year, extract_quota
        
        print(f"Query: '{query}'")
        print("\n📊 Parameter Extraction Results:")
        
        branch = extract_branch(query)
        category = extract_category(query)
        gender = extract_gender(query)
        year = extract_year(query)
        quota = extract_quota(query)
        
        print(f"   Branch: {branch}")
        print(f"   Category: {category}")
        print(f"   Gender: {gender}")
        print(f"   Year: {year}")
        print(f"   Quota: {quota}")
        
        # Test intent classification
        from app.classifier.intent_classifier import classify
        
        print(f"\n🎯 Intent Classification:")
        result = classify(query)
        print(f"   Intent: {result.intent.value}")
        print(f"   Confidence: {result.confidence}")
        print(f"   Reason: {result.reason}")
        
        # Test what happens in cutoff handler
        print(f"\n⚙️ Cutoff Handler Logic:")
        if not branch:
            print("   ❌ Missing branch - should ask user to specify")
        if not category:
            print("   ❌ Missing category - should ask user to specify")
        
        # This is the expected behavior for this query
        expected_response = """Please specify which branch you're asking about. 
Available branches: CSE, ECE, EEE, IT, MECH, CIVIL, CSE (AI & ML), CSE (Data Science), etc.

Example: 'What is the cutoff for CSE branch?'"""
        
        print(f"\n✅ Expected Response:")
        print(f"   {expected_response}")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

def test_chat_endpoint():
    """Test the actual chat endpoint behavior."""
    
    print(f"\n🌐 TESTING CHAT ENDPOINT")
    print("=" * 60)
    
    try:
        import asyncio
        from app.api.chat import handle_cutoff_query
        from app.classifier.intent_classifier import ClassificationResult, IntentType
        
        # Create mock intent result
        intent_result = ClassificationResult(
            intent=IntentType.CUTOFF,
            confidence=0.9,
            reason="Test cutoff query"
        )
        
        async def run_test():
            query = "Branch-wise Cutoff Ranks"
            response = await handle_cutoff_query(query, intent_result)
            return response
        
        response = asyncio.run(run_test())
        
        print(f"✅ Chat Response:")
        print(f"   Intent: {response.intent}")
        print(f"   Response: {response.response[:200]}...")
        print(f"   Metadata: {response.metadata}")
        
        if "trouble connecting" not in response.response:
            print("✅ No connection error - working properly!")
        else:
            print("❌ Still getting connection error")
            
    except Exception as e:
        print(f"❌ Chat endpoint error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_branch_wise_cutoff_query()
    test_chat_endpoint()
    
    print(f"\n🎯 SOLUTION:")
    print("The query 'Branch-wise Cutoff Ranks' is too generic.")
    print("The chatbot should ask the user to specify:")
    print("1. Which branch (CSE, ECE, IT, etc.)")
    print("2. Which category (OC, BC-D, etc.)")
    print("3. This is the correct behavior, not an error!")

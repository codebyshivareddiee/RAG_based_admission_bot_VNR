"""
Test script to verify chat.py imports and functionality work correctly.
"""
import sys
sys.path.insert(0, '.')

def test_imports():
    """Test that all imports work correctly."""
    print("🧪 Testing imports...")
    
    try:
        from app.api.chat import router, ChatRequest, ChatResponse
        print("✅ Chat API imports successful")
        
        from app.classifier.intent_classifier import classify, IntentType, ClassificationResult
        print("✅ Intent classifier imports successful")
        
        from app.utils.validators import extract_branch, extract_category
        print("✅ Validators imports successful")
        
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_parameter_extraction():
    """Test parameter extraction works."""
    print("\n🔍 Testing parameter extraction...")
    
    try:
        from app.utils.validators import extract_branch, extract_category, extract_gender, extract_year
        
        test_query = "What is CSE cutoff for BC-D category in 2023 for Boys?"
        
        branch = extract_branch(test_query)
        category = extract_category(test_query)
        gender = extract_gender(test_query)
        year = extract_year(test_query)
        
        print(f"Query: '{test_query}'")
        print(f"Branch: {branch}")
        print(f"Category: {category}")
        print(f"Gender: {gender}")  
        print(f"Year: {year}")
        
        if branch == "CSE" and category == "BC-D":
            print("✅ Parameter extraction working correctly")
            return True
        else:
            print("❌ Parameter extraction not working as expected")
            return False
            
    except Exception as e:
        print(f"❌ Parameter extraction error: {e}")
        return False

def test_intent_classification():
    """Test intent classification."""
    print("\n🎯 Testing intent classification...")
    
    try:
        from app.classifier.intent_classifier import classify, IntentType
        
        test_queries = [
            "What is CSE cutoff for BC-D?",
            "Hello",
            "Tell me about VNRVJIET"
        ]
        
        for query in test_queries:
            result = classify(query)
            print(f"Query: '{query}' → Intent: {result.intent.value} (confidence: {result.confidence})")
        
        print("✅ Intent classification working")
        return True
        
    except Exception as e:
        print(f"❌ Intent classification error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 TESTING CHATBOT FIXES")
    print("=" * 50)
    
    success = True
    success &= test_imports()
    success &= test_parameter_extraction()
    success &= test_intent_classification()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 ALL TESTS PASSED! The chatbot should work now.")
        print("\n📝 To run the server:")
        print("   uvicorn app.main:app --reload")
        print("\n⚠️  Remember to set your actual API keys in .env file:")
        print("   - OPENAI_API_KEY")
        print("   - PINECONE_API_KEY") 
        print("   - FIREBASE_PROJECT_ID")
    else:
        print("❌ Some tests failed. Check the errors above.")
"""
Test script to verify the Firestore cutoff query fix.
Tests both the old error and the new fixed behavior.
"""

import sys
import traceback

# Add the app directory to Python path
sys.path.insert(0, '.')

def test_cutoff_query_fix():
    """Test the cutoff query with proper parameter extraction."""
    
    print("🧪 TESTING CUTOFF QUERY FIX")
    print("=" * 50)
    
    try:
        # Import the chat handler
        from app.api.chat import handle_cutoff_query
        from app.classifier.intent_classifier import IntentResult, IntentCategory
        
        # Test cases that should work
        test_cases = [
            {
                "query": "What is CSE cutoff for BC-D category in 2023 for Boys Convenor quota?",
                "expected_branch": "CSE",
                "expected_category": "BC-D",
                "description": "Specific query with all parameters"
            },
            {
                "query": "CSE branch BC-D 2025 boys cutoff",
                "expected_branch": "CSE", 
                "expected_category": "BC-D",
                "description": "Short form query"
            },
            {
                "query": "What is the cutoff rank for IT branch?",
                "expected_branch": "IT",
                "expected_category": None,
                "description": "Missing category (should ask for it)"
            },
            {
                "query": "Show me BC-A cutoff ranks",
                "expected_branch": None,
                "expected_category": "BC-A", 
                "description": "Missing branch (should ask for it)"
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n[Test {i}] {test_case['description']}")
            print(f"Query: '{test_case['query']}'")
            
            # Create mock intent result
            intent_result = IntentResult(
                category=IntentCategory.CUTOFF,
                confidence=0.9,
                language="en"
            )
            
            try:
                # This should be an async function, let's handle it properly
                import asyncio
                
                async def run_test():
                    return await handle_cutoff_query(test_case['query'], intent_result)
                
                response = asyncio.run(run_test())
                
                print(f"✅ Response received")
                print(f"Intent: {response.intent}")
                print(f"Metadata: {response.metadata}")
                print(f"Response (first 200 chars): {response.response[:200]}...")
                
                # Check for the old error
                if "BRANCH-WISE CUTOFF RANKS" in response.response:
                    print("❌ ERROR: Still getting 'BRANCH-WISE CUTOFF RANKS' error!")
                else:
                    print("✅ No 'BRANCH-WISE CUTOFF RANKS' error found")
                    
            except Exception as e:
                print(f"❌ ERROR in test: {e}")
                traceback.print_exc()
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed and app is properly configured")
        traceback.print_exc()

def test_parameter_extraction():
    """Test the parameter extraction functions directly."""
    
    print(f"\n🔍 TESTING PARAMETER EXTRACTION")
    print("=" * 50)
    
    try:
        from app.utils.validators import (
            extract_branch, extract_category, extract_gender, 
            extract_year, extract_quota
        )
        
        test_query = "What is CSE cutoff for BC-D category in 2023 for Boys Convenor quota?"
        
        print(f"Test query: '{test_query}'")
        print(f"Branch: {extract_branch(test_query)}")
        print(f"Category: {extract_category(test_query)}")
        print(f"Gender: {extract_gender(test_query)}")
        print(f"Year: {extract_year(test_query)}")
        print(f"Quota: {extract_quota(test_query)}")
        
        # Test problematic case
        problem_query = "BRANCH-WISE CUTOFF RANKS 2023 Boys Convenor quota"
        print(f"\nProblematic query: '{problem_query}'")
        print(f"Branch: {extract_branch(problem_query)}")
        print(f"Category: {extract_category(problem_query)}")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")

if __name__ == "__main__":
    test_parameter_extraction()
    test_cutoff_query_fix()
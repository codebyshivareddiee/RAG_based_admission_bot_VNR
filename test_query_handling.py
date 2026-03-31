"""
Quick test to verify the "Branch-wise Cutoff Ranks" query fix.
"""
import sys
sys.path.insert(0, '.')

def test_query_handling():
    """Test that the problematic query is handled properly."""
    
    print("🔍 TESTING 'Branch-wise Cutoff Ranks' QUERY HANDLING")
    print("=" * 60)
    
    try:
        from app.utils.validators import extract_branch, extract_category
        
        query = "Branch-wise Cutoff Ranks"
        
        branch = extract_branch(query)
        category = extract_category(query)
        
        print(f"Query: '{query}'")
        print(f"Extracted branch: {branch}")
        print(f"Extracted category: {category}")
        
        if not branch and not category:
            print("✅ Correctly identified as missing required parameters")
            print("✅ Should trigger 'Please specify branch' response")
            return True
        else:
            print("❌ Unexpected parameter extraction results")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_query_handling()
    
    if success:
        print("\n🎉 QUERY HANDLING TEST PASSED!")
        print("\nExpected behavior:")
        print("User: 'Branch-wise Cutoff Ranks'")
        print("Bot: 'Please specify which branch you're asking about.'")
        print("     'Available branches: CSE, ECE, EEE, IT...'")
    else:
        print("\n❌ Query handling test failed")
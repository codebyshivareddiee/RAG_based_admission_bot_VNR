"""
Debug Firestore cutoff query issue.
Let's trace exactly what's happening with the query.
"""
from app.data.init_db import get_db, COLLECTION
from google.cloud.firestore_v1.base_query import FieldFilter
from app.logic.cutoff_engine import get_cutoff
import traceback

def debug_firestore_data():
    """Check what's actually in Firestore and debug the query issue."""
    
    print("🔍 DEBUGGING FIRESTORE CUTOFF ISSUE")
    print("=" * 60)
    
    try:
        db = get_db()
        if db is None:
            print("❌ ERROR: Cannot connect to Firestore database")
            print("   Check your Firebase credentials and configuration")
            return
            
        print("✅ Connected to Firestore successfully")
        
        # Check if collection exists and has data
        collection_ref = db.collection(COLLECTION)
        docs = list(collection_ref.limit(5).stream())
        
        if not docs:
            print(f"❌ ERROR: No documents found in collection '{COLLECTION}'")
            print("   The database might be empty or collection name is wrong")
            return
            
        print(f"✅ Found {len(docs)} sample documents in collection '{COLLECTION}'")
        
        # Show sample document structure
        sample_doc = docs[0].to_dict()
        print(f"\n📄 Sample document structure:")
        for key, value in sample_doc.items():
            print(f"   {key}: {value} ({type(value).__name__})")
        
        # Check for 2023 data specifically
        print(f"\n🔍 Checking for 2023 data...")
        query_2023 = collection_ref.where(filter=FieldFilter("year", "==", 2023))
        docs_2023 = list(query_2023.stream())
        print(f"   Found {len(docs_2023)} documents for year 2023")
        
        if docs_2023:
            print("   Sample 2023 records:")
            for i, doc in enumerate(docs_2023[:3]):
                d = doc.to_dict()
                print(f"   [{i+1}] {d.get('branch')} | {d.get('category')} | {d.get('gender')} | {d.get('quota')}")
        
        # Check for Boys gender specifically
        print(f"\n🔍 Checking for 'Boys' gender data...")
        query_boys = collection_ref.where(filter=FieldFilter("gender", "==", "Boys"))
        docs_boys = list(query_boys.stream())
        print(f"   Found {len(docs_boys)} documents with gender='Boys'")
        
        # Check for Convenor quota
        print(f"\n🔍 Checking for 'Convenor' quota data...")
        query_convenor = collection_ref.where(filter=FieldFilter("quota", "==", "Convenor"))
        docs_convenor = list(query_convenor.stream())
        print(f"   Found {len(docs_convenor)} documents with quota='Convenor'")
        
        # Now try the failing query
        print(f"\n🔍 Testing failing query components...")
        print("   Testing query: branch='BRANCH-WISE CUTOFF RANKS'")
        
        query_failing = collection_ref.where(filter=FieldFilter("branch", "==", "BRANCH-WISE CUTOFF RANKS"))
        docs_failing = list(query_failing.stream())
        print(f"   Found {len(docs_failing)} documents with branch='BRANCH-WISE CUTOFF RANKS'")
        
        if len(docs_failing) == 0:
            print("   ❌ This confirms the issue - no documents with that branch name")
            print("   📝 Available branches in database:")
            
            # Get unique branch names
            all_docs = list(collection_ref.stream())
            branches = set()
            for doc in all_docs:
                d = doc.to_dict()
                if 'branch' in d:
                    branches.add(d['branch'])
            
            for branch in sorted(branches):
                print(f"      • {branch}")
                
    except Exception as e:
        print(f"❌ ERROR: {e}")
        traceback.print_exc()

def test_specific_query():
    """Test a working query to understand the format."""
    print(f"\n🧪 TESTING A WORKING QUERY")
    print("=" * 60)
    
    try:
        # Try a query that should work based on the seed data
        result = get_cutoff(
            branch="CSE",
            category="BC-D", 
            year=2025,
            gender="Any",
            quota="Convenor"
        )
        
        print("✅ Test query result:")
        print(f"   Branch: {result.branch}")
        print(f"   Category: {result.category}")
        print(f"   Found: {result.found}")
        print(f"   Message: {result.message[:200]}...")
        
    except Exception as e:
        print(f"❌ ERROR in test query: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    debug_firestore_data()
    test_specific_query()
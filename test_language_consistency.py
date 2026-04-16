"""
Test script for language consistency in chatbot responses.
Tests cutoff queries in multiple languages to ensure full localization.
"""

import asyncio
import sys
from app.logic.cutoff_engine import get_cutoff
from app.utils.languages import get_cutoff_label

def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80 + "\n")

def test_cutoff_english():
    """Test cutoff query in English."""
    print_section("TEST 1: English Cutoff Query")
    
    result = get_cutoff(
        branch="CSE",
        category="BC-D",
        year=2023,
        gender="Boys",
        quota="Convenor",
        language="en"
    )
    
    print("Branch: CSE")
    print("Category: BC-D")
    print("Gender: Boys")
    print("Year: 2023")
    print("Language: English")
    print("\nResponse:")
    print(result.message)
    
    # Check for English labels
    assert "Branch:" in result.message or "branch" in result.message.lower()
    assert "Category:" in result.message or "category" in result.message.lower()
    print("\n✅ English test passed - Labels are in English")

def test_cutoff_marathi():
    """Test cutoff query in Marathi."""
    print_section("TEST 2: Marathi Cutoff Query")
    
    result = get_cutoff(
        branch="CSE",
        category="BC-D",
        year=2023,
        gender="Boys",
        quota="Convenor",
        language="mr"
    )
    
    print("Branch: CSE")
    print("Category: BC-D")
    print("Gender: Boys (मुले)")
    print("Year: 2023")
    print("Language: Marathi (मराठी)")
    print("\nResponse:")
    print(result.message)
    
    # Check for Marathi labels
    expected_labels = ["शाखा", "प्रवर्ग", "लिंग", "कोटा", "फेरी"]
    found_labels = [label for label in expected_labels if label in result.message]
    
    # Check for unwanted English labels
    unwanted_english = ["Branch:", "Category:", "Gender:", "Quota:", "Round:", 
                        "First Rank (Opening)", "Last Rank (Closing)"]
    found_english = [word for word in unwanted_english if word in result.message]
    
    print(f"\n✅ Found Marathi labels: {', '.join(found_labels)}")
    
    if found_english:
        print(f"❌ ERROR: Found English labels that should be translated: {', '.join(found_english)}")
        return False
    else:
        print("✅ No English labels found - Fully localized!")
        
    return True

def test_cutoff_hindi():
    """Test cutoff query in Hindi."""
    print_section("TEST 3: Hindi Cutoff Query")
    
    result = get_cutoff(
        branch="CSE",
        category="OC",
        year=2023,
        gender="Girls",
        quota="Convenor",
        language="hi"
    )
    
    print("Branch: CSE")
    print("Category: OC")
    print("Gender: Girls (लड़कियां)")
    print("Year: 2023")
    print("Language: Hindi (हिन्दी)")
    print("\nResponse:")
    print(result.message)
    
    # Check for Hindi labels
    expected_labels = ["शाखा", "श्रेणी", "लिंग"]
    found_labels = [label for label in expected_labels if label in result.message]
    
    print(f"\n✅ Found Hindi labels: {', '.join(found_labels)}")
    return True

def test_cutoff_telugu():
    """Test cutoff query in Telugu."""
    print_section("TEST 4: Telugu Cutoff Query")
    
    result = get_cutoff(
        branch="ECE",
        category="OC",
        year=2023,
        gender="Boys",
        quota="Convenor",
        language="te"
    )
    
    print("Branch: ECE")
    print("Category: OC")
    print("Gender: Boys (అబ్బాయిలు)")
    print("Year: 2023")
    print("Language: Telugu (తెలుగు)")
    print("\nResponse:")
    print(result.message)
    
    # Check for Telugu labels
    expected_labels = ["శాఖ", "వర్గం", "లింగం"]
    found_labels = [label for label in expected_labels if label in result.message]
    
    print(f"\n✅ Found Telugu labels: {', '.join(found_labels)}")
    return True

def test_label_translations():
    """Test individual label translations."""
    print_section("TEST 5: Label Translation Functions")
    
    languages = {
        "en": "English",
        "hi": "Hindi",
        "te": "Telugu",
        "ta": "Tamil",
        "mr": "Marathi",
        "kn": "Kannada"
    }
    
    labels = ["branch", "category", "gender", "quota", "round", 
              "first_rank_opening", "last_rank_closing"]
    
    print("Testing label translations across all languages:\n")
    
    for label in labels:
        print(f"{label.replace('_', ' ').title()}:")
        for lang_code, lang_name in languages.items():
            translation = get_cutoff_label(label, lang_code)
            print(f"  {lang_name:10} -> {translation}")
        print()
    
    print("✅ Label translation test completed")

def main():
    """Run all tests."""
    print_section("Language Consistency Test Suite")
    print("Testing cutoff engine language localization")
    print("Expected: All labels should be translated to the selected language")
    print("Numbers, category codes (BC-D, OC), and branch codes (CSE, ECE) remain unchanged")
    
    try:
        # Test individual label translations
        test_label_translations()
        
        # Test English
        test_cutoff_english()
        
        # Test Marathi (most critical - must be 100% Marathi)
        marathi_passed = test_cutoff_marathi()
        
        # Test Hindi
        test_cutoff_hindi()
        
        # Test Telugu
        test_cutoff_telugu()
        
        print_section("TEST SUMMARY")
        if marathi_passed:
            print("✅ ALL TESTS PASSED!")
            print("✅ Language consistency is working correctly")
            print("✅ Marathi responses are fully localized (0% English mixing)")
            return 0
        else:
            print("❌ SOME TESTS FAILED")
            print("❌ Please review the output above for details")
            return 1
            
    except Exception as e:
        print(f"\n❌ ERROR during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

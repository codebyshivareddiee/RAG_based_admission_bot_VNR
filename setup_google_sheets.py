"""
Setup script for Google Sheets Contact Request System

Run this once to initialize your Google Sheet with:
- Headers
- Conditional formatting (color-coding)
- Share with admission staff
"""

import sys
from app.logic.google_sheets_service import GoogleSheetsService


def main():
    print("🚀 Setting up Google Sheets for Contact Requests...\n")
    
    try:
        # Create service
        print("📋 Connecting to Google Sheets...")
        sheets = GoogleSheetsService()
        print("✅ Connected successfully!\n")
        
        # Setup headers and formatting
        print("📝 Setting up sheet headers...")
        if sheets.setup_sheet():
            print("✅ Headers created!\n")
        else:
            print("❌ Failed to create headers\n")
            return
        
        # Add conditional formatting
        print("🎨 Adding color-coding (red=pending, yellow=contacted, green=resolved)...")
        if sheets.add_conditional_formatting():
            print("✅ Conditional formatting added!\n")
        else:
            print("⚠️  Skipped conditional formatting\n")
        
        # Optionally share with admission staff
        share_email = input("\n📧 Share with admission staff? Enter email (or press Enter to skip): ").strip()
        if share_email:
            print(f"👥 Sharing with {share_email}...")
            if sheets.share_with_email(share_email, role='writer'):
                print(f"✅ Sheet shared with {share_email}!\n")
            else:
                print("❌ Failed to share sheet\n")
        
        # Test with a sample entry
        add_test = input("\n🧪 Add a test entry? (y/n): ").strip().lower()
        if add_test == 'y':
            print("📝 Adding test entry...")
            success = sheets.add_contact_request(
                name="Test User",
                email="test@example.com",
                phone="9876543210",
                query_type="general_inquiry",
                message="This is a test entry from the setup script",
                reference_id="TEST001"
            )
            if success:
                print("✅ Test entry added!\n")
            else:
                print("❌ Failed to add test entry\n")
        
        print("=" * 60)
        print("✅ SETUP COMPLETE!")
        print("=" * 60)
        print(f"\n📊 Your Google Sheet is ready!")
        print(f"\nOpen it here:")
        print(f"https://docs.google.com/spreadsheets/d/{sheets.spreadsheet_id}/edit")
        print(f"\nAdmission staff can now:")
        print("  - View contact requests in real-time")
        print("  - Update status (Pending → Contacted → Resolved)")
        print("  - Add staff notes")
        print("  - Export to Excel/CSV")
        print("  - Access from mobile app")
        print("\n🎉 Done!\n")
        
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        print("\n📖 Please follow the setup guide:")
        print("   docs/GOOGLE_SHEETS_SETUP.md")
        sys.exit(1)
        
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        print("\n📖 Please check your .env file:")
        print("   GOOGLE_SHEETS_SPREADSHEET_ID=your-sheet-id-here")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print("\n📖 See troubleshooting guide:")
        print("   docs/GOOGLE_SHEETS_SETUP.md#troubleshooting")
        sys.exit(1)


if __name__ == "__main__":
    main()

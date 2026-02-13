# Google Sheets Setup Guide for Contact Requests

## Quick Setup (5 Minutes)

### Step 1: Create Google Sheet

1. Go to [Google Sheets](https://sheets.google.com)
2. Create a new spreadsheet
3. Name it: **"VNRVJIET Contact Requests"**
4. Rename the first tab to: **"Contact Requests"**
5. Copy the **Spreadsheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/SPREADSHEET_ID_HERE/edit
   ```

### Step 2: Enable Google Sheets API

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select existing): **"VNRVJIET Chatbot"**
3. Enable APIs:
   - Click **"Enable APIs and Services"**
   - Search for **"Google Sheets API"** → Enable
   - Search for **"Google Drive API"** → Enable

### Step 3: Create Service Account

1. In Google Cloud Console, go to **IAM & Admin** → **Service Accounts**
2. Click **"Create Service Account"**
3. Name: `vnrvjiet-chatbot-sheets`
4. Click **"Create and Continue"**
5. Grant role: **"Editor"** → **Continue**
6. Click **"Done"**

### Step 4: Generate Service Account Key

1. Click on the service account you just created
2. Go to **"Keys"** tab
3. Click **"Add Key"** → **"Create new key"**
4. Choose **JSON** format
5. Click **"Create"**
6. File will download automatically
7. **Rename** the file to: `google-service-account.json`
8. **Move** it to your project root folder:
   ```
   admission-bot/
   └── google-service-account.json  ← Place here
   ```

### Step 5: Share Sheet with Service Account

1. Open the downloaded JSON file
2. Copy the **"client_email"** value (looks like: `vnrvjiet-chatbot-sheets@project.iam.gserviceaccount.com`)
3. Go back to your Google Sheet
4. Click **"Share"** button
5. Paste the service account email
6. Give it **"Editor"** access
7. **UNCHECK** "Notify people" (it's a service account, not a person)
8. Click **"Share"**

### Step 6: Configure Environment Variables

Add to your `.env` file:

```env
# Google Sheets Configuration
GOOGLE_SHEETS_SPREADSHEET_ID=paste-your-spreadsheet-id-here
GOOGLE_SERVICE_ACCOUNT_PATH=google-service-account.json

# Optional: Share with admission staff
ADMISSION_STAFF_EMAIL=admissions@vnrvjiet.ac.in
```

### Step 7: Install Required Package

```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

Add to `requirements.txt`:
```
google-api-python-client>=2.100.0
google-auth-httplib2>=0.1.1
google-auth-oauthlib>=1.1.0
```

### Step 8: Initialize the Sheet

Run this once to set up headers and formatting:

```bash
python -c "from app.logic.google_sheets_service import GoogleSheetsService; gs = GoogleSheetsService(); gs.setup_sheet(); gs.add_conditional_formatting()"
```

### Step 9: Test It

```python
from app.logic.google_sheets_service import GoogleSheetsService

# Create service
sheets = GoogleSheetsService()

# Add a test contact request
sheets.add_contact_request(
    name="Test User",
    email="test@example.com",
    phone="9876543210",
    query_type="fraud_report",
    message="Testing the system",
    reference_id="TEST123"
)

# Check your Google Sheet - you should see the entry!
```

---

## Sheet Structure

Your Google Sheet will have these columns:

| Column | Description | Example |
|--------|-------------|---------|
| **A: Timestamp** | When request was made | 2026-02-12 14:30:45 |
| **B: Name** | User's name | Rahul Kumar |
| **C: Email** | User's email | rahul@example.com |
| **D: Phone** | User's phone (or [Hidden]) | 9876543210 |
| **E: Query Type** | Type of request | Fraud Report |
| **F: Message** | User's message | I was approached by an agent... |
| **G: Status** | Current status | Pending |
| **H: Staff Notes** | Notes from admission staff | Called and resolved |
| **I: Contacted Date** | When staff contacted user | 2026-02-13 10:00:00 |
| **J: Reference ID** | Unique ID for tracking | a3b4c5d6 |

---

## Color Coding (Automatic)

- 🔴 **Red**: Pending (needs attention)
- 🟡 **Yellow**: Contacted (in progress)
- 🟢 **Green**: Resolved (completed)

The sheet will automatically color-code rows based on the Status column!

---

## How Admission Staff Use It

### View All Requests
1. Open the Google Sheet
2. All requests appear in real-time
3. Sort by timestamp to see newest first
4. Filter by status using Google Sheets filters

### Update a Request
1. Find the row
2. Change **Status** column to:
   - `Contacted` - when you call/email the user
   - `Resolved` - when issue is resolved
3. Add **Staff Notes** to track what was done
4. **Contacted Date** updates automatically when status changes

### Export/Reporting
1. **File** → **Download** → **Excel** or **CSV**
2. Use Google Sheets built-in charts for analytics

### Share with Team
1. Click **"Share"** button
2. Add team members' emails
3. They can all view/edit simultaneously

---

## Mobile Access

**Admission staff can use the Google Sheets mobile app:**

1. Download **Google Sheets** app (iOS/Android)
2. Open the shared spreadsheet
3. View and update requests on the go
4. Get real-time notifications when new requests come in

---

## Privacy Implementation

```python
# Phone numbers are only shared for:
query_type in ['fraud_report', 'general_inquiry']

# For other types, phone is saved as "[Hidden]"
# This protects the admission section phone number
```

---

## Advanced Features (Optional)

### Email Notifications on New Row

1. In Google Sheet, go to **Extensions** → **Apps Script**
2. Paste this code:

```javascript
function onEdit(e) {
  var sheet = e.source.getActiveSheet();
  if (sheet.getName() !== "Contact Requests") return;
  
  var range = e.range;
  var row = range.getRow();
  
  // If new row added (row > 1 to skip header)
  if (row > 1 && range.getColumn() == 1) {
    var values = sheet.getRange(row, 1, 1, 10).getValues()[0];
    
    // Send email
    MailApp.sendEmail({
      to: "admissions@vnrvjiet.ac.in",
      subject: "New Contact Request - " + values[4],
      body: "Name: " + values[1] + "\n" +
            "Email: " + values[2] + "\n" +
            "Phone: " + values[3] + "\n" +
            "Type: " + values[4] + "\n" +
            "Message: " + values[5]
    });
  }
}
```

3. Save and authorize the script
4. Now you get email alerts for every new request!

### Weekly Summary Report

Create a second tab in your sheet called **"Weekly Summary"** with this formula:

```
=QUERY('Contact Requests'!A:J, 
  "SELECT COUNT(A), E WHERE A >= date '"&TEXT(TODAY()-7, "yyyy-mm-dd")&"' 
   GROUP BY E LABEL COUNT(A) 'Count', E 'Query Type'")
```

This shows you a breakdown of requests by type for the last 7 days.

---

## Troubleshooting

### "Service account file not found"
- Make sure `google-service-account.json` is in the project root
- Check the path in `.env`: `GOOGLE_SERVICE_ACCOUNT_PATH=google-service-account.json`

### "Permission denied"
- Make sure you shared the sheet with the service account email
- Check that the service account has "Editor" access

### "Spreadsheet not found"
- Double-check the Spreadsheet ID in `.env`
- Make sure you copied the ID correctly from the URL

### "API not enabled"
- Go to Google Cloud Console
- Enable both Google Sheets API and Google Drive API

---

## Security Checklist

✅ Service account JSON file in `.gitignore`  
✅ Spreadsheet ID in `.env` (not hardcoded)  
✅ Sheet shared only with authorized emails  
✅ Phone numbers hidden for non-fraud cases  
✅ No API keys committed to git  

---

## Cost

**FREE!** 
- Google Sheets API: Free for up to 500 requests per 100 seconds
- For a chatbot, this is more than enough
- Google Sheet storage: Free (up to 15GB per Google account)

---

## Support

If you encounter issues:

1. Check [Google Sheets API Documentation](https://developers.google.com/sheets/api)
2. Verify service account permissions
3. Test with a simple script first
4. Check error logs in the terminal

The system is ready to use! 🎉

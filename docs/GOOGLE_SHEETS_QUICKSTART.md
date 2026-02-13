# 🎯 Google Sheets Integration - Quick Start

**Contact Request System using Google Sheets** - The easiest solution for admission staff!

## What You Get

✅ **Familiar Interface** - Admission staff use Google Sheets (no training needed)  
✅ **Real-Time Updates** - See contact requests instantly as they arrive  
✅ **Mobile Access** - Use Google Sheets app on phone/tablet  
✅ **Color-Coded Status** - Red (Pending) → Yellow (Contacted) → Green (Resolved)  
✅ **Team Collaboration** - Multiple staff can work on same sheet simultaneously  
✅ **Export Ready** - Download as Excel/CSV for reports  
✅ **Privacy Protected** - Phone numbers hidden for non-fraud cases  

---

## 5-Minute Setup

### 1️⃣ Create Google Sheet

1. Go to https://sheets.google.com
2. Create new spreadsheet: **"VNRVJIET Contact Requests"**
3. Rename first tab to: **"Contact Requests"**
4. Copy the Spreadsheet ID from URL:
   ```
   https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit
                                          ^^^^^^^^^^^^^^^^^^^^
   ```

### 2️⃣ Enable Google Sheets API

1. Go to https://console.cloud.google.com
2. Create project: **"VNRVJIET Chatbot"**
3. Enable these APIs:
   - **Google Sheets API**
   - **Google Drive API**

### 3️⃣ Create Service Account

1. **IAM & Admin** → **Service Accounts** → **Create Service Account**
2. Name: `vnrvjiet-chatbot-sheets`
3. Role: **Editor**
4. Create **JSON key**
5. Download and rename to: `google-service-account.json`
6. Move file to project root folder

### 4️⃣ Share Sheet

1. Open the JSON file
2. Copy the `client_email` (looks like: `vnrvjiet-chatbot-sheets@....iam.gserviceaccount.com`)
3. In your Google Sheet, click **Share**
4. Paste the email, give **Editor** access
5. Uncheck "Notify people"

### 5️⃣ Configure

Add to `.env`:
```env
GOOGLE_SHEETS_SPREADSHEET_ID=paste-your-spreadsheet-id-here
GOOGLE_SERVICE_ACCOUNT_PATH=google-service-account.json
```

### 6️⃣ Install & Setup

```bash
# Install packages
pip install -r requirements.txt

# Run setup script (one-time)
python setup_google_sheets.py
```

✅ **Done!** Your Google Sheet is ready!

---

## Sheet Structure

| Timestamp | Name | Email | Phone | Query Type | Message | Status | Staff Notes | Contacted Date | Ref ID |
|-----------|------|-------|-------|------------|---------|--------|-------------|----------------|--------|
| 2026-02-12 14:30 | Rahul K. | rahul@ex.com | 9876543210 | Fraud Report | Fake agent... | Pending | - | - | a3b4c5d6 |

---

## How Staff Use It

### View Requests
- Open Google Sheet
- All requests appear in real-time
- Sort by timestamp (newest first)
- Filter by Status

### Update Status
1. Find the row
2. Change **Status** column:
   - `Contacted` - when you reach out
   - `Resolved` - when issue is closed
3. Add **Staff Notes** (what you did)
4. **Contacted Date** fills automatically

### Mobile Access
- Download **Google Sheets** app
- Open the shared sheet
- Update on the go

---

## Privacy Protection

```python
# Phone numbers are ONLY shared for:
- fraud_report (user reporting fraudsters)
- general_inquiry (user explicitly wants admission to call)

# For other query types (chatbot dissatisfaction, etc.):
- Phone shows as "[Hidden]"
- Admission staff gets email only
```

This protects the admission section phone (+91 9391982884) from being overwhelmed with calls.

---

## Advanced Features

### Email Alerts (Optional)

In Google Sheet: **Extensions** → **Apps Script**

```javascript
function onEdit(e) {
  var sheet = e.source.getActiveSheet();
  if (sheet.getName() !== "Contact Requests") return;
  
  var range = e.range;
  var row = range.getRow();
  
  if (row > 1 && range.getColumn() == 1) {
    var values = sheet.getRange(row, 1, 1, 10).getValues()[0];
    
    MailApp.sendEmail({
      to: "admissions@vnrvjiet.ac.in",
      subject: "New Contact Request - " + values[4],
      body: "Name: " + values[1] + "\nEmail: " + values[2] + "\nPhone: " + values[3]
    });
  }
}
```

Now you get email alerts for every new request!

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Service account file not found" | Check `google-service-account.json` is in project root |
| "Permission denied" | Share sheet with service account email (Editor access) |
| "Spreadsheet not found" | Double-check Spreadsheet ID in `.env` |
| "API not enabled" | Enable Google Sheets API + Drive API in Cloud Console |

---

## Next Steps

1. ✅ Complete setup (5 minutes)
2. ✅ Test with sample entry
3. ✅ Share with admission team
4. ✅ Integrate with chat endpoint (see [contact_collection_flow.md](contact_collection_flow.md))

---

## Support

- **Full Guide**: [GOOGLE_SHEETS_SETUP.md](GOOGLE_SHEETS_SETUP.md)
- **Chat Integration**: [contact_collection_flow.md](contact_collection_flow.md)
- **7 Method Comparison**: [contact_request_methods.md](contact_request_methods.md)

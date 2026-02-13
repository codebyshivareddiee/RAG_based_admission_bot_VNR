# Contact Request Collection - Chat Flow Example

## How to Integrate into Chat Endpoint

### Step 1: Detect when user wants to contact admission

```python
# In app/api/chat.py

from app.logic.contact_requests import (
    ContactRequest,
    ContactRequestService,
    send_contact_request_notification
)

# Keywords that trigger contact collection
CONTACT_TRIGGERS = [
    "talk to admission",
    "speak with someone",
    "contact admission",
    "call me",
    "not satisfied",
    "need help",
    "speak to human",
    "human support"
]

def wants_to_contact_admission(message: str) -> bool:
    """Check if user wants to contact admission department"""
    message_lower = message.lower()
    return any(trigger in message_lower for trigger in CONTACT_TRIGGERS)
```

### Step 2: Multi-turn conversation to collect info

```python
# Session-based state management
user_sessions = {}  # In production, use Redis or database

class ContactCollectionState:
    ASKING_NAME = "asking_name"
    ASKING_EMAIL = "asking_email"
    ASKING_PHONE = "asking_phone"
    ASKING_QUERY_TYPE = "asking_query_type"
    ASKING_MESSAGE = "asking_message"
    COMPLETE = "complete"

@router.post("/chat")
async def chat(request: ChatRequest):
    session_id = request.session_id
    message = request.message
    
    # Check if user is in contact collection flow
    if session_id in user_sessions:
        session_data = user_sessions[session_id]
        
        if session_data.get('collecting_contact'):
            return await handle_contact_collection(session_id, message, session_data)
    
    # Check if user wants to contact admission
    if wants_to_contact_admission(message):
        # Initialize contact collection
        user_sessions[session_id] = {
            'collecting_contact': True,
            'state': ContactCollectionState.ASKING_NAME,
            'data': {}
        }
        
        return {
            "reply": "I'd be happy to connect you with our admission team! 😊\n\nMay I have your name?",
            "session_id": session_id
        }
    
    # ... rest of normal chat logic ...
```

### Step 3: Handle contact info collection

```python
async def handle_contact_collection(session_id: str, message: str, session_data: dict):
    """Handle multi-turn contact info collection"""
    
    state = session_data['state']
    data = session_data['data']
    
    # Collect name
    if state == ContactCollectionState.ASKING_NAME:
        data['name'] = message.strip()
        session_data['state'] = ContactCollectionState.ASKING_EMAIL
        
        return {
            "reply": f"Nice to meet you, {data['name']}! 👋\n\nWhat's your email address?",
            "session_id": session_id
        }
    
    # Collect email
    elif state == ContactCollectionState.ASKING_EMAIL:
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(email_pattern, message.strip()):
            return {
                "reply": "Please enter a valid email address (e.g., student@example.com)",
                "session_id": session_id
            }
        
        data['email'] = message.strip()
        session_data['state'] = ContactCollectionState.ASKING_PHONE
        
        return {
            "reply": "Great! What's your phone number? 📞\n\n(Include country code if outside India)",
            "session_id": session_id
        }
    
    # Collect phone
    elif state == ContactCollectionState.ASKING_PHONE:
        phone = ''.join(filter(str.isdigit, message))
        
        if len(phone) < 10:
            return {
                "reply": "Please enter a valid phone number (at least 10 digits)",
                "session_id": session_id
            }
        
        data['phone'] = phone
        session_data['state'] = ContactCollectionState.ASKING_QUERY_TYPE
        
        return {
            "reply": "Thank you! What is this regarding?\n\n1️⃣ Report fraud/unauthorized agent\n2️⃣ General admission inquiry\n3️⃣ Not satisfied with chatbot response\n4️⃣ Other\n\nPlease type the number (1-4) or describe your concern:",
            "session_id": session_id
        }
    
    # Collect query type
    elif state == ContactCollectionState.ASKING_QUERY_TYPE:
        query_type_map = {
            '1': 'fraud_report',
            '2': 'general_inquiry',
            '3': 'dissatisfied',
            '4': 'other'
        }
        
        # Check if user typed number
        if message.strip() in query_type_map:
            data['query_type'] = query_type_map[message.strip()]
        # Check if message contains fraud keywords
        elif any(word in message.lower() for word in ['fraud', 'agent', 'scam', 'unauthorized']):
            data['query_type'] = 'fraud_report'
        else:
            data['query_type'] = 'other'
        
        session_data['state'] = ContactCollectionState.ASKING_MESSAGE
        
        return {
            "reply": "Got it! Would you like to add any additional details? (Or type 'skip' to proceed)",
            "session_id": session_id
        }
    
    # Collect additional message
    elif state == ContactCollectionState.ASKING_MESSAGE:
        if message.lower().strip() != 'skip':
            data['message'] = message.strip()
        
        # Save contact request
        try:
            contact_request = ContactRequest(
                name=data['name'],
                email=data['email'],
                phone=data['phone'],
                query_type=data['query_type'],
                message=data.get('message')
            )
            
            # Save to Firestore
            service = ContactRequestService()
            doc_id = service.save_request(contact_request)
            
            # Send email notification (only for fraud reports and general inquiries)
            await send_contact_request_notification(contact_request)
            
            # Clear session
            user_sessions.pop(session_id, None)
            
            # Determine response based on query type
            if data['query_type'] == 'fraud_report':
                reply = f"🚨 **Fraud Report Received**\n\nThank you for reporting this, {data['name']}. Your report has been forwarded to our admission team with high priority.\n\n**What happens next:**\n✅ Our team will investigate immediately\n✅ You'll receive a call at {data['phone']} within 24 hours\n✅ Legal action will be taken if fraud is confirmed\n\n**Reference ID:** {doc_id[:8]}\n\nRemember: VNRVJIET does NOT use agents for Category B & NRI admissions."
            else:
                reply = f"✅ **Request Submitted Successfully**\n\nThank you, {data['name']}! Our admission team has received your request.\n\n**Contact Details:**\n📧 {data['email']}\n📞 {data['phone']}\n\n**What's next:**\nOur team will reach out to you within 24 hours (Monday-Friday, 9 AM - 5 PM).\n\n**Reference ID:** {doc_id[:8]}\n\nIs there anything else I can help you with?"
            
            return {
                "reply": reply,
                "session_id": session_id,
                "contact_request_id": doc_id
            }
            
        except Exception as e:
            # Clear session on error
            user_sessions.pop(session_id, None)
            
            return {
                "reply": f"❌ I'm sorry, there was an error saving your request. Please contact us directly at:\n\n📞 +91 9391982884\n📧 postbox@vnrvjiet.ac.in\n\nError: {str(e)}",
                "session_id": session_id
            }

### Step 5: Google Sheets Integration (RECOMMENDED)

For the easiest admission staff experience, save to Google Sheets instead:

```python
from app.logic.google_sheets_service import save_contact_to_sheets

# Replace Firestore save with Google Sheets
if data['query_type'] == 'fraud_report' or data['query_type'] == 'general_inquiry':
    success, ref_id = await save_contact_to_sheets(
        name=data['name'],
        email=data['email'],
        phone=data['phone'],
        query_type=data['query_type'],
        message=data.get('message')
    )
else:
    # Hide phone for non-fraud cases
    success, ref_id = await save_contact_to_sheets(
        name=data['name'],
        email=data['email'],
        phone='[Hidden]',  # Privacy protection
        query_type=data['query_type'],
        message=data.get('message')
    )

if success:
    # Success message with reference ID
    reply = f"✅ Request saved! Reference ID: {ref_id}"
else:
    reply = "❌ Error saving request. Please try again."
```
```

### Step 4: Add cancellation option

```python
# Allow users to cancel at any time
def handle_contact_collection(session_id: str, message: str, session_data: dict):
    # Check for cancel keywords
    if message.lower().strip() in ['cancel', 'stop', 'exit', 'quit', 'nevermind']:
        user_sessions.pop(session_id, None)
        return {
            "reply": "No problem! The request has been cancelled. How else can I help you?",
            "session_id": session_id
        }
    
    # ... rest of collection logic ...
```

## Privacy & Security Features

### 1. Phone Number Privacy
- Phone number is **ONLY shared** for:
  - Fraud reports
  - Explicit contact requests
- Hidden for general chatbot dissatisfaction

### 2. Data Protection
```python
# In contact_requests.py
async def send_contact_request_notification(request: ContactRequest):
    """Only sends phone for fraud reports or explicit contact requests"""
    
    share_phone = request.query_type in ["fraud_report", "general_inquiry"]
    
    phone_display = request.phone if share_phone else "[Hidden - Not fraud report]"
```

### 3. Secure Admin Access
- Password protected (move to environment variables)
- IP whitelist (optional)
- HTTPS only in production

## Testing the Flow

```bash
# Terminal test
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to talk to someone from admission", "session_id": "test123"}'

# Expected: Bot asks for name

curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "John Doe", "session_id": "test123"}'

# Expected: Bot asks for email
# ... continue flow ...
```

## Environment Variables to Add

```env
# Email notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_FROM_EMAIL=chatbot@vnrvjiet.ac.in
SMTP_USERNAME=your-email@vnrvjiet.ac.in
SMTP_PASSWORD=your-app-password
ADMISSION_EMAIL=admissions@vnrvjiet.ac.in

# Admin dashboard
ADMIN_PASSWORD=your-secure-password-here

# Google Sheets (optional)
GOOGLE_SHEETS_SPREADSHEET_ID=your-spreadsheet-id
GOOGLE_SERVICE_ACCOUNT_PATH=path/to/service-account.json
```

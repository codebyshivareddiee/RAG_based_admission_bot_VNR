"""
Contact Request Collection & Management System

Collects user contact info when they want to speak with admission department.
Stores in Firestore and sends email notification.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, validator
from firebase_admin import firestore
from app.data.init_db import get_db

# Contact request model
class ContactRequest(BaseModel):
    """User contact request model"""
    name: str
    email: EmailStr
    phone: str
    programme: str  # "B.Tech", "M.Tech", "MCA"
    query_type: str  # "fraud_report", "general_inquiry", "dissatisfied", "other"
    message: Optional[str] = None
    timestamp: Optional[datetime] = None
    status: str = "pending"  # pending, contacted, resolved
    
    @validator('phone')
    def validate_phone(cls, v):
        # Remove spaces and dashes
        cleaned = ''.join(filter(str.isdigit, v))
        if len(cleaned) < 10:
            raise ValueError('Phone number must be at least 10 digits')
        return cleaned
    
    @validator('programme')
    def validate_programme(cls, v):
        allowed = ["b.tech", "m.tech", "mca", "btech", "mtech"]
        v_lower = v.lower().replace(" ", "").replace(".", "")
        if v_lower in ["btech", "btech"]:  
            return "B.Tech"
        elif v_lower in ["mtech", "mtech"]:
            return "M.Tech"
        elif v_lower == "mca":
            return "MCA"
        else:
            return "B.Tech"  # Default
    
    @validator('query_type')
    def validate_query_type(cls, v):
        allowed = ["fraud_report", "general_inquiry", "dissatisfied", "other"]
        if v.lower() not in allowed:
            return "other"
        return v.lower()


class ContactRequestService:
    """Service for managing contact requests"""
    
    COLLECTION = "contact_requests"
    
    def __init__(self):
        self.db = get_db()
    
    def save_request(self, request: ContactRequest) -> str:
        """
        Save contact request to Firestore
        
        Returns:
            Document ID
        """
        if not request.timestamp:
            request.timestamp = datetime.now()
        
        # Convert to dict
        data = request.dict()
        data['timestamp'] = firestore.SERVER_TIMESTAMP
        
        # Save to Firestore
        doc_ref = self.db.collection(self.COLLECTION).add(data)
        doc_id = doc_ref[1].id
        
        return doc_id
    
    def get_all_requests(
        self, 
        status: Optional[str] = None,
        limit: int = 100
    ) -> list[dict]:
        """
        Get all contact requests
        
        Args:
            status: Filter by status (pending, contacted, resolved)
            limit: Max number of records to return
            
        Returns:
            List of contact requests
        """
        query = self.db.collection(self.COLLECTION).order_by(
            'timestamp', 
            direction=firestore.Query.DESCENDING
        ).limit(limit)
        
        if status:
            query = query.where('status', '==', status)
        
        docs = query.stream()
        
        return [
            {
                'id': doc.id,
                **doc.to_dict()
            }
            for doc in docs
        ]
    
    def update_status(self, doc_id: str, status: str, notes: Optional[str] = None):
        """
        Update contact request status
        
        Args:
            doc_id: Document ID
            status: New status (pending, contacted, resolved)
            notes: Optional notes from staff
        """
        update_data = {
            'status': status,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        if notes:
            update_data['staff_notes'] = notes
        
        self.db.collection(self.COLLECTION).document(doc_id).update(update_data)
    
    def export_to_csv(self, status: Optional[str] = None) -> str:
        """
        Export contact requests to CSV
        
        Args:
            status: Filter by status
            
        Returns:
            CSV string
        """
        import csv
        from io import StringIO
        
        requests = self.get_all_requests(status=status, limit=1000)
        
        output = StringIO()
        if requests:
            fieldnames = ['id', 'timestamp', 'name', 'email', 'phone', 
                         'query_type', 'message', 'status', 'staff_notes']
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            
            for req in requests:
                # Convert timestamp to string
                if 'timestamp' in req and req['timestamp']:
                    req['timestamp'] = req['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                writer.writerow({k: req.get(k, '') for k in fieldnames})
        
        return output.getvalue()


# Email notification service
async def send_contact_request_notification(request: ContactRequest):
    """
    Send email notification to admission department
    
    Only sends phone number for fraud reports or explicit contact requests.
    """
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from app.config import get_settings
        
        settings = get_settings()
        
        # Determine if phone should be shared
        share_phone = request.query_type in ["fraud_report", "general_inquiry"]
        
        # Email content
        subject = f"New Contact Request - {request.query_type.replace('_', ' ').title()}"
        
        body = f"""
New Contact Request from VNRVJIET Chatbot

Name: {request.name}
Email: {request.email}
{"Phone: " + request.phone if share_phone else "Phone: [Hidden - Not fraud report]"}
Type: {request.query_type.replace('_', ' ').title()}
Message: {request.message or 'N/A'}
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Status: Pending

---
Please respond to the user at: {request.email}
{"or call: " + request.phone if share_phone else ""}

VNRVJIET Admissions Chatbot
        """
        
        # Create email
        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_FROM_EMAIL if hasattr(settings, 'SMTP_FROM_EMAIL') else 'chatbot@vnrvjiet.ac.in'
        msg['To'] = 'admissions@vnrvjiet.ac.in'  # Configure in settings
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email (configure SMTP settings in .env)
        if hasattr(settings, 'SMTP_HOST'):
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            if hasattr(settings, 'SMTP_USE_TLS') and settings.SMTP_USE_TLS:
                server.starttls()
            if hasattr(settings, 'SMTP_USERNAME'):
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            return True
        else:
            print("⚠️  SMTP not configured. Email notification skipped.")
            return False
            
    except Exception as e:
        print(f"❌ Failed to send email notification: {e}")
        return False


# Google Sheets integration (optional)
async def save_to_google_sheets(request: ContactRequest):
    """
    Save contact request to Google Sheet
    
    Requires: google-auth, google-auth-oauthlib, google-auth-httplib2, google-api-python-client
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        # Load credentials (configure path in .env)
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        SERVICE_ACCOUNT_FILE = 'path/to/service-account.json'
        
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        
        service = build('sheets', 'v4', credentials=credentials)
        
        # Sheet ID and range (configure in .env)
        SPREADSHEET_ID = 'your-spreadsheet-id'
        RANGE_NAME = 'Contact Requests!A:H'
        
        # Prepare row data
        share_phone = request.query_type in ["fraud_report", "general_inquiry"]
        values = [[
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            request.name,
            request.email,
            request.phone if share_phone else '[Hidden]',
            request.query_type,
            request.message or '',
            'Pending',
            ''  # Notes column
        ]]
        
        body = {'values': values}
        
        result = service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME,
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to save to Google Sheets: {e}")
        return False


# Usage example in chat endpoint
"""
from app.logic.contact_requests import (
    ContactRequest, 
    ContactRequestService,
    send_contact_request_notification
)

# In your chat endpoint when user wants to contact admission
if user_wants_contact:
    # Collect user info
    contact_request = ContactRequest(
        name=user_name,
        email=user_email,
        phone=user_phone,
        query_type="general_inquiry",  # or "fraud_report", "dissatisfied"
        message=user_message
    )
    
    # Save to Firestore
    service = ContactRequestService()
    doc_id = service.save_request(contact_request)
    
    # Send notification (only if fraud report or explicit contact request)
    await send_contact_request_notification(contact_request)
    
    # Return confirmation to user
    return {
        "reply": "Thank you! Your contact request has been recorded. Our admission team will reach out to you within 24 hours.",
        "contact_request_id": doc_id
    }
"""

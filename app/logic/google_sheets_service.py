"""
Google Sheets Integration for Contact Requests

Saves contact requests directly to Google Sheets - perfect for admission staff
who prefer familiar spreadsheet interface.
"""

from datetime import datetime
from typing import Optional
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import get_settings

settings = get_settings()


class GoogleSheetsService:
    """Service for managing contact requests in Google Sheets"""
    
    # Google Sheets API scope
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    def __init__(self):
        """Initialize Google Sheets service"""
        # Get credentials path from environment or default location
        creds_path = os.getenv(
            'GOOGLE_SERVICE_ACCOUNT_PATH',
            'google-service-account.json'
        )
        
        if not Path(creds_path).exists():
            raise FileNotFoundError(
                f"Google service account file not found: {creds_path}\n"
                "Please download it from Google Cloud Console and save it in the project root."
            )
        
        # Load credentials
        self.credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=self.SCOPES
        )
        
        # Build service
        self.service = build('sheets', 'v4', credentials=self.credentials)
        
        # Get spreadsheet ID from environment
        self.spreadsheet_id = os.getenv('GOOGLE_SHEETS_SPREADSHEET_ID')
        if not self.spreadsheet_id:
            raise ValueError(
                "GOOGLE_SHEETS_SPREADSHEET_ID not set in environment variables.\n"
                "Please create a Google Sheet and add its ID to .env"
            )
    
    def setup_sheet(self):
        """
        Create the initial sheet structure with headers
        
        Run this once to set up the sheet headers
        """
        headers = [
            'Timestamp',
            'Name',
            'Email',
            'Phone',
            'Programme',
            'Query Type',
            'Message',
            'Status',
            'Staff Notes',
            'Contacted Date',
            'Reference ID'
        ]
        
        try:
            # Clear existing data
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range='ContactRequests!A1:K1000'
            ).execute()
            
            # Write headers
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range='ContactRequests!A1:K1',
                valueInputOption='RAW',
                body={'values': [headers]}
            ).execute()
            
            # Format headers (bold, background color)
            requests = [
                {
                    'repeatCell': {
                        'range': {
                            'sheetId': 0,
                            'startRowIndex': 0,
                            'endRowIndex': 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'textFormat': {'bold': True},
                                'backgroundColor': {
                                    'red': 0.2,
                                    'green': 0.6,
                                    'blue': 0.9
                                }
                            }
                        },
                        'fields': 'userEnteredFormat(textFormat,backgroundColor)'
                    }
                },
                {
                    'autoResizeDimensions': {
                        'dimensions': {
                            'sheetId': 0,
                            'dimension': 'COLUMNS',
                            'startIndex': 0,
                            'endIndex': 11
                        }
                    }
                }
            ]
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={'requests': requests}
            ).execute()
            
            print("✅ Sheet setup complete with headers!")
            return True
            
        except HttpError as e:
            print(f"❌ Error setting up sheet: {e}")
            return False
    
    def add_contact_request(
        self,
        name: str,
        email: str,
        phone: str,
        programme: str,
        query_type: str,
        message: Optional[str] = None,
        reference_id: Optional[str] = None
    ) -> bool:
        """
        Add a new contact request to the sheet
        
        Args:
            name: User's name
            email: User's email
            phone: User's phone (or "[Hidden]" for non-fraud cases)
            programme: Programme type (B.Tech, M.Tech, MCA)
            query_type: Type of query
            message: Optional message from user
            reference_id: Optional reference ID
            
        Returns:
            True if successful, False otherwise
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        row = [
            timestamp,
            name,
            email,
            phone,
            programme,
            query_type.replace('_', ' ').title(),
            message or '',
            'Pending',
            '',  # Staff notes (empty initially)
            '',  # Contacted date (empty initially)
            reference_id or ''
        ]
        
        try:
            # Append to sheet
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range='ContactRequests!A:K',
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            # Get the row number that was added
            updated_range = result.get('updates', {}).get('updatedRange', '')
            
            print(f"✅ Contact request added to Google Sheets: {updated_range}")
            return True
            
        except HttpError as e:
            print(f"❌ Error adding to Google Sheets: {e}")
            return False
    
    def get_all_requests(self, status: Optional[str] = None) -> list[dict]:
        """
        Get all contact requests from the sheet
        
        Args:
            status: Filter by status (Pending, Contacted, Resolved)
            
        Returns:
            List of contact request dictionaries
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='ContactRequests!A2:K1000'  # Skip header row
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                return []
            
            # Convert to list of dicts
            requests = []
            headers = ['timestamp', 'name', 'email', 'phone', 'query_type', 
                      'message', 'status', 'staff_notes', 'contacted_date', 'reference_id']
            
            for idx, row in enumerate(values, start=2):
                # Pad row with empty strings if needed
                row = row + [''] * (10 - len(row))
                
                request = dict(zip(headers, row))
                request['row_number'] = idx  # Track row number for updates
                
                # Filter by status if provided
                if status and request['status'].lower() != status.lower():
                    continue
                
                requests.append(request)
            
            return requests
            
        except HttpError as e:
            print(f"❌ Error reading from Google Sheets: {e}")
            return []
    
    def update_status(
        self,
        row_number: int,
        status: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Update the status of a contact request
        
        Args:
            row_number: Row number in the sheet (starts at 2, after headers)
            status: New status (Pending, Contacted, Resolved)
            notes: Optional staff notes
            
        Returns:
            True if successful
        """
        try:
            updates = []
            
            # Update status (column G)
            updates.append({
                'range': f'ContactRequests!G{row_number}',
                'values': [[status]]
            })
            
            # Update staff notes if provided (column H)
            if notes:
                updates.append({
                    'range': f'ContactRequests!H{row_number}',
                    'values': [[notes]]
                })
            
            # Update contacted date if status is "Contacted" (column I)
            if status.lower() == 'contacted':
                contacted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                updates.append({
                    'range': f'ContactRequests!I{row_number}',
                    'values': [[contacted_date]]
                })
            
            # Batch update
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={'valueInputOption': 'USER_ENTERED', 'data': updates}
            ).execute()
            
            print(f"✅ Updated row {row_number} to status: {status}")
            return True
            
        except HttpError as e:
            print(f"❌ Error updating Google Sheets: {e}")
            return False
    
    def add_conditional_formatting(self):
        """
        Add color-coding to the sheet based on status
        
        - Pending: Red background
        - Contacted: Yellow background
        - Resolved: Green background
        """
        try:
            requests = [
                # Pending = Red
                {
                    'addConditionalFormatRule': {
                        'rule': {
                            'ranges': [{
                                'sheetId': 0,
                                'startRowIndex': 1,
                                'endRowIndex': 1000,
                                'startColumnIndex': 6,
                                'endColumnIndex': 7
                            }],
                            'booleanRule': {
                                'condition': {
                                    'type': 'TEXT_EQ',
                                    'values': [{'userEnteredValue': 'Pending'}]
                                },
                                'format': {
                                    'backgroundColor': {
                                        'red': 1.0,
                                        'green': 0.9,
                                        'blue': 0.9
                                    }
                                }
                            }
                        },
                        'index': 0
                    }
                },
                # Contacted = Yellow
                {
                    'addConditionalFormatRule': {
                        'rule': {
                            'ranges': [{
                                'sheetId': 0,
                                'startRowIndex': 1,
                                'endRowIndex': 1000,
                                'startColumnIndex': 6,
                                'endColumnIndex': 7
                            }],
                            'booleanRule': {
                                'condition': {
                                    'type': 'TEXT_EQ',
                                    'values': [{'userEnteredValue': 'Contacted'}]
                                },
                                'format': {
                                    'backgroundColor': {
                                        'red': 1.0,
                                        'green': 1.0,
                                        'blue': 0.8
                                    }
                                }
                            }
                        },
                        'index': 1
                    }
                },
                # Resolved = Green
                {
                    'addConditionalFormatRule': {
                        'rule': {
                            'ranges': [{
                                'sheetId': 0,
                                'startRowIndex': 1,
                                'endRowIndex': 1000,
                                'startColumnIndex': 6,
                                'endColumnIndex': 7
                            }],
                            'booleanRule': {
                                'condition': {
                                    'type': 'TEXT_EQ',
                                    'values': [{'userEnteredValue': 'Resolved'}]
                                },
                                'format': {
                                    'backgroundColor': {
                                        'red': 0.85,
                                        'green': 1.0,
                                        'blue': 0.85
                                    }
                                }
                            }
                        },
                        'index': 2
                    }
                }
            ]
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={'requests': requests}
            ).execute()
            
            print("✅ Conditional formatting added!")
            return True
            
        except HttpError as e:
            print(f"❌ Error adding conditional formatting: {e}")
            return False
    
    def share_with_email(self, email: str, role: str = 'writer'):
        """
        Share the spreadsheet with an email address
        
        Args:
            email: Email address to share with
            role: 'reader', 'writer', or 'owner'
        """
        try:
            # Build Drive API service
            drive_service = build('drive', 'v3', credentials=self.credentials)
            
            permission = {
                'type': 'user',
                'role': role,
                'emailAddress': email
            }
            
            drive_service.permissions().create(
                fileId=self.spreadsheet_id,
                body=permission,
                sendNotificationEmail=True
            ).execute()
            
            print(f"✅ Sheet shared with {email} as {role}")
            return True
            
        except HttpError as e:
            print(f"❌ Error sharing sheet: {e}")
            return False


# Usage in chat.py
async def save_contact_to_sheets(
    name: str,
    email: str,
    phone: str,
    programme: str,
    query_type: str,
    message: Optional[str] = None
):
    """
    Save contact request to Google Sheets
    
    Phone number privacy:
    - Only share phone for fraud_report and general_inquiry
    - Hide phone for other query types
    """
    try:
        sheets = GoogleSheetsService()
        
        # Privacy control: hide phone for non-fraud cases
        share_phone = query_type in ['fraud_report', 'general_inquiry']
        phone_display = phone if share_phone else '[Hidden]'
        
        # Generate reference ID
        import uuid
        reference_id = str(uuid.uuid4())[:8]
        
        # Add to sheet
        success = sheets.add_contact_request(
            name=name,
            email=email,
            phone=phone_display,
            programme=programme,
            query_type=query_type,
            message=message,
            reference_id=reference_id
        )
        
        if success:
            # Also save to Firestore as backup (optional)
            from app.logic.contact_requests import ContactRequest, ContactRequestService
            
            contact_request = ContactRequest(
                name=name,
                email=email,
                phone=phone,
                programme=programme,
                query_type=query_type,
                message=message
            )
            
            service = ContactRequestService()
            service.save_request(contact_request)
        
        return success, reference_id
        
    except Exception as e:
        print(f"❌ Error saving to Google Sheets: {e}")
        return False, None

"""
Admin Dashboard for Contact Requests

Simple HTML interface for admission staff to view and manage contact requests.
Access at: /admin/contacts
"""

import logging
import traceback

logger = logging.getLogger(__name__)
logger.info("admin.py: starting imports...")

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
from io import BytesIO

try:
    from app.logic.contact_requests import ContactRequestService
    logger.info("admin.py: ContactRequestService imported OK")
except Exception as e:
    logger.error(f"admin.py: FAILED to import ContactRequestService: {e}")
    traceback.print_exc()
    raise

router = APIRouter(prefix="/admin", tags=["admin"])

# Simple password protection (replace with proper auth in production)
ADMIN_PASSWORD = "vnrvjiet_admin_2025"  # Move to environment variables

def verify_admin(password: str):
    """Simple password verification"""
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@router.get("/contacts", response_class=HTMLResponse)
async def view_contacts(
    password: str,
    status: Optional[str] = None
):
    """
    Admin dashboard to view contact requests
    
    Usage: /admin/contacts?password=vnrvjiet_admin_2025
    """
    verify_admin(password)
    
    service = ContactRequestService()
    requests = service.get_all_requests(status=status)
    
    # Generate HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Contact Requests - VNRVJIET Admin</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: #f5f5f5;
                padding: 20px;
            }}
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #1a73e8;
                margin-bottom: 10px;
                font-size: 28px;
            }}
            .subtitle {{
                color: #666;
                margin-bottom: 25px;
                font-size: 14px;
            }}
            .stats {{
                display: flex;
                gap: 15px;
                margin-bottom: 25px;
                flex-wrap: wrap;
            }}
            .stat-card {{
                background: #f8f9fa;
                padding: 15px 20px;
                border-radius: 6px;
                border-left: 4px solid #1a73e8;
            }}
            .stat-card.pending {{ border-left-color: #ea4335; }}
            .stat-card.contacted {{ border-left-color: #fbbc04; }}
            .stat-card.resolved {{ border-left-color: #34a853; }}
            .stat-number {{
                font-size: 24px;
                font-weight: bold;
                color: #202124;
            }}
            .stat-label {{
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
            }}
            .filters {{
                margin-bottom: 20px;
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
            }}
            .btn {{
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                text-decoration: none;
                display: inline-block;
                transition: background 0.2s;
            }}
            .btn-primary {{
                background: #1a73e8;
                color: white;
            }}
            .btn-primary:hover {{
                background: #1557b0;
            }}
            .btn-secondary {{
                background: #f8f9fa;
                color: #202124;
                border: 1px solid #dadce0;
            }}
            .btn-secondary:hover {{
                background: #e8eaed;
            }}
            .btn-export {{
                background: #34a853;
                color: white;
            }}
            .btn-export:hover {{
                background: #2d8e47;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}
            th {{
                background: #f8f9fa;
                padding: 12px;
                text-align: left;
                font-weight: 600;
                font-size: 13px;
                color: #202124;
                border-bottom: 2px solid #dadce0;
            }}
            td {{
                padding: 12px;
                border-bottom: 1px solid #e8eaed;
                font-size: 14px;
                color: #3c4043;
            }}
            tr:hover {{
                background: #f8f9fa;
            }}
            .status {{
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 500;
                display: inline-block;
            }}
            .status-pending {{
                background: #fce8e6;
                color: #c5221f;
            }}
            .status-contacted {{
                background: #fef7e0;
                color: #e37400;
            }}
            .status-resolved {{
                background: #e6f4ea;
                color: #1e8e3e;
            }}
            .query-type {{
                padding: 4px 8px;
                background: #e8f0fe;
                color: #1a73e8;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
            .fraud-report {{
                background: #fce8e6;
                color: #c5221f;
            }}
            .no-data {{
                text-align: center;
                padding: 60px 20px;
                color: #666;
            }}
            .empty-icon {{
                font-size: 64px;
                margin-bottom: 20px;
            }}
            @media (max-width: 768px) {{
                .container {{
                    padding: 15px;
                }}
                table {{
                    font-size: 12px;
                }}
                th, td {{
                    padding: 8px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📞 Contact Requests Dashboard</h1>
            <p class="subtitle">VNRVJIET Admissions - Manage student contact requests</p>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number">{len(requests)}</div>
                    <div class="stat-label">Total Requests</div>
                </div>
                <div class="stat-card pending">
                    <div class="stat-number">{len([r for r in requests if r.get('status') == 'pending'])}</div>
                    <div class="stat-label">Pending</div>
                </div>
                <div class="stat-card contacted">
                    <div class="stat-number">{len([r for r in requests if r.get('status') == 'contacted'])}</div>
                    <div class="stat-label">Contacted</div>
                </div>
                <div class="stat-card resolved">
                    <div class="stat-number">{len([r for r in requests if r.get('status') == 'resolved'])}</div>
                    <div class="stat-label">Resolved</div>
                </div>
            </div>
            
            <div class="filters">
                <a href="/admin/contacts?password={password}" class="btn btn-secondary">All</a>
                <a href="/admin/contacts?password={password}&status=pending" class="btn btn-secondary">Pending</a>
                <a href="/admin/contacts?password={password}&status=contacted" class="btn btn-secondary">Contacted</a>
                <a href="/admin/contacts?password={password}&status=resolved" class="btn btn-secondary">Resolved</a>
                <a href="/admin/contacts/export?password={password}" class="btn btn-export">📥 Export CSV</a>
            </div>
            
            {"".join([f'''
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Phone</th>
                        <th>Type</th>
                        <th>Message</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join([f"""
                    <tr>
                        <td>{r.get('timestamp', 'N/A')}</td>
                        <td><strong>{r.get('name', 'N/A')}</strong></td>
                        <td><a href="mailto:{r.get('email', '')}">{r.get('email', 'N/A')}</a></td>
                        <td><a href="tel:{r.get('phone', '')}">{r.get('phone', 'N/A')}</a></td>
                        <td><span class="query-type {('fraud-report' if r.get('query_type') == 'fraud_report' else '')}">{r.get('query_type', 'other').replace('_', ' ').title()}</span></td>
                        <td>{r.get('message', 'N/A')[:100]}{"..." if len(r.get('message', '')) > 100 else ""}</td>
                        <td><span class="status status-{r.get('status', 'pending')}">{r.get('status', 'pending').title()}</span></td>
                    </tr>
                    """ for r in requests])}
                </tbody>
            </table>
            ''' if requests else '''
            <div class="no-data">
                <div class="empty-icon">📭</div>
                <h3>No contact requests found</h3>
                <p>Contact requests will appear here when students request to speak with admission department.</p>
            </div>
            '''])}
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


@router.get("/contacts/export")
async def export_contacts(
    password: str,
    status: Optional[str] = None
):
    """
    Export contact requests to CSV
    
    Usage: /admin/contacts/export?password=vnrvjiet_admin_2025
    """
    verify_admin(password)
    
    service = ContactRequestService()
    csv_data = service.export_to_csv(status=status)
    
    # Create response
    output = BytesIO(csv_data.encode('utf-8'))
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=contact_requests_{status or 'all'}.csv"
        }
    )

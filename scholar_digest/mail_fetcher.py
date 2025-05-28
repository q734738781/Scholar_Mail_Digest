import os.path
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import email
from datetime import datetime

# If modifying these scopes, delete token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def get_credentials():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds

def fetch_emails(service, query):
    """Fetch emails based on the query."""
    try:
        response = service.users().messages().list(userId="me", q=query).execute()
        messages = []
        if "messages" in response:
            messages.extend(response["messages"])

        while "nextPageToken" in response:
            page_token = response["nextPageToken"]
            response = (
                service.users()
                .messages()
                .list(userId="me", q=query, pageToken=page_token)
                .execute()
            )
            if "messages" in response:
                messages.extend(response["messages"])
        return messages
    except HttpError as error:
        print(f"An error occurred: {error}")
        return []

def get_email_details(service, message_id):
    """Get the full email data for a given message ID."""
    try:
        message = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="raw")
            .execute()
        )
        
        raw_email = base64.urlsafe_b64decode(message["raw"].encode("ASCII"))
        email_message = email.message_from_bytes(raw_email)
        
        email_data = {
            "id": message_id,
            "snippet": message["snippet"], # Gmail's own snippet
            "subject": "",
            "date": "",
            "body_html": ""
        }

        for header in email_message._headers:
            if header[0].lower() == "subject":
                email_data["subject"] = header[1]
            if header[0].lower() == "date":
                # Parse date and convert to Unix timestamp
                dt_object = datetime.strptime(header[1].split(" (")[0].strip(), '%a, %d %b %Y %H:%M:%S %z')
                email_data["date"] = dt_object.timestamp()


        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if content_type == "text/html" and "attachment" not in content_disposition:
                    try:
                        email_data["body_html"] = part.get_payload(decode=True).decode()
                        break 
                    except UnicodeDecodeError:
                         email_data["body_html"] = part.get_payload(decode=True).decode(errors='ignore')
                         break
        else:
            content_type = email_message.get_content_type()
            if content_type == "text/html":
                try:
                    email_data["body_html"] = email_message.get_payload(decode=True).decode()
                except UnicodeDecodeError:
                    email_data["body_html"] = email_message.get_payload(decode=True).decode(errors='ignore')
        
        return email_data
    except HttpError as error:
        print(f"An error occurred while fetching email {message_id}: {error}")
        return None

def get_scholar_alert_emails(last_run_timestamp=None):
    """
    Fetches Google Scholar alert emails since the last run.
    If last_run_timestamp is None, fetches all scholar alerts (for the first run).
    """
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)
    
    query = "from:scholaralerts-noreply@google.com"
    if last_run_timestamp:
        # Gmail API uses seconds for timestamp in query
        query += f" after:{int(last_run_timestamp)}"
        
    print(f"Fetching emails with query: {query}")
    message_ids = fetch_emails(service, query)
    
    emails_data = []
    if not message_ids:
        print("No new messages found.")
    else:
        print(f"Found {len(message_ids)} new messages.")
        for msg_info in message_ids:
            email_content = get_email_details(service, msg_info["id"])
            if email_content:
                emails_data.append(email_content)
    
    # Sort emails by date (timestamp) to ensure the last_run_timestamp is the latest
    emails_data.sort(key=lambda x: x['date'], reverse=True)
    return emails_data

if __name__ == "__main__":
    # Example usage:
    # For the very first run, or to fetch all scholar alerts:
    # scholar_emails = get_scholar_alert_emails()
    
    # For subsequent runs, provide the timestamp of the last fetched email
    # This would typically be read from last_run.txt
    # For testing, let's use a timestamp from a few days ago
    # test_last_run = datetime(2024, 1, 1).timestamp() 
    # scholar_emails = get_scholar_alert_emails(last_run_timestamp=test_last_run)
    
    scholar_emails = get_scholar_alert_emails() # Fetches all initially
    
    if scholar_emails:
        print(f"Successfully fetched {len(scholar_emails)} scholar emails.")
        for i, email_data in enumerate(scholar_emails[:2]): # Print details of first 2 emails
            print(f"--- Email {i+1} ---")
            print(f"ID: {email_data['id']}")
            print(f"Subject: {email_data['subject']}")
            print(f"Date: {datetime.fromtimestamp(email_data['date'])}")
            # print(f"Body HTML (first 200 chars): {email_data['body_html'][:200]}")
        
        # To simulate a subsequent run, you would save the date of the newest email.
        # latest_email_date = scholar_emails[0]['date'] # Assuming sorted by date descending
        # print(f"Timestamp of the latest email: {latest_email_date}")
    else:
        print("No scholar emails fetched.")

    # Note: credentials.json needs to be in the same directory or provide the correct path.
    # You will be prompted to authorize access the first time you run this. 
from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()

class SMSService:
    def __init__(self):
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.phone_number = os.getenv('TWILIO_PHONE_NUMBER')
        self.server_url = os.getenv('SERVER_URL', 'http://localhost:8501')
        
        if self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            self.client = None
    
    def send_tracking_request(self, recipient_phone, tracking_id, custom_message=None):
        if not self.client:
            return {
                'success': False,
                'error': 'Twilio credentials not configured',
                'debug_url': f"{self.server_url}/?tracking_id={tracking_id}"
            }
        
        try:
            tracking_url = f"{self.server_url}/?tracking_id={tracking_id}"
            message_body = f"{custom_message or 'Please share your location for safety reasons.'}\n\nShare your location here: {tracking_url}\n\nThis link will expire in 24 hours."
            
            message = self.client.messages.create(
                body=message_body,
                from_=self.phone_number,
                to=recipient_phone
            )
            
            return {
                'success': True,
                'message_sid': message.sid,
                'tracking_url': tracking_url
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

sms_service = SMSService()
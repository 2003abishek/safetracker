from twilio.rest import Client
import streamlit as st

class SMSService:
    def __init__(self):
        # Get credentials from Streamlit secrets
        self.account_sid = st.secrets.get('TWILIO_ACCOUNT_SID')
        self.auth_token = st.secrets.get('TWILIO_AUTH_TOKEN')
        self.phone_number = st.secrets.get('TWILIO_PHONE_NUMBER')
        
        # Get server URL from secrets
        self.server_url = st.secrets.get('SERVER_URL', 'https://your-app-name.streamlit.app')
        
        self.is_configured = bool(self.account_sid and self.auth_token and self.phone_number)
        
        if self.is_configured:
            try:
                self.client = Client(self.account_sid, self.auth_token)
            except Exception as e:
                print(f"Twilio initialization failed: {e}")
                self.client = None
                self.is_configured = False
        else:
            self.client = None
    
    def send_tracking_request(self, recipient_phone, tracking_id, custom_message=None):
        tracking_url = f"{self.server_url}/?tracking_id={tracking_id}"
        
        if not self.is_configured:
            return {
                'success': False,
                'sms_sent': False,
                'error': 'Twilio not configured',
                'tracking_url': tracking_url,
                'message': 'Manual sharing required - copy and send the URL'
            }
        
        try:
            message_body = f"{custom_message or 'Please share your location for safety reasons.'}\n\nShare your location here: {tracking_url}\n\nThis link will expire in 24 hours."
            
            message = self.client.messages.create(
                body=message_body,
                from_=self.phone_number,
                to=recipient_phone
            )
            
            return {
                'success': True,
                'sms_sent': True,
                'message_sid': message.sid,
                'tracking_url': tracking_url
            }
            
        except Exception as e:
            return {
                'success': False,
                'sms_sent': False,
                'error': str(e),
                'tracking_url': tracking_url
            }

sms_service = SMSService()

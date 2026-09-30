"""External messaging is called by explicit UI actions or opted-in schedules."""
import os
import re
import json


def send_whatsapp(contact, message):
    if not re.fullmatch(r'\+[1-9]\d{9,14}', contact or ''):
        return 'failed', 'Add a valid caregiver number in your profile.'
    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    sender = os.getenv('TWILIO_WHATSAPP_FROM')
    if not all((sid, token, sender)):
        return 'not_configured', 'WhatsApp is not configured on this server.'
    try:
        import requests
        payload = {'From': sender, 'To': f'whatsapp:{contact}'}
        content_sid = os.getenv('TWILIO_WHATSAPP_CONTENT_SID')
        if content_sid:
            service_sid = os.getenv('TWILIO_MESSAGING_SERVICE_SID')
            if not service_sid:
                return 'not_configured', 'Configure the Twilio Messaging Service for template messages.'
            payload.update(ContentSid=content_sid, MessagingServiceSid=service_sid,
                           ContentVariables=json.dumps({'1':' '.join(message.split())[:1000]}))
        else:
            payload['Body'] = message[:1500]
        response = requests.post(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
                                 auth=(sid, token), timeout=15,
                                 data=payload)
        if not response.ok:
            return 'failed', f'Twilio rejected the request (HTTP {response.status_code}). Check recipient and sender setup.'
        return 'queued', response.json()['sid']
    except Exception:
        # A timeout can occur after acceptance. Do not blindly retry and send duplicates.
        return 'unknown', 'Provider acceptance could not be confirmed; check Twilio before retrying.'

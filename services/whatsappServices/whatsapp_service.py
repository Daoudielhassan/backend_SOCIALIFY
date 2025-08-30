"""
WhatsApp Business API Service
Handles WhatsApp message sending, receiving, and webhook management
"""

import aiohttp
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from config.settings import get_settings
from utils.logger import logger
from utils.errors import WhatsAppError, APIError

logger = logger
settings = get_settings()

class WhatsAppService:
    """WhatsApp Business API service for sending and receiving messages"""
    
    def __init__(self):
        # Get fresh settings each time
        self.settings = get_settings()
        
    @property
    def api_url(self):
        return self.settings.WHATSAPP_API_URL
        
    @property
    def access_token(self):
        return self.settings.WHATSAPP_ACCESS_TOKEN
        
    @property
    def phone_number_id(self):
        return self.settings.WHATSAPP_PHONE_NUMBER_ID
        
    @property
    def webhook_verify_token(self):
        return self.settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
    
    def _check_configuration(self):
        """Check if WhatsApp configuration is complete"""
        if not all([self.api_url, self.access_token, self.phone_number_id]):
            logger.warning("⚠️ WhatsApp configuration incomplete - service may not work properly")
    
    async def send_message(self, to: str, message: str, message_type: str = "text") -> Dict[str, Any]:
        """
        Send a WhatsApp message
        
        Args:
            to: Recipient phone number (with country code, no +)
            message: Message content
            message_type: Type of message (text, template, etc.)
            
        Returns:
            Response from WhatsApp API
        """
        try:
            if not settings.ENABLE_WHATSAPP:
                raise WhatsAppError("WhatsApp service is disabled")
            
            url = f"{self.api_url}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": message_type,
                message_type: {
                    "body": message
                }
            }
            
            logger.info(f"📱 Sending WhatsApp message to {to[:5]}***")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    response_data = await response.json()
                    
                    logger.info(f"📱 WhatsApp API Response - Status: {response.status}")
                    logger.info(f"📱 WhatsApp API Response - Data: {response_data}")
                    
                    if response.status == 200:
                        logger.info(f"✅ WhatsApp message sent successfully")
                        return {
                            "success": True,
                            "message_id": response_data.get("messages", [{}])[0].get("id"),
                            "status": "sent",
                            "data": response_data
                        }
                    else:
                        logger.error(f"❌ WhatsApp API error: Status {response.status}, Data: {response_data}")
                        raise WhatsAppError(f"{response.status}: {response_data}")
                        
        except Exception as e:
            logger.error(f"❌ WhatsApp send error: {str(e)}")
            raise WhatsAppError(f"Failed to send WhatsApp message: {str(e)}")
    
    async def send_template_message(self, to: str, template_name: str, language_code: str = "en", 
                                  parameters: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Send a WhatsApp template message
        
        Args:
            to: Recipient phone number
            template_name: Name of the approved template
            language_code: Language code (e.g., 'en', 'fr', 'es')
            parameters: Template parameters
            
        Returns:
            Response from WhatsApp API
        """
        try:
            if not settings.ENABLE_WHATSAPP:
                raise WhatsAppError("WhatsApp service is disabled")
            
            url = f"{self.api_url}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            template_payload = {
                "name": template_name,
                "language": {"code": language_code}
            }
            
            if parameters:
                template_payload["components"] = [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": param} for param in parameters]
                }]
            
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": template_payload
            }
            
            logger.info(f"📱 Sending WhatsApp template '{template_name}' to {to[:5]}***")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        logger.info(f"✅ WhatsApp template sent successfully")
                        return {
                            "success": True,
                            "message_id": response_data.get("messages", [{}])[0].get("id"),
                            "template": template_name,
                            "data": response_data
                        }
                    else:
                        logger.error(f"❌ WhatsApp template API error: {response_data}")
                        raise WhatsAppError(f"Failed to send template: {response_data}")
                        
        except Exception as e:
            logger.error(f"❌ WhatsApp template send error: {str(e)}")
            raise WhatsAppError(f"Failed to send WhatsApp template: {str(e)}")
    
    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """
        Verify WhatsApp webhook
        
        Args:
            mode: Verification mode
            token: Verification token
            challenge: Challenge string
            
        Returns:
            Challenge string if verification succeeds, None otherwise
        """
        try:
            logger.info(f"🔍 Webhook verification - Mode: {mode}, Expected token: {self.webhook_verify_token[:10]}***, Received token: {token[:10]}***")
            
            if mode == "subscribe" and token == self.webhook_verify_token:
                logger.info("✅ WhatsApp webhook verified successfully")
                return challenge
            else:
                logger.warning(f"❌ WhatsApp webhook verification failed - Mode: {mode}, Token match: {token == self.webhook_verify_token}")
                return None
                
        except Exception as e:
            logger.error(f"❌ WhatsApp webhook verification error: {str(e)}")
            return None
    
    async def process_webhook_message(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming WhatsApp webhook message
        
        Args:
            webhook_data: Webhook payload from WhatsApp
            
        Returns:
            Processed message data
        """
        try:
            if not webhook_data.get("entry"):
                return {"success": False, "error": "No entry data"}
            
            messages = []
            for entry in webhook_data["entry"]:
                if "changes" in entry:
                    for change in entry["changes"]:
                        if change.get("field") == "messages":
                            value = change.get("value", {})
                            
                            # Process incoming messages
                            if "messages" in value:
                                for message in value["messages"]:
                                    processed_message = {
                                        "id": message.get("id"),
                                        "from": message.get("from"),
                                        "timestamp": datetime.fromtimestamp(int(message.get("timestamp", 0))),
                                        "type": message.get("type"),
                                        "text": message.get("text", {}).get("body", "") if message.get("type") == "text" else "",
                                        "source": "whatsapp",
                                        "raw_data": message
                                    }
                                    messages.append(processed_message)
                                    logger.info(f"📱 Received WhatsApp message from {message.get('from', 'unknown')}")
            
            return {
                "success": True,
                "messages": messages,
                "count": len(messages)
            }
            
        except Exception as e:
            logger.error(f"❌ WhatsApp webhook processing error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def get_message_status(self, message_id: str) -> Dict[str, Any]:
        """
        Get WhatsApp message delivery status
        
        Args:
            message_id: WhatsApp message ID
            
        Returns:
            Message status information
        """
        try:
            if not settings.ENABLE_WHATSAPP:
                raise WhatsAppError("WhatsApp service is disabled")
            
            # Note: WhatsApp doesn't provide a direct API to check message status
            # Status updates come through webhooks
            logger.info(f"📱 Message status check requested for: {message_id}")
            
            return {
                "success": True,
                "message_id": message_id,
                "note": "Status updates are received via webhooks"
            }
            
        except Exception as e:
            logger.error(f"❌ WhatsApp status check error: {str(e)}")
            raise WhatsAppError(f"Failed to check message status: {str(e)}")
    
    def get_service_info(self) -> Dict[str, Any]:
        """Get WhatsApp service configuration info"""
        return {
            "service": "WhatsApp Business API",
            "enabled": settings.ENABLE_WHATSAPP,
            "api_url": self.api_url if self.api_url else "Not configured",
            "phone_number_id": self.phone_number_id[:10] + "***" if self.phone_number_id else "Not configured",
            "webhook_configured": bool(self.webhook_verify_token),
            "status": "ready" if all([self.api_url, self.access_token, self.phone_number_id]) else "configuration_incomplete"
        }

# Global service instance
whatsapp_service = WhatsAppService()

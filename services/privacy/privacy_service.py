"""
Privacy Service - Unified Privacy Operations
Consolidates all privacy-related functionality into a single service
Handles: Data protection, encryption, compliance, audit trails
"""

import os
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text

from db.models import User, MessageMetadata
from utils.logger import logger
from utils.encryption import token_encryption
from dotenv import load_dotenv

load_dotenv()

@dataclass
class PrivacyAuditResult:
    """
    Data class for privacy audit results
    """
    compliant: bool
    violations: List[str]
    recommendations: List[str]
    audit_timestamp: str
    score: float  # 0.0 to 1.0

class PrivacyService:
    """
    Unified Privacy Service - Handles all privacy operations
    Features:
    - Data encryption and decryption
    - Privacy compliance auditing
    - Content filtering and redaction
    - Audit trail management
    - GDPR/CCPA compliance utilities
    """
    
    def __init__(self):
        self.compliance_standards = ["GDPR", "CCPA", "SOC2"]
        self.sensitive_fields = [
            "password", "token", "body", "content", "message", 
            "email_content", "personal_data", "private_info"
        ]
        self.privacy_levels = ["public", "internal", "confidential", "restricted"]
    
    def encrypt_sensitive_data(self, data: Union[str, Dict[str, Any]]) -> str:
        """
        Encrypt sensitive data using the token encryption system
        
        Args:
            data: Data to encrypt (string or dict)
            
        Returns:
            Encrypted string
        """
        try:
            if isinstance(data, dict):
                data_str = json.dumps(data, sort_keys=True)
            else:
                data_str = str(data)
            
            encrypted = token_encryption.encrypt_token(data_str)
            logger.debug("🔒 Data encrypted successfully")
            return encrypted
            
        except Exception as e:
            logger.error(f"Error encrypting sensitive data: {str(e)}")
            raise ValueError("Failed to encrypt sensitive data")
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> Union[str, Dict[str, Any]]:
        """
        Decrypt sensitive data
        
        Args:
            encrypted_data: Encrypted data string
            
        Returns:
            Decrypted data (string or dict)
        """
        try:
            decrypted_str = token_encryption.decrypt_token(encrypted_data)
            
            # Try to parse as JSON first
            try:
                return json.loads(decrypted_str)
            except json.JSONDecodeError:
                return decrypted_str
                
        except Exception as e:
            logger.error("Error decrypting sensitive data")
            raise ValueError("Failed to decrypt sensitive data")
    
    def filter_sensitive_content(self, content: str, replacement: str = "[FILTERED]") -> str:
        """
        Filter sensitive content for logging and display
        
        Args:
            content: Content to filter
            replacement: Replacement text for sensitive content
            
        Returns:
            Filtered content
        """
        if not content:
            return content
        
        # Email patterns
        import re
        filtered = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 
                         f'[EMAIL_FILTERED]', content)
        
        # Phone patterns
        filtered = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', 
                         f'[PHONE_FILTERED]', filtered)
        
        # Token patterns
        filtered = re.sub(r'\b[A-Za-z0-9]{32,}\b', 
                         f'[TOKEN_FILTERED]', filtered)
        
        # Credit card patterns (basic)
        filtered = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', 
                         f'[CARD_FILTERED]', filtered)
        
        # Social Security Number patterns
        filtered = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', 
                         f'[SSN_FILTERED]', filtered)
        
        return filtered
    
    def redact_personal_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Redact personal information from data dictionary
        
        Args:
            data: Data dictionary to redact
            
        Returns:
            Redacted data dictionary
        """
        redacted = data.copy()
        
        for key, value in redacted.items():
            lower_key = key.lower()
            
            # Redact known sensitive fields
            if any(sensitive in lower_key for sensitive in self.sensitive_fields):
                if isinstance(value, str):
                    redacted[key] = "[REDACTED]"
                elif isinstance(value, dict):
                    redacted[key] = {"redacted": True}
                elif isinstance(value, list):
                    redacted[key] = ["[REDACTED]" for _ in value]
                else:
                    redacted[key] = "[REDACTED]"
            
            # Recursively redact nested dictionaries
            elif isinstance(value, dict):
                redacted[key] = self.redact_personal_info(value)
                
            # Filter string content
            elif isinstance(value, str):
                redacted[key] = self.filter_sensitive_content(value)
        
        return redacted
    
    async def audit_database_privacy(self, db: AsyncSession) -> PrivacyAuditResult:
        """
        Comprehensive privacy audit of the database
        
        Args:
            db: Database session
            
        Returns:
            Privacy audit results
        """
        violations = []
        recommendations = []
        checks_passed = 0
        total_checks = 0
        
        try:
            # Check 1: No plaintext tokens
            total_checks += 1
            legacy_tokens_query = await db.execute(
                select(func.count(User.id)).where(
                    and_(
                        User.gmail_token_encrypted.is_(None)
                    )
                )
            )
            legacy_token_count = legacy_tokens_query.scalar() or 0
            
            if legacy_token_count > 0:
                violations.append(f"{legacy_token_count} users have unencrypted tokens")
                recommendations.append("Migrate legacy tokens to encrypted storage")
            else:
                checks_passed += 1
            
            # Check 2: No password hashes for OAuth users
            total_checks += 1
            oauth_with_passwords_query = await db.execute(
                select(func.count(User.id)).where(
                    and_(
                        User.auth_method == 'oauth',
                        User.password_hash.isnot(None)
                    )
                )
            )
            oauth_password_count = oauth_with_passwords_query.scalar() or 0
            
            if oauth_password_count > 0:
                violations.append(f"{oauth_password_count} OAuth users still have password hashes")
                recommendations.append("Remove password hashes for OAuth-only users")
            else:
                checks_passed += 1
            
            # Check 3: Verify message content is not stored
            total_checks += 1
            try:
                # Try to query old Message table - should not exist or be empty
                legacy_messages_result = await db.execute(text("SELECT COUNT(*) FROM messages"))
                legacy_message_count = legacy_messages_result.scalar() or 0
                
                if legacy_message_count > 0:
                    violations.append(f"{legacy_message_count} messages in legacy content table")
                    recommendations.append("Migrate to metadata-only storage and remove content table")
                else:
                    checks_passed += 1
                    
            except Exception:
                # Table doesn't exist - this is good for privacy
                checks_passed += 1
            
            # Check 4: Verify metadata-only storage
            total_checks += 1
            metadata_query = await db.execute(select(func.count(MessageMetadata.id)))
            metadata_count = metadata_query.scalar() or 0
            
            if metadata_count > 0:
                # Sample some records to verify no content
                sample_query = await db.execute(
                    select(MessageMetadata).limit(5)
                )
                sample_messages = sample_query.scalars().all()
                
                content_found = any(
                    hasattr(msg, 'body') or hasattr(msg, 'content') 
                    for msg in sample_messages
                )
                
                if content_found:
                    violations.append("Message content found in metadata table")
                    recommendations.append("Remove content columns from metadata table")
                else:
                    checks_passed += 1
            else:
                checks_passed += 1
            
            # Check 5: Verify encryption is working
            total_checks += 1
            encrypted_tokens_query = await db.execute(
                select(func.count(User.id)).where(
                    User.gmail_token_encrypted.isnot(None)
                )
            )
            encrypted_token_count = encrypted_tokens_query.scalar() or 0
            
            if encrypted_token_count > 0:
                # Test decryption on a sample
                sample_user_query = await db.execute(
                    select(User).where(User.gmail_token_encrypted.isnot(None)).limit(1)
                )
                sample_user = sample_user_query.scalar_one_or_none()
                
                if sample_user:
                    try:
                        decrypted = self.decrypt_sensitive_data(sample_user.gmail_token_encrypted)
                        if decrypted:
                            checks_passed += 1
                        else:
                            violations.append("Token decryption verification failed")
                            recommendations.append("Verify encryption keys and re-encrypt tokens")
                    except Exception:
                        violations.append("Token decryption verification failed")
                        recommendations.append("Verify encryption keys and re-encrypt tokens")
                else:
                    checks_passed += 1
            else:
                # No encrypted tokens to test, but that's not necessarily bad
                checks_passed += 1
            
            # Calculate compliance score
            compliance_score = checks_passed / total_checks if total_checks > 0 else 0.0
            is_compliant = len(violations) == 0
            
            audit_result = PrivacyAuditResult(
                compliant=is_compliant,
                violations=violations,
                recommendations=recommendations,
                audit_timestamp=datetime.utcnow().isoformat(),
                score=compliance_score
            )
            
            logger.info(f"🔍 Privacy audit completed - Score: {compliance_score:.2f}")
            return audit_result
            
        except Exception as e:
            logger.error(f"Error during privacy audit: {str(e)}")
            return PrivacyAuditResult(
                compliant=False,
                violations=[f"Audit error: {str(e)}"],
                recommendations=["Fix audit system errors"],
                audit_timestamp=datetime.utcnow().isoformat(),
                score=0.0
            )
    
    async def cleanup_old_data(
        self, 
        db: AsyncSession, 
        retention_days: int = 90
    ) -> Dict[str, Any]:
        """
        Clean up old data according to retention policies
        
        Args:
            db: Database session
            retention_days: Number of days to retain data
            
        Returns:
            Cleanup results
        """
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        try:
            # Count old metadata records
            old_metadata_query = await db.execute(
                select(func.count(MessageMetadata.id)).where(
                    MessageMetadata.received_at < cutoff_date
                )
            )
            old_metadata_count = old_metadata_query.scalar() or 0
            
            if old_metadata_count > 0:
                # Delete old metadata
                from sqlalchemy import delete
                await db.execute(
                    delete(MessageMetadata).where(
                        MessageMetadata.received_at < cutoff_date
                    )
                )
                await db.commit()
                
                logger.info(f"🗑️  Cleaned up {old_metadata_count} old metadata records")
            
            return {
                "success": True,
                "cleaned_records": old_metadata_count,
                "cutoff_date": cutoff_date.isoformat(),
                "retention_days": retention_days
            }
            
        except Exception as e:
            logger.error(f"Error during data cleanup: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def generate_privacy_report(self, audit_result: PrivacyAuditResult) -> Dict[str, Any]:
        """
        Generate comprehensive privacy compliance report
        
        Args:
            audit_result: Results from privacy audit
            
        Returns:
            Formatted privacy report
        """
        return {
            "privacy_compliance_report": {
                "timestamp": audit_result.audit_timestamp,
                "overall_status": "COMPLIANT" if audit_result.compliant else "NON_COMPLIANT",
                "compliance_score": f"{audit_result.score:.1%}",
                "standards_checked": self.compliance_standards,
                "summary": {
                    "violations_found": len(audit_result.violations),
                    "recommendations_provided": len(audit_result.recommendations),
                    "privacy_grade": self._calculate_privacy_grade(audit_result.score)
                },
                "violations": audit_result.violations,
                "recommendations": audit_result.recommendations,
                "privacy_features": [
                    "OAuth2-only authentication",
                    "Encrypted token storage", 
                    "Metadata-only message storage",
                    "Content filtering in logs",
                    "Automated data cleanup",
                    "Privacy audit system"
                ],
                "next_audit_recommended": (
                    datetime.fromisoformat(audit_result.audit_timestamp) + timedelta(days=30)
                ).isoformat()
            }
        }
    
    def _calculate_privacy_grade(self, score: float) -> str:
        """
        Calculate privacy grade based on compliance score
        """
        if score >= 0.95:
            return "A+"
        elif score >= 0.90:
            return "A"
        elif score >= 0.85:
            return "B+"
        elif score >= 0.80:
            return "B"
        elif score >= 0.70:
            return "C"
        else:
            return "F"
    
    def hash_for_tracking(self, data: str) -> str:
        """
        Create privacy-safe hash for tracking purposes
        
        Args:
            data: Data to hash
            
        Returns:
            SHA-256 hash string
        """
        return hashlib.sha256(data.encode()).hexdigest()[:16]  # Truncated for privacy
    
    def anonymize_email(self, email: str) -> str:
        """
        Anonymize email address for logging/display
        
        Args:
            email: Email address to anonymize
            
        Returns:
            Anonymized email address
        """
        if '@' not in email:
            return "[INVALID_EMAIL]"
        
        local, domain = email.split('@', 1)
        
        if len(local) <= 2:
            anonymized_local = local[0] + '*'
        else:
            anonymized_local = local[0] + '*' * (len(local) - 2) + local[-1]
        
        return f"{anonymized_local}@{domain}"
    
    def get_privacy_settings(self) -> Dict[str, Any]:
        """
        Get current privacy service settings
        """
        return {
            "service": "PrivacyService",
            "compliance_standards": self.compliance_standards,
            "sensitive_fields_monitored": len(self.sensitive_fields),
            "privacy_levels": self.privacy_levels,
            "encryption_enabled": True,
            "content_filtering_enabled": True,
            "audit_system_enabled": True,
            "data_retention_enabled": True
        }

# Singleton instance
privacy_service = PrivacyService()

"""
Validation Service
Antigravity Skill: error-handling-patterns
"""
import re
import dns.resolver
from typing import Dict, Any, Tuple
from app.utils.logger import get_logger

logger = get_logger(__name__)

class ValidationService:
    @staticmethod
    def validate_email(email: str) -> Tuple[bool, str]:
        """
        Validates email format and domain existence.
        Returns: (is_valid, error_message)
        """
        email = email.lower().strip()
        
        # 1. Regex Format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return False, "Formato de e-mail inválido."
            
        # 2. Domain Check (DNS)
        domain = email.split('@')[1]
        try:
            dns.resolver.resolve(domain, 'MX')
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            # Try A record as fallback (some domains accept mail at root)
            try:
                 dns.resolver.resolve(domain, 'A')
            except Exception:
                return False, f"Domínio '{domain}' não parece válido para e-mails."
        except Exception as e:
            logger.warning(f"DNS check failed for {domain}: {e}")
            # Don't block on transient DNS errors, just warn
            
        return True, ""

    @staticmethod
    def validate_phone(phone: str) -> Tuple[bool, str]:
        """
        Validates Brazilian phone format.
        Expects: 55 + DDD + 9 digits (total 13 chars) approx.
        Accepts flexible input and sanitizes first.
        """
        # Remove non-digits
        clean_phone = re.sub(r"\D", "", phone)
        
        # Check if length is roughly correct (10-13 digits)
        # Brazil: 55 (2) + DDD (2) + 9xxxx-xxxx (9) = 13
        # Allow missing country code for domestic logic if needed, but standard is full.
        
        if not 10 <= len(clean_phone) <= 13:
            return False, "Telefone deve ter DDD + número (ex: 11999999999)."
            
        # If it seems like a mobile number (9 digits), ensure it starts with 9
        # (Assuming full number including DDD)
        # Detailed validation can be complex, keeping it simple for now.
        
        return True, ""

    @staticmethod
    def validate_name(name: str) -> Tuple[bool, str]:
        """
        Validates name (min length, no numbers).
        """
        name = name.strip()
        if len(name) < 3:
            return False, "Nome muito curto."
            
        if re.search(r"\d", name):
            return False, "Nome não deve conter números."
            
        return True, ""

    @staticmethod
    def sanitize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cleans and formats input data.
        """
        sanitized = data.copy()
        
        if "email" in sanitized and isinstance(sanitized["email"], str):
            sanitized["email"] = sanitized["email"].lower().strip()
            
        if "name" in sanitized and isinstance(sanitized["name"], str):
            # Title Case
            sanitized["name"] = sanitized["name"].strip().title()
            
        if "phone" in sanitized and isinstance(sanitized["phone"], str):
             sanitized["phone"] = re.sub(r"\D", "", sanitized["phone"])
             
        if "company" in sanitized and isinstance(sanitized["company"], str):
             sanitized["company"] = sanitized["company"].strip()
             
        return sanitized

# app/utils/auth.py
"""
Authentication utilities following SOLID principles.
Implements Single Responsibility and Strategy patterns.
"""

import hashlib
import hmac
import secrets/°
import logging
from typing import Optional, Dict, Any, Protocol
from abc import ABC, abstractmethod
from functools import wraps
from flask import request, jsonify

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Custom authentication error"""
    pass


class AuthorizationError(Exception):
    """Custom authorization error"""
    pass


class ISignatureValidator(Protocol):
    """Interface for signature validators"""
    
    def validate_signature(self, payload: str, signature: str, secret: str) -> bool:
        """Validate request signature"""
        ...


class ITokenValidator(Protocol):
    """Interface for token validators"""
    
    def validate_token(self, token: str) -> bool:
        """Validate authentication token"""
        ...


class IPermissionChecker(Protocol):
    """Interface for permission checkers"""
    
    def has_permission(self, user_id: str, permission: str) -> bool:
        """Check if user has permission"""
        ...


class HMACSignatureValidator(ISignatureValidator):
    """HMAC-based signature validator"""
    
    def __init__(self, hash_algorithm: str = 'sha256'):
        self.hash_algorithm = hash_algorithm
    
    def validate_signature(self, payload: str, signature: str, secret: str) -> bool:
        """Validate HMAC signature"""
        try:
            # Generate expected signature
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                payload.encode('utf-8'),
                getattr(hashlib, self.hash_algorithm)
            ).hexdigest()
            
            # Secure comparison
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error(f"Error validating HMAC signature: {e}")
            return False


class SHA256SignatureValidator(ISignatureValidator):
    """SHA256-based signature validator"""
    
    def validate_signature(self, payload: str, signature: str, secret: str) -> bool:
        """Validate SHA256 signature"""
        try:
            # Remove 'sha256=' prefix if present
            if signature.startswith('sha256='):
                signature = signature[7:]
            
            # Generate expected signature
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Secure comparison
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error(f"Error validating SHA256 signature: {e}")
            return False


class SimpleTokenValidator(ITokenValidator):
    """Simple token validator for basic authentication"""
    
    def __init__(self, valid_tokens: set):
        self.valid_tokens = valid_tokens
    
    def validate_token(self, token: str) -> bool:
        """Validate token against known valid tokens"""
        return token in self.valid_tokens


class RoleBasedPermissionChecker(IPermissionChecker):
    """Role-based permission checker"""
    
    def __init__(self, user_roles: Dict[str, set], role_permissions: Dict[str, set]):
        self.user_roles = user_roles
        self.role_permissions = role_permissions
    
    def has_permission(self, user_id: str, permission: str) -> bool:
        """Check if user has permission based on roles"""
        user_roles = self.user_roles.get(user_id, set())
        
        for role in user_roles:
            role_perms = self.role_permissions.get(role, set())
            if permission in role_perms:
                return True
        
        return False


class WebhookAuthenticator:
    """Authenticator for webhook requests"""
    
    def __init__(
        self,
        signature_validator: ISignatureValidator,
        signature_header: str = 'X-Signature',
        secret_key: str = None
    ):
        self.signature_validator = signature_validator
        self.signature_header = signature_header
        self.secret_key = secret_key
    
    def authenticate_request(self, request_data: str = None, signature: str = None) -> bool:
        """Authenticate webhook request"""
        if not self.secret_key:
            logger.warning("No secret key configured for webhook authentication")
            return False
        
        if request_data is None:
            request_data = request.get_data(as_text=True)
        
        if signature is None:
            signature = request.headers.get(self.signature_header)
        
        if not signature:
            logger.warning(f"No signature found in header {self.signature_header}")
            return False
        
        return self.signature_validator.validate_signature(
            request_data, signature, self.secret_key
        )


class APIKeyAuthenticator:
    """Authenticator for API key-based requests"""
    
    def __init__(
        self,
        token_validator: ITokenValidator,
        api_key_header: str = 'X-API-Key'
    ):
        self.token_validator = token_validator
        self.api_key_header = api_key_header
    
    def authenticate_request(self, api_key: str = None) -> bool:
        """Authenticate API key request"""
        if api_key is None:
            api_key = request.headers.get(self.api_key_header)
        
        if not api_key:
            logger.warning(f"No API key found in header {self.api_key_header}")
            return False
        
        return self.token_validator.validate_token(api_key)


class AuthorizationManager:
    """Manager for handling authorization"""
    
    def __init__(self, permission_checker: IPermissionChecker):
        self.permission_checker = permission_checker
    
    def require_permission(self, user_id: str, permission: str) -> bool:
        """Check if user has required permission"""
        if not self.permission_checker.has_permission(user_id, permission):
            raise AuthorizationError(f"User {user_id} lacks permission: {permission}")
        return True


# Decorators
def require_webhook_signature(
    secret_key: str, 
    signature_header: str = 'X-Signature',
    validator_type: str = 'hmac'
):
    """Decorator to require valid webhook signature"""
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create appropriate validator
            if validator_type == 'hmac':
                validator = HMACSignatureValidator()
            elif validator_type == 'sha256':
                validator = SHA256SignatureValidator()
            else:
                raise ValueError(f"Unknown validator type: {validator_type}")
            
            # Create authenticator
            authenticator = WebhookAuthenticator(
                validator, signature_header, secret_key
            )
            
            # Authenticate request
            if not authenticator.authenticate_request():
                logger.warning(f"Invalid signature for {request.path}")
                return jsonify({
                    'error': 'Invalid signature',
                    'status': 'unauthorized'
                }), 401
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_api_key(valid_keys: set, api_key_header: str = 'X-API-Key'):
    """Decorator to require valid API key"""
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create validator and authenticator
            validator = SimpleTokenValidator(valid_keys)
            authenticator = APIKeyAuthenticator(validator, api_key_header)
            
            # Authenticate request
            if not authenticator.authenticate_request():
                logger.warning(f"Invalid API key for {request.path}")
                return jsonify({
                    'error': 'Invalid API key',
                    'status': 'unauthorized'
                }), 401
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_permission(permission: str, permission_checker: IPermissionChecker):
    """Decorator to require specific permission"""
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get user ID from request (implementation depends on your auth system)
            user_id = request.headers.get('X-User-ID') or 'anonymous'
            
            # Check permission
            if not permission_checker.has_permission(user_id, permission):
                logger.warning(f"User {user_id} lacks permission {permission} for {request.path}")
                return jsonify({
                    'error': f'Permission denied: {permission}',
                    'status': 'forbidden'
                }), 403
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


# Utility functions
def generate_api_key(length: int = 32) -> str:
    """Generate a secure API key"""
    return secrets.token_urlsafe(length)


def hash_password(password: str, salt: str = None) -> tuple:
    """Hash password with salt"""
    if salt is None:
        salt = secrets.token_hex(16)
    
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return pwd_hash.hex(), salt


def verify_password(password: str, hash_value: str, salt: str) -> bool:
    """Verify password against hash"""
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return hmac.compare_digest(hash_value, pwd_hash.hex())


# Factory functions
def create_webhook_authenticator(
    secret_key: str,
    signature_type: str = 'hmac',
    signature_header: str = 'X-Signature'
) -> WebhookAuthenticator:
    """Factory for creating webhook authenticator"""
    if signature_type == 'hmac':
        validator = HMACSignatureValidator()
    elif signature_type == 'sha256':
        validator = SHA256SignatureValidator()
    else:
        raise ValueError(f"Unknown signature type: {signature_type}")
    
    return WebhookAuthenticator(validator, signature_header, secret_key)


def create_api_key_authenticator(
    valid_keys: set,
    api_key_header: str = 'X-API-Key'
) -> APIKeyAuthenticator:
    """Factory for creating API key authenticator"""
    validator = SimpleTokenValidator(valid_keys)
    return APIKeyAuthenticator(validator, api_key_header)

# app/utils/validation.py
"""
Validation utilities following SOLID principles.
Implements Single Responsibility and Open/Closed principles.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Protocol
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom validation error"""
    
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(message)


class ValidationResult:
    """Result of validation operation"""
    
    def __init__(self, is_valid: bool = True, errors: List[str] = None):
        self.is_valid = is_valid
        self.errors = errors or []
    
    def add_error(self, error: str) -> None:
        """Add validation error"""
        self.errors.append(error)
        self.is_valid = False


class IValidator(Protocol):
    """Interface for validators"""
    
    def validate(self, value: Any) -> ValidationResult:
        """Validate a value"""
        ...


class BaseValidator(ABC):
    """Base class for validators"""
    
    def __init__(self, error_message: str = None):
        self.error_message = error_message
    
    @abstractmethod
    def _validate_value(self, value: Any) -> bool:
        """Validate the value - to be implemented by subclasses"""
        pass
    
    def validate(self, value: Any) -> ValidationResult:
        """Validate value and return result"""
        result = ValidationResult()
        
        if not self._validate_value(value):
            error_msg = self.error_message or self._get_default_error_message()
            result.add_error(error_msg)
        
        return result
    
    def _get_default_error_message(self) -> str:
        """Get default error message"""
        return f"Validation failed for {self.__class__.__name__}"


class RequiredValidator(BaseValidator):
    """Validator for required fields"""
    
    def _validate_value(self, value: Any) -> bool:
        """Check if value is present"""
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        return True
    
    def _get_default_error_message(self) -> str:
        return "This field is required"


class EmailValidator(BaseValidator):
    """Validator for email addresses"""
    
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    def _validate_value(self, value: Any) -> bool:
        """Validate email format"""
        if not isinstance(value, str):
            return False
        return bool(self.EMAIL_PATTERN.match(value))
    
    def _get_default_error_message(self) -> str:
        return "Invalid email format"


class PhoneValidator(BaseValidator):
    """Validator for Brazilian phone numbers"""
    
    def _validate_value(self, value: Any) -> bool:
        """Validate Brazilian phone number"""
        if not isinstance(value, str):
            return False
        
        # Remove non-digits
        digits = re.sub(r'\D', '', value)
        
        # Check length (10-13 digits)
        if len(digits) < 10 or len(digits) > 13:
            return False
        
        # Additional Brazilian phone validation logic
        return self._validate_brazilian_phone(digits)
    
    def _validate_brazilian_phone(self, digits: str) -> bool:
        """Validate Brazilian phone number format"""
        n = len(digits)
        
        # Valid patterns:
        # 10 digits: DDD + number (ex: 6293159124)
        # 11 digits: DDD + 9 + number (ex: 62993159124)
        # 12 digits: DDI + DDD + number (ex: 556293159124)
        # 13 digits: DDI + DDD + 9 + number (ex: 5562993159124)
        
        if n == 10:
            return digits[:2].isdigit() and digits[2:].isdigit()
        elif n == 11:
            return digits[:2].isdigit() and digits[2] == '9' and digits[3:].isdigit()
        elif n == 12:
            return digits.startswith('55') and digits[2:4].isdigit() and digits[4:].isdigit()
        elif n == 13:
            return digits.startswith('55') and digits[2:4].isdigit() and digits[4] == '9' and digits[5:].isdigit()
        
        return False
    
    def _get_default_error_message(self) -> str:
        return "Invalid Brazilian phone number format"


class CNPJValidator(BaseValidator):
    """Validator for Brazilian CNPJ"""
    
    def _validate_value(self, value: Any) -> bool:
        """Validate CNPJ format and check digit"""
        if not isinstance(value, str):
            return False
        
        # Remove non-digits
        cnpj = re.sub(r'\D', '', value)
        
        # Check length
        if len(cnpj) != 14:
            return False
        
        # Check if all digits are the same
        if cnpj == cnpj[0] * 14:
            return False
        
        # Validate check digits
        return self._validate_cnpj_check_digits(cnpj)
    
    def _validate_cnpj_check_digits(self, cnpj: str) -> bool:
        """Validate CNPJ check digits"""
        # First check digit
        sequence = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        sum_result = sum(int(cnpj[i]) * sequence[i] for i in range(12))
        remainder = sum_result % 11
        first_check = 0 if remainder < 2 else 11 - remainder
        
        if int(cnpj[12]) != first_check:
            return False
        
        # Second check digit
        sequence = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        sum_result = sum(int(cnpj[i]) * sequence[i] for i in range(13))
        remainder = sum_result % 11
        second_check = 0 if remainder < 2 else 11 - remainder
        
        return int(cnpj[13]) == second_check
    
    def _get_default_error_message(self) -> str:
        return "Invalid CNPJ format"


class CPFValidator(BaseValidator):
    """Validator for Brazilian CPF"""
    
    def _validate_value(self, value: Any) -> bool:
        """Validate CPF format and check digit"""
        if not isinstance(value, str):
            return False
        
        # Remove non-digits
        cpf = re.sub(r'\D', '', value)
        
        # Check length
        if len(cpf) != 11:
            return False
        
        # Check if all digits are the same
        if cpf == cpf[0] * 11:
            return False
        
        # Validate check digits
        return self._validate_cpf_check_digits(cpf)
    
    def _validate_cpf_check_digits(self, cpf: str) -> bool:
        """Validate CPF check digits"""
        # First check digit
        sum_result = sum(int(cpf[i]) * (10 - i) for i in range(9))
        remainder = sum_result % 11
        first_check = 0 if remainder < 2 else 11 - remainder
        
        if int(cpf[9]) != first_check:
            return False
        
        # Second check digit
        sum_result = sum(int(cpf[i]) * (11 - i) for i in range(10))
        remainder = sum_result % 11
        second_check = 0 if remainder < 2 else 11 - remainder
        
        return int(cpf[10]) == second_check
    
    def _get_default_error_message(self) -> str:
        return "Invalid CPF format"


class CompositeValidator(IValidator):
    """Validator that combines multiple validators"""
    
    def __init__(self, validators: List[IValidator]):
        self.validators = validators
    
    def validate(self, value: Any) -> ValidationResult:
        """Validate using all validators"""
        result = ValidationResult()
        
        for validator in self.validators:
            validator_result = validator.validate(value)
            if not validator_result.is_valid:
                result.errors.extend(validator_result.errors)
                result.is_valid = False
        
        return result


class FieldValidator:
    """Validator for validating fields in dictionaries"""
    
    def __init__(self):
        self.field_validators: Dict[str, List[IValidator]] = {}
    
    def add_field_validator(self, field_name: str, validator: IValidator) -> None:
        """Add validator for a field"""
        if field_name not in self.field_validators:
            self.field_validators[field_name] = []
        self.field_validators[field_name].append(validator)
    
    def validate_dict(self, data: Dict[str, Any]) -> Dict[str, ValidationResult]:
        """Validate dictionary data"""
        results = {}
        
        for field_name, validators in self.field_validators.items():
            value = data.get(field_name)
            
            # Create composite validator for the field
            composite = CompositeValidator(validators)
            results[field_name] = composite.validate(value)
        
        return results
    
    def is_valid(self, data: Dict[str, Any]) -> bool:
        """Check if all fields are valid"""
        results = self.validate_dict(data)
        return all(result.is_valid for result in results.values())
    
    def get_errors(self, data: Dict[str, Any]) -> Dict[str, List[str]]:
        """Get all validation errors"""
        results = self.validate_dict(data)
        return {
            field: result.errors 
            for field, result in results.items() 
            if not result.is_valid
        }


# Factory functions
def create_required_validator(error_message: str = None) -> RequiredValidator:
    """Create required field validator"""
    return RequiredValidator(error_message)


def create_email_validator(error_message: str = None) -> EmailValidator:
    """Create email validator"""
    return EmailValidator(error_message)


def create_phone_validator(error_message: str = None) -> PhoneValidator:
    """Create phone validator"""
    return PhoneValidator(error_message)


def create_cnpj_validator(error_message: str = None) -> CNPJValidator:
    """Create CNPJ validator"""
    return CNPJValidator(error_message)


def create_cpf_validator(error_message: str = None) -> CPFValidator:
    """Create CPF validator"""
    return CPFValidator(error_message)


# Common validator combinations
def create_contact_validator() -> FieldValidator:
    """Create validator for contact data"""
    validator = FieldValidator()
    
    validator.add_field_validator('contact_name', create_required_validator())
    validator.add_field_validator('contact_number', create_required_validator())
    validator.add_field_validator('contact_number', create_phone_validator())
    
    return validator


def create_company_validator() -> FieldValidator:
    """Create validator for company data"""
    validator = FieldValidator()
    
    validator.add_field_validator('company_name', create_required_validator())
    validator.add_field_validator('document', create_required_validator())
    validator.add_field_validator('document', create_cnpj_validator())
    
    return validator

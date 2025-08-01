# app/utils/utils.py

"""
Main utilities module following SOLID principles.
Imports specific utilities from dedicated modules.
"""

# Import decorators
from app.utils.decorators import (
    retry_with_backoff,
    respond_with_200_on_exception,
    debug,
    RetryDecorator,
    WebhookResponseDecorator,
    DebugDecorator,
)

# Import validation utilities
from app.utils.validation import PhoneNumberValidator

# Import Selenium utilities
from app.utils.selenium_utils import SeleniumDiagnosticTool

# Import phone utils
from app.utils.phone_utils import standardize_phone_number

# Re-export for backward compatibility
standardize_phone_number = PhoneNumberValidator.standardize_phone_number
save_page_diagnosis = SeleniumDiagnosticTool.save_page_diagnosis
truncate = DebugDecorator.truncate

__all__ = [
    # Decorators
    "retry_with_backoff",
    "respond_with_200_on_exception",
    "debug",
    "RetryDecorator",
    "WebhookResponseDecorator",
    "DebugDecorator",
    # Validation
    "PhoneNumberValidator",
    "standardize_phone_number",
    # Selenium
    "SeleniumDiagnosticTool",
    "save_page_diagnosis",
    # Utilities
    "truncate",
]

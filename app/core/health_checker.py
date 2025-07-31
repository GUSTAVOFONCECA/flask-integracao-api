# app/core/health_checker.py
"""
Health checking service implementing IHealthChecker interface.
"""

from typing import Dict
from flask import Flask

from .interfaces import IHealthChecker, IConfigProvider
from .container import container


class HealthChecker(IHealthChecker):
    """
    Health checking service following Single Responsibility Principle.
    """
    
    def __init__(self, app: Flask, config: IConfigProvider):
        self.app = app
        self.config = config
    
    def check_api_health(self) -> bool:
        """Check if API is responding correctly"""
        try:
            with self.app.test_client() as client:
                response = client.get(
                    "/api/health/",
                    headers={"X-API-Key": self.config.get("API_KEY")},
                )
                
                if response.status_code != 200:
                    return False
                
                data = response.get_json()
                return (
                    data.get("status") == "healthy" and 
                    data.get("environment") == self.config.get("ENV")
                )
        except Exception:
            return False
    
    def check_dependencies(self) -> Dict[str, bool]:
        """Check health of all registered dependencies"""
        results = {}
        
        # Check database
        try:
            from app.database.database import init_db
            init_db()
            results["database"] = True
        except Exception:
            results["database"] = False
        
        # Check configuration
        try:
            self.config.validate()
            results["configuration"] = True
        except Exception:
            results["configuration"] = False
        
        return results

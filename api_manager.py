#!/usr/bin/env python3
"""
API Key Manager for Harvey Project
Uses single GOOGLE_API_KEY for all services
"""

import os
from pathlib import Path

class APIKeyManager:
    def __init__(self):
        self.api_key = self.load_api_key()
        
    def load_api_key(self):
        """Load single API key from .env"""
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            print("❌ No API key found! Please set up your .env file:")
            print("GOOGLE_API_KEY=your_google_api_key")
            return None
            
        print(f"✅ Loaded Google API key")
        return api_key
        
    def get_key_for_service(self, service_type=None):
        """Get API key for any service type"""
        return self.api_key
        
    def get_available_key(self, service_type=None):
        """Get the API key (simplified - always returns the same key)"""
        return self.api_key

# Global instance
api_manager = APIKeyManager()
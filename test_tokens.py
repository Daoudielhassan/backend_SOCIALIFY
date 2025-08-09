#!/usr/bin/env python3
"""
Simple test script to demonstrate JWT token generation and printing
"""

import requests
import json

# Test endpoints
BASE_URL = "http://127.0.0.1:8000"

def test_auth_config():
    """Test auth configuration endpoint"""
    print("🔧 Testing auth configuration...")
    response = requests.get(f"{BASE_URL}/auth/config")
    print(f"Auth config: {response.json()}")
    return response.status_code == 200

def test_login_with_dummy_user():
    """Test login endpoint (will fail but show token generation process)"""
    print("\n🔐 Testing login endpoint...")
    
    login_data = {
        "email": "test@example.com",
        "password": "testpassword"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json=login_data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response data: {response.json()}")
        
        if response.status_code == 200:
            token = response.json().get("access_token")
            print(f"✅ LOGIN SUCCESS - Token: {token}")
            return token
        else:
            print(f"❌ LOGIN FAILED - {response.json()}")
            return None
            
    except Exception as e:
        print(f"❌ REQUEST ERROR: {str(e)}")
        return None

def test_google_auth_init():
    """Test Google OAuth initialization"""
    print("\n🔐 Testing Google OAuth initialization...")
    
    try:
        response = requests.get(f"{BASE_URL}/auth/google/init")
        print(f"Response status: {response.status_code}")
        print(f"Response data: {response.json()}")
        
    except Exception as e:
        print(f"❌ REQUEST ERROR: {str(e)}")

def main():
    print("🚀 Starting JWT Token Testing...")
    print("=" * 50)
    
    # Test auth config
    if not test_auth_config():
        print("❌ Auth config test failed")
        return
    
    # Test login (will show debug output in server terminal)
    token = test_login_with_dummy_user()
    
    # Test Google OAuth init
    test_google_auth_init()
    
    print("\n" + "=" * 50)
    print("✅ Token testing complete!")
    print("🔍 Check the server terminal for JWT token debug output")

if __name__ == "__main__":
    main()

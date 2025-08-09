import requests
import time
# Use your JWT token
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMyIsImVtYWlsIjoiZGFvdWRpaGE2QGdtYWlsLmNvbSIsImV4cCI6MTc1NTI5MjA3MX0.m7icamDpBHXxK1iUEf1mdOwGpKZtvfxH-soRU6p6Wqo"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

def test_gmail_endpoints():
    print("🔄 Testing Gmail Endpoints After OAuth...")
    print("="*60)
    
    # Test 1: Gmail Status
    print("📊 Test 1: Gmail Status")
    try:
        response = requests.get("http://127.0.0.1:8000/api/v1/gmail/status", headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            connection_status = data.get("connection", {}).get("status")
            print(f"   ✅ Connection Status: {connection_status}")
        else:
            print(f"   ❌ Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    print()
    
    # Test 2: Gmail Fetch (small batch)
    print("📧 Test 2: Gmail Fetch (5 messages)")
    try:
        response = requests.post(
            "http://127.0.0.1:8000/api/v1/gmail/fetch?max_messages=5&force_sync=false", 
            headers=headers
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            result = data.get("result", {})
            message_count = result.get("message_count", 0)
            print(f"   ✅ Messages fetched: {message_count}")
            print(f"   ✅ Privacy protected: {data.get('privacy_protected', False)}")
        else:
            print(f"   ❌ Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    print()
    
    # Test 3: Gmail Connection Test
    print("🔗 Test 3: Gmail Connection Test")
    try:
        response = requests.post("http://127.0.0.1:8000/api/v1/gmail/test/connection", headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            connection_ok = data.get("connection_ok", False)
            print(f"   ✅ Connection Test: {'PASSED' if connection_ok else 'FAILED'}")
        else:
            print(f"   ❌ Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    print("\n" + "="*60)
    print("📝 SUMMARY:")
    print("If all tests show ✅, your Gmail integration is working perfectly!")
    print("If you see ❌, please complete the OAuth flow first.")

if __name__ == "__main__":
    test_gmail_endpoints()

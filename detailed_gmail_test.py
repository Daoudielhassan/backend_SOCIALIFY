import requests
import json

# Use your JWT token
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMyIsImVtYWlsIjoiZGFvdWRpaGE2QGdtYWlsLmNvbSIsImV4cCI6MTc1NTI5MjA3MX0.m7icamDpBHXxK1iUEf1mdOwGpKZtvfxH-soRU6p6Wqo"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

def detailed_gmail_test():
    print("🔍 Detailed Gmail Analysis")
    print("="*60)
    
    # Test 1: Gmail Status with full response
    print("📊 Test 1: Gmail Status (Full Response)")
    try:
        response = requests.get("http://127.0.0.1:8000/api/v1/gmail/status", headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   📄 Full Response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"   ❌ Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    print("\n" + "="*60)
    
    # Test 2: Gmail Fetch with full response
    print("📧 Test 2: Gmail Fetch (Full Response)")
    try:
        response = requests.post(
            "http://127.0.0.1:8000/api/v1/gmail/fetch?max_messages=10&force_sync=true", 
            headers=headers
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   📄 Full Response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"   ❌ Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    print("\n" + "="*60)
    
    # Test 3: Connection Test with full response
    print("🔗 Test 3: Gmail Connection Test (Full Response)")
    try:
        response = requests.post("http://127.0.0.1:8000/api/v1/gmail/test/connection", headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   📄 Full Response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"   ❌ Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")

if __name__ == "__main__":
    detailed_gmail_test()

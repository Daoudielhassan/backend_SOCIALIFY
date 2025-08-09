import requests

# Use the token that was printed in the terminal
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMyIsImVtYWlsIjoiZGFvdWRpaGE2QGdtYWlsLmNvbSIsImV4cCI6MTc1NTI5MTA2OX0.wCGqctgUfeUHXMPLLV4HejZAYp9FazZay6y6cMYJ4xI"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

print("🔑 Testing JWT token...")
print(f"Token (first 50 chars): {token[:50]}...")

# Test the Gmail fetch endpoint
url = "http://127.0.0.1:8000/api/v1/gmail/fetch?max_messages=50&force_sync=false"
print(f"\n📧 Testing: {url}")

try:
    response = requests.post(url, headers=headers)
    print(f"✅ Status Code: {response.status_code}")
    print(f"📄 Response: {response.text}")
    
    if response.status_code == 200:
        print("🎉 SUCCESS! The endpoint is working correctly.")
    else:
        print("❌ The endpoint returned an error.")
        
except Exception as e:
    print(f"❌ Request failed: {str(e)}")

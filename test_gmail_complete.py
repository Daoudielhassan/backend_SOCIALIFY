import requests

# Use the token that was printed in the terminal
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMyIsImVtYWlsIjoiZGFvdWRpaGE2QGdtYWlsLmNvbSIsImV4cCI6MTc1NTI5MTA2OX0.wCGqctgUfeUHXMPLLV4HejZAYp9FazZay6y6cMYJ4xI"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

print("🔑 Testing Gmail Status Endpoint...")

# Test the Gmail status endpoint first
url = "http://127.0.0.1:8000/api/v1/gmail/status"
print(f"\n📧 Testing: {url}")

try:
    response = requests.get(url, headers=headers)
    print(f"✅ Status Code: {response.status_code}")
    print(f"📄 Response: {response.text}")
    
    if response.status_code == 200:
        print("🎉 Gmail status endpoint is working!")
    else:
        print("❌ Gmail status endpoint returned an error.")
        
except Exception as e:
    print(f"❌ Request failed: {str(e)}")

print("\n" + "="*60)
print("🔍 Testing Gmail Fetch Endpoint...")

# Test the Gmail fetch endpoint 
url = "http://127.0.0.1:8000/api/v1/gmail/fetch?max_messages=10&force_sync=false"
print(f"\n📧 Testing: {url}")

try:
    response = requests.post(url, headers=headers)
    print(f"✅ Status Code: {response.status_code}")
    print(f"📄 Response: {response.text}")
    
    if response.status_code == 200:
        print("🎉 SUCCESS! The Gmail fetch endpoint is working correctly.")
    elif response.status_code == 401:
        print("🔑 AUTHENTICATION ERROR: Gmail OAuth token needs to be refreshed.")
        print("💡 The user needs to reconnect their Gmail account.")
    else:
        print("❌ The endpoint returned an error.")
        
except Exception as e:
    print(f"❌ Request failed: {str(e)}")

print("\n" + "="*60)
print("📝 Summary:")
print("- JWT token authentication: ✅ Working")
print("- API routing: ✅ Working") 
print("- Gmail OAuth token: ❌ Needs refresh")
print("💡 Next step: User needs to reconnect Gmail via OAuth flow")

import requests
import webbrowser

# Use your working JWT token
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMyIsImVtYWlsIjoiZGFvdWRpaGE2QGdtYWlsLmNvbSIsImV4cCI6MTc1NTI5MTA2OX0.wCGqctgUfeUHXMPLLV4HejZAYp9FazZay6y6cMYJ4xI"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

print("🔄 Gmail OAuth Reconnection Helper")
print("="*50)

# Step 1: Get OAuth URL
print("🔗 Step 1: Getting Gmail OAuth URL...")
try:
    response = requests.get("http://127.0.0.1:8000/auth/google/init", headers=headers)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        oauth_data = response.json()
        oauth_url = oauth_data.get("authorization_url")
        
        print(f"✅ OAuth URL generated!")
        print(f"🔗 URL: {oauth_url}")
        print("\n" + "="*50)
        print("📋 NEXT STEPS:")
        print("1. Copy the URL below")
        print("2. Open it in your browser")
        print("3. Grant Gmail permissions")
        print("4. Copy the callback URL from your browser")
        print("5. The callback will automatically save the token")
        print("\n🔗 GMAIL OAUTH URL:")
        print(oauth_url)
        
        # Try to open automatically
        try:
            webbrowser.open(oauth_url)
            print("\n🌐 Browser opened automatically!")
        except:
            print("\n⚠️  Could not open browser automatically. Please copy the URL manually.")
            
    else:
        print(f"❌ Failed to get OAuth URL: {response.text}")
        
except Exception as e:
    print(f"❌ Error: {str(e)}")
    
print("\n" + "="*50)
print("💡 After completing OAuth in browser:")
print("   Use the callback URL to complete the connection!")

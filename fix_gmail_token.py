import requests

# Use your JWT token
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMyIsImVtYWlsIjoiZGFvdWRpaGE2QGdtYWlsLmNvbSIsImV4cCI6MTc1NTI5MTYxOH0.cHcxSHb8tR2z1QZhQsMzFLQLbT4dtwKghOwEN6qOauU"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

print("🔄 Gmail Token Reset Helper")
print("="*50)

# Step 1: Disconnect Gmail to clear the corrupted token
print("🔌 Step 1: Disconnecting Gmail to clear corrupted token...")
try:
    response = requests.post("http://127.0.0.1:8000/auth/gmail/disconnect", headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("✅ Gmail disconnected successfully!")
    else:
        print(f"⚠️ Disconnect response: {response.text}")
except Exception as e:
    print(f"❌ Disconnect error: {str(e)}")

print("\n" + "="*50)

# Step 2: Get new OAuth URL
print("🔗 Step 2: Getting fresh OAuth URL...")
try:
    response = requests.get("http://127.0.0.1:8000/auth/google/init", headers=headers)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        oauth_data = response.json()
        oauth_url = oauth_data.get("authorization_url")
        
        print(f"✅ Fresh OAuth URL generated!")
        print(f"🔗 URL: {oauth_url}")
        print("\n" + "="*50)
        print("📋 NEXT STEPS:")
        print("1. Copy the URL below")
        print("2. Open it in your browser") 
        print("3. Grant Gmail permissions")
        print("4. Run test_after_oauth.py again")
        print("\n🔗 FRESH GMAIL OAUTH URL:")
        print(oauth_url)
        
        # Try to open automatically
        try:
            import webbrowser
            webbrowser.open(oauth_url)
            print("\n🌐 Browser opened automatically!")
        except:
            print("\n⚠️ Could not open browser automatically. Please copy the URL manually.")
            
    else:
        print(f"❌ Failed to get OAuth URL: {response.text}")
        
except Exception as e:
    print(f"❌ Error: {str(e)}")

print("\n" + "="*50)
print("💡 This should fix the token decryption issue!")

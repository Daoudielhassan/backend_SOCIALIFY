from flask import Flask
import redis

app = Flask(__name__)

# Connect to Redis running in Docker
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

@app.route('/')
def home():
    r.set('greeting', 'Hello from Flask + Redis!')
    return r.get('greeting')

if __name__ == '__main__':
    app.run(debug=True)

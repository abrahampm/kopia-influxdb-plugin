from flask import Flask, request
import json

app = Flask(__name__)

@app.route('/test', methods=['POST'])
def webhook():
    print("\n📥 Received a POST request")

    # Print headers
    print("\n🔸 Headers:")
    for key, value in request.headers.items():
        print(f"{key}: {value}")

    # Try to parse JSON body
    try:
        data = request.get_json(force=True)
        print("\n📄 JSON Body:")
        print(json.dumps(data, indent=2))
    except Exception as e:
        print("\n⚠️ Could not parse JSON body:", str(e))
        print("📄 Raw Body:")
        print(request.data.decode('utf-8'))

    return 'OK', 200

if __name__ == '__main__':
    print("🚀 Starting debug webhook server on http://0.0.0.0:5000/")
    app.run(host='0.0.0.0', port=5000)

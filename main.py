from flask import Flask, request, jsonify
import requests
import os
import logging

# Set up Flask app to handle the callback
app = Flask(__name__)

# Set up logging for debugging
logging.basicConfig(level=logging.INFO)

# Your Discord OAuth2 credentials
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID', '1284821331560501309')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET', 'uAkfY7g7bICIgrL1hWkcqo5wiRUcHC3a')
REDIRECT_URI = 'https://aidm5e.lm.r.appspot.com/callback'  # Cloud Run service URL for Flask

@app.route('/')
def home():
    return 'Hello, Flask is running!'


# Route to handle the OAuth2 callback
@app.route('/callback')
def callback():
    # Get the authorization code from the query parameters
    code = request.args.get('code')
    
    if not code:
        logging.error("No code provided by Discord.")
        return "Error: No code provided by Discord.", 400

    # Exchange the authorization code for an access token
    TOKEN_URL = 'https://discord.com/api/oauth2/token'
    
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }

    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        response = requests.post(TOKEN_URL, data=data, headers=headers)
        token_data = response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Token exchange failed: {e}")
        return "Error: Failed to exchange code for token.", 500

    # Check if we successfully got an access token
    if 'access_token' in token_data:
        access_token = token_data['access_token']
        logging.info(f"Access Token: {access_token}")

        # Use the access token to fetch user info
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            user_info = requests.get('https://discord.com/api/users/@me', headers=headers).json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch user info: {e}")
            return "Error: Failed to fetch user info.", 500

        # Return the user info as JSON
        logging.info(f"User Info: {user_info}")
        return jsonify(user_info), 200
    else:
        logging.error(f"Error retrieving access token: {token_data}")
        return f"Error retrieving access token: {token_data}", 400


# Run the Flask server
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)  # Listen on all interfaces

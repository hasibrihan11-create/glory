HASIB BOTS | Guild Glory Dashboard

Files: app.py, requirements.txt

Run locally:
  pip install -r requirements.txt
  python app.py

For production use a WSGI start command:
  gunicorn app:app --bind 0.0.0.0:$PORT

Set environment variables on your host:
  ACCESS_KEY = a long private dashboard password
  FLASK_SECRET = a long random secret

Important:
- This dashboard does NOT include the original bot engine. The supplied ZIP only has Android-specific compiled .so modules, so Start/Stop/Restart are intentionally disabled.
- Auto Join Clan calls the API URL supplied by the project owner using uploaded account credentials. Keep the dashboard private, use only accounts you own/are authorized to use, and do not share accounts.json.
- Uploaded account data is held in memory and is lost when the app restarts. Do not use a public deployment without setting ACCESS_KEY.

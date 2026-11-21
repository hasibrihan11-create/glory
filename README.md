# Lightweight Multi-User Python Hosting Panel

Single-file Flask dashboard for Railway.

## Files
- `main.py`: app, embedded HTML/CSS, authentication, workspace uploads and safe diagnostics.
- `requirements.txt`: dependencies.
- `Procfile`: Railway start command.

## Railway setup
1. Deploy this repository from GitHub.
2. Set start command to `gunicorn --workers 1 --threads 4 --timeout 60 main:app` (or let Railway use Procfile).
3. Add variables:
   - `SECRET_KEY`: long random secret (required for stable sessions)
   - `DATA_DIR`: persistent mounted volume path, e.g. `/data`
   - `MAX_UPLOAD_MB`: optional, defaults to 25
4. Attach a Railway Volume at `/data` if you want SQLite and uploaded files to persist across deploys/restarts.

## Important execution limitation
This starter intentionally does **not** run arbitrary uploaded Python scripts or arbitrary shell commands inside the shared web service. That would let one user compromise other users and the dashboard. To offer real multi-user bot hosting, add a separate isolated worker/container per user with strict CPU, memory, filesystem, network and time limits. Railway's ordinary single web service is not a security boundary between untrusted scripts.

The first registered account is marked admin in the database, but advanced admin controls are not included in this starter.

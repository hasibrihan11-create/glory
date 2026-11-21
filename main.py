import os
import io
import zipfile
import sqlite3
import secrets
import subprocess
import sys
from pathlib import Path
from functools import wraps

from flask import Flask, request, redirect, url_for, session, flash, render_template_string, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = Path(os.environ.get("DATA_DIR", "data")).resolve()
WORKSPACES = BASE / "workspaces"
DB_PATH = BASE / "panel.db"
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
BASE.mkdir(parents=True, exist_ok=True)
WORKSPACES.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

STYLE = """
:root{color-scheme:dark;--bg:#090d18;--panel:#111a2b;--line:#26344d;--muted:#91a0b8;--text:#edf3ff;--blue:#6d8cff;--green:#42d6a0}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0,#18264a 0,transparent 35%),var(--bg);color:var(--text);font:15px Inter,system-ui,sans-serif}
a{color:#a9bcff;text-decoration:none}button,.btn{background:var(--blue);border:0;border-radius:9px;padding:10px 14px;color:white;font-weight:700;cursor:pointer}
input{width:100%;background:#0a1221;border:1px solid var(--line);border-radius:9px;padding:12px;color:white;margin:6px 0 14px}
.wrap{max-width:1100px;margin:35px auto;padding:0 18px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}
.brand{font-weight:900;letter-spacing:.08em}.muted,small{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.card{background:linear-gradient(145deg,#142039,#0e1728);border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:14px}
h1{font-size:28px;margin:8px 0}h2{font-size:17px;margin-top:0}.stat{font-size:26px;font-weight:800}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.row input{flex:1;min-width:180px}
.file{padding:10px 0;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:10px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#070c15;padding:14px;border-radius:10px;color:#b8f5d8;min-height:90px}
.notice{padding:12px;border-radius:10px;background:#172744;margin:12px 0}.danger{color:#ff9b9b}
@media(max-width:600px){.wrap{margin:18px auto}.top{align-items:flex-start;gap:10px;flex-direction:column}}
"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }}</title><style>""" + STYLE + """</style></head><body><main class="wrap">{{ body|safe }}</main></body></html>"""

LOGIN = """
<div class="card" style="max-width:440px;margin:8vh auto">
 <div class="brand">HASIB BOTS <span class="muted">/ PYTHON HOST</span></div><h1>{{ heading }}</h1>
 <p class="muted">Lightweight multi-user workspace dashboard</p>
 {% with messages=get_flashed_messages() %}{% for m in messages %}<div class="notice">{{m}}</div>{% endfor %}{% endwith %}
 <form method="post"><label>Username</label><input name="username" required minlength="3" maxlength="32" autocomplete="username">
 <label>Password</label><input name="password" type="password" required minlength="8" autocomplete="current-password">
 <button>{{ action }}</button></form><p class="muted">{{ other|safe }}</p>
</div>"""

DASH = """
<div class="top"><div><div class="brand">HASIB BOTS / PYTHON HOST</div><div class="muted">Workspace dashboard</div></div><div>Signed in as <b>{{user}}</b> · <a href="/logout">Logout</a></div></div>
{% with messages=get_flashed_messages() %}{% for m in messages %}<div class="notice">{{m}}</div>{% endfor %}{% endwith %}
<div class="grid"><section class="card"><div class="muted">Workspace files</div><div class="stat">{{files|length}}</div></section><section class="card"><div class="muted">Upload limit</div><div class="stat">{{limit}} MB</div></section><section class="card"><div class="muted">Execution mode</div><div class="stat" style="font-size:19px;color:#ffc978">Sandbox pending</div></section></div>
<div class="grid"><section class="card"><h2>Upload files / ZIP</h2><form method="post" action="/upload" enctype="multipart/form-data"><input type="file" name="file" required><button>Upload</button></form><small>ZIP extraction blocks path traversal and overwrites are avoided.</small></section>
<section class="card"><h2>Quick diagnostics</h2><form method="post" action="/terminal"><input name="command" placeholder="python --version / pip list / pwd / ls" required><button>Run diagnostic</button></form><small>Only read-only allowlisted commands are accepted. No shell access.</small></section></div>
<section class="card"><h2>Your files</h2>{% if files %}{% for f in files %}<div class="file"><span>📄 {{f}}</span><a href="/download/{{f}}">Download</a></div>{% endfor %}{% else %}<p class="muted">No files uploaded yet.</p>{% endif %}</section>
<section class="card"><h2>Terminal output</h2><pre>{{output}}</pre><p class="muted">Running arbitrary uploaded Python files is intentionally disabled in this shared web process. Add a separate isolated worker/container before enabling multi-user execution.</p></section>
"""

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0
        )""")

def workspace():
    uid = str(session["uid"])
    path = (WORKSPACES / uid).resolve()
    if WORKSPACES not in path.parents:
        abort(403)
    path.mkdir(parents=True, exist_ok=True)
    return path

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if "uid" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def safe_name(name):
    name = secure_filename(name.replace("\\\\", "/").split("/")[-1])
    if not name or name in {".", ".."}:
        raise ValueError("Invalid filename")
    return name

def list_files(root):
    out = []
    for p in root.rglob("*"):
        if p.is_file() and len(out) < 300:
            out.append(p.relative_to(root).as_posix())
    return sorted(out)

@app.get("/")
def index():
    return redirect(url_for("dashboard") if "uid" in session else url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not (3 <= len(username) <= 32) or not username.replace("_", "").isalnum():
            flash("Username must be 3–32 letters, numbers or underscores.")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.")
        else:
            try:
                with db() as con:
                    cur = con.execute("INSERT INTO users(username,password_hash,is_admin) VALUES(?,?,?)",
                        (username, generate_password_hash(password), 1 if count == 0 else 0))
                    session.clear()
                    session["uid"] = cur.lastrowid
                    session["username"] = username
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("That username is already taken.")
    return render_template_string(PAGE, title="Register", body=render_template_string(LOGIN,
        heading="Create account", action="Register", other='Already registered? <a href="/login">Login</a>'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["uid"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password.")
    return render_template_string(PAGE, title="Login", body=render_template_string(LOGIN,
        heading="Welcome back", action="Login", other='New here? <a href="/register">Create account</a>'))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/dashboard")
@login_required
def dashboard():
    root = workspace()
    return render_template_string(PAGE, title="Dashboard", body=render_template_string(
        DASH, user=session["username"], files=list_files(root), limit=MAX_UPLOAD_MB,
        output=session.pop("last_output", "Ready. Upload a project or run a diagnostic command.")))

@app.post("/upload")
@login_required
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a file first.")
        return redirect(url_for("dashboard"))
    root = workspace()
    try:
        name = safe_name(f.filename)
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(f.stream) as zf:
                for item in zf.infolist():
                    if item.is_dir():
                        continue
                    parts = Path(item.filename).parts
                    if item.filename.startswith(("/", "\\\\")) or ".." in parts:
                        raise ValueError("Unsafe ZIP path detected.")
                    target = (root / Path(*parts)).resolve()
                    if root not in target.parents:
                        raise ValueError("Unsafe ZIP path detected.")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        raise ValueError("File already exists: " + item.filename)
                    if item.file_size > 10 * 1024 * 1024:
                        raise ValueError("A ZIP member exceeds 10 MB.")
                    with zf.open(item) as src, target.open("xb") as dst:
                        dst.write(src.read(10 * 1024 * 1024 + 1))
        else:
            target = root / name
            if target.exists():
                raise ValueError("File already exists.")
            f.save(target)
        flash("Upload completed.")
    except (ValueError, zipfile.BadZipFile, OSError) as e:
        flash("Upload failed: " + str(e))
    return redirect(url_for("dashboard"))

@app.get("/download/<path:name>")
@login_required
def download(name):
    root = workspace()
    target = (root / name).resolve()
    if root not in target.parents or not target.is_file():
        abort(404)
    return send_file(target, as_attachment=True)

@app.post("/terminal")
@login_required
def terminal():
    cmd = request.form.get("command", "").strip()
    allowed = {
        "python --version": [sys.executable, "--version"],
        "pip --version": [sys.executable, "-m", "pip", "--version"],
        "pip list": [sys.executable, "-m", "pip", "list", "--format=columns"],
        "pwd": ["pwd"],
        "ls": ["ls", "-la"],
    }
    if cmd not in allowed:
        session["last_output"] = "Command blocked. Allowed: " + ", ".join(allowed)
    else:
        try:
            result = subprocess.run(allowed[cmd], cwd=str(workspace()), capture_output=True,
                text=True, timeout=8, check=False, env={"PATH": os.environ.get("PATH", "")})
            session["last_output"] = (result.stdout + result.stderr)[:12000] or "(no output)"
        except Exception as e:
            session["last_output"] = "Diagnostic failed: " + str(e)
    return redirect(url_for("dashboard"))

@app.errorhandler(413)
def too_large(_):
    return "Upload too large. Maximum size is %s MB." % MAX_UPLOAD_MB, 413

@app.get("/health")
def health():
    return {"status": "ok"}

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))

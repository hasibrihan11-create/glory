import os, json, threading, time
from flask import Flask, request, jsonify, session, redirect, render_template_string
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'change-this-secret-before-deploying')
ACCESS_KEY = os.environ.get('ACCESS_KEY', '')
ENGINE_AVAILABLE = False  # This ZIP has Android-only .so modules, not a host-compatible bot engine.
accounts = []
state = {'bot': 'Engine unavailable', 'last_action': 'Dashboard ready'}
lock = threading.Lock()

PAGE = r'''<!doctype html><n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HASIB BOTS | Guild Glory</title><style>
:root{color-scheme:dark;--bg:#080b13;--panel:#111827;--line:#263247;--muted:#9aa8bd;--accent:#8b5cf6;--cyan:#22d3ee}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% 0,#211548 0,transparent 35%),var(--bg);color:#eef2ff;font:15px Inter,system-ui,Arial}.wrap{max-width:1100px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.brand{font-weight:900;letter-spacing:1.4px}.brand span{color:#a78bfa}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-top:20px}.card{background:#111827eF;border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:0 14px 40px #0005}.wide{grid-column:1/-1}h2{font-size:17px;margin:0 0 14px}button,.btn{border:0;border-radius:10px;padding:11px 15px;background:var(--accent);color:white;font-weight:700;cursor:pointer}button.alt{background:#263247}button.red{background:#9f334d}button:disabled{opacity:.45;cursor:not-allowed}input,textarea{width:100%;background:#080d18;border:1px solid var(--line);border-radius:10px;padding:12px;color:white;margin:7px 0 12px}textarea{min-height:85px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#070b12;border:1px solid var(--line);border-radius:12px;padding:14px;min-height:90px;color:#b8c7dc}.pill{display:inline-block;padding:6px 10px;border-radius:99px;background:#392b17;color:#fbbf24;font-size:12px}.row{display:flex;gap:8px;flex-wrap:wrap}.small{font-size:12px}.account{padding:9px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:10px}.login{max-width:390px;margin:12vh auto}.danger{color:#fca5a5}a{color:#c4b5fd}
</style></head><body><div class="wrap"><div class="top"><div class="brand">HASIB BOTS <span>| GUILD GLORY</span><div class="muted small">CONTROL DASHBOARD</div></div><div><span class="pill">BOT ENGINE NOT CONNECTED</span></div></div>
<div class="grid"><section class="card"><h2>Bot controls</h2><p class="muted">Engine status: <b id="status">{{status}}</b></p><div class="row"><button disabled title="Requires a compatible bot engine">Start</button><button class="alt" disabled>Stop</button><button class="alt" disabled>Restart</button></div><p class="small danger">Your ZIP contains Android-only compiled modules. These controls remain disabled until a compatible engine is supplied.</p></section>
<section class="card"><h2>Account manager</h2><form id="upload"><input type="file" name="file" accept=".json,.txt" required><button>Upload accounts</button></form><p class="muted small">JSON records must include uid and password. Keep this dashboard private.</p><div id="accounts">{{count}} accounts loaded</div></section>
<section class="card"><h2>Auto Join Clan</h2><label class="muted small">Guild / clan ID (used if an account has no clan_id)</label><input id="guild" placeholder="Enter guild ID"><button id="join">Auto Join Clan</button><p class="muted small">Uses the join API endpoint you provided. Only run this for accounts you own or are authorized to use.</p></section>
<section class="card"><h2>Console</h2><pre id="log">{{last}}</pre><div class="row"><input id="cmd" placeholder="Dashboard note / command" style="flex:1"><button id="send">Send</button></div><p class="muted small">Commands are logged only; no bot process is connected yet.</p></section></div></div>
<script>
const log=document.getElementById('log');function say(t){log.textContent=new Date().toLocaleTimeString()+'  '+t+'\\n'+log.textContent}
document.getElementById('upload').onsubmit=async e=>{e.preventDefault();let r=await fetch('/api/accounts',{method:'POST',body:new FormData(e.target)});let d=await r.json();say(d.message||d.error);if(d.ok)document.getElementById('accounts').textContent=d.count+' accounts loaded'};
document.getElementById('join').onclick=async()=>{let guild_id=document.getElementById('guild').value.trim();if(!guild_id){say('Enter a guild ID first');return}let b=document.getElementById('join');b.disabled=true;b.textContent='Joining...';try{let r=await fetch('/api/auto_join_clans',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({guild_id})});let d=await r.json();say(d.message||d.error||'Finished')}catch(e){say('Request failed: '+e)}finally{b.disabled=false;b.textContent='Auto Join Clan'}};
document.getElementById('send').onclick=async()=>{let command=document.getElementById('cmd').value.trim();if(!command)return;let r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command})});let d=await r.json();say(d.message||d.error);document.getElementById('cmd').value=''};
</script></body></html>'''.replace('<n<html','<html')

LOGIN = '''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Guild Glory Login</title><style>body{background:#080b13;color:white;font:16px Arial;display:grid;place-items:center;height:100vh}.box{background:#111827;padding:28px;border-radius:16px;width:min(90%,360px)}input,button{width:100%;padding:12px;margin-top:12px;border-radius:9px}input{background:#080d18;color:white;border:1px solid #334155}button{background:#8b5cf6;color:white;border:0;font-weight:bold}</style><form class="box" method="post"><h2>HASIB BOTS</h2><p>Guild Glory access</p><input name="key" type="password" placeholder="Access key" required><button>Sign in</button><p>{{error}}</p></form>'''

def authorized():
    return (not ACCESS_KEY) or session.get('ok') is True

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        if ACCESS_KEY and request.form.get('key') == ACCESS_KEY:
            session['ok'] = True
            return redirect('/')
        return render_template_string(LOGIN, error='Incorrect access key')
    return render_template_string(LOGIN, error='')

@app.before_request
def protect():
    if ACCESS_KEY and request.endpoint not in ('login',) and not session.get('ok'):
        if request.path.startswith('/api/'): return jsonify(ok=False,error='Login required'),401
        return redirect('/login')

@app.route('/')
def home():
    return render_template_string(PAGE,status=state['bot'],last=state['last_action'],count=len(accounts))

@app.route('/api/accounts', methods=['POST'])
def upload_accounts():
    global accounts
    f=request.files.get('file')
    if not f: return jsonify(ok=False,error='Choose a file'),400
    try:
        raw=f.read().decode('utf-8-sig')
        if f.filename.lower().endswith('.json'):
            data=json.loads(raw)
        else:
            data=[]
            for line in raw.splitlines():
                parts=line.strip().split('|')
                if len(parts)>=2 and parts[0].lower()!='uid': data.append({'uid':parts[0],'password':parts[1]})
        if isinstance(data,dict): data=data.get('accounts',[])
        if not isinstance(data,list): raise ValueError('Expected a JSON array of accounts')
        valid=[]
        for item in data:
            if isinstance(item,dict) and item.get('uid') and item.get('password'):
                valid.append({'uid':str(item['uid']),'password':str(item['password']),'clan_id':str(item.get('clan_id',''))})
        accounts=valid
        return jsonify(ok=True,count=len(accounts),message=f'Loaded {len(accounts)} valid accounts')
    except Exception as e: return jsonify(ok=False,error=f'Could not read accounts: {e}'),400

@app.route('/api/auto_join_clans', methods=['POST'])
def auto_join_clans():
    data=request.get_json(silent=True) or {}; default_guild=str(data.get('guild_id','')).strip()
    if not accounts: return jsonify(ok=False,message='Upload accounts.json first'),400
    if not default_guild and not any(a['clan_id'] for a in accounts): return jsonify(ok=False,message='Enter a guild ID or add clan_id to accounts'),400
    results=[]
    for a in accounts:
        gid=a['clan_id'] or default_guild
        try:
            resp=requests.get('https://danger-guild-management-web.vercel.app/join',params={'guild_id':gid,'uid':a['uid'],'password':a['password']},timeout=20)
            # Include the API's rejection reason so HTTP 400 can be diagnosed.
            # Never echo the account password into the dashboard log.
            detail=(resp.text or '').replace(a['password'],'[redacted]').replace('\\r',' ').replace('\\n',' ').strip()[:350]
            results.append(f"{a['uid']}: HTTP {resp.status_code}" + (f" — {detail}" if detail else ""))
        except requests.RequestException as e: results.append(f"{a['uid']}: request failed ({e})")
        time.sleep(0.2)
    state['last_action']=f'Auto join attempted for {len(results)} accounts'
    return jsonify(ok=True,message='\\n'.join(results))

@app.route('/api/command', methods=['POST'])
def command():
    cmd=str((request.get_json(silent=True) or {}).get('command','')).strip()
    if not cmd: return jsonify(ok=False,error='Empty command'),400
    state['last_action']='Logged dashboard command: '+cmd[:160]
    return jsonify(ok=True,message='Saved to dashboard log. No bot engine is connected.')

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8080')))

# app.py
import os
import io
import zipfile
import sqlite3
from functools import wraps
from pathlib import Path
from datetime import timedelta
from flask import (
    Flask, request, jsonify, render_template_string,
    redirect, url_for, session, send_from_directory, flash, make_response
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import Workbook

# ---- CONFIG ----
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "alumni.db"
UPLOAD_FOLDER.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = "secret-key-change-me"
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.permanent_session_lifetime = timedelta(days=7)

# ---- DB ----
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            is_admin INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS alumni(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullName TEXT,
            phone TEXT,
            nin TEXT,
            school TEXT,
            neighborhood TEXT,
            photo TEXT,
            approved INTEGER DEFAULT 0
        )""")
init_db()

# ---- HELPERS ----
def allowed_file(f): return "." in f and f.rsplit(".",1)[1].lower() in {"png","jpg","jpeg"}
def admin_required(f):
    @wraps(f)
    def wrap(*a,**kw):
        uid = session.get("uid")
        if not uid: return redirect(url_for("login"))
        with get_db() as c:
            u=c.execute("select * from users where id=?",(uid,)).fetchone()
        if not u or not u["is_admin"]:
            flash("Admin only"); return redirect(url_for("login"))
        return f(*a,**kw)
    return wrap
def login_required(f):
    @wraps(f)
    def wrap(*a,**kw):
        if "uid" not in session: return redirect(url_for("login"))
        return f(*a,**kw)
    return wrap

# ---- LANG ----
TRANSL = {
 "en":{"submit":"Submit Info","name":"Full Name","phone":"Phone","nin":"NIN (optional)","school":"School","neighborhood":"Neighborhood","photo":"Passport Photo","send":"Send","thanks":"Thank you","pending":"Pending","approved":"Approved","download":"Download","approve":"Approve"},
 "ha":{"submit":"Aika Bayanka","name":"Cikakken Suna","phone":"Lambar Waya","nin":"NIN (ba lallai ba)","school":"Makaranta","neighborhood":"Unguwa","photo":"Hoton Fasfo","send":"Aika","thanks":"Na gode","pending":"Ana Jira","approved":"An Amince","download":"Sauke","approve":"Amince"},
}
def t(k): return TRANSL.get(session.get("lang","en"),TRANSL["en"]).get(k,k)

@app.route("/setlang",methods=["POST"])
def setlang():
    session["lang"]=request.form.get("lang","en")
    return redirect(request.referrer or url_for("submit"))

# ---- ROUTES ----
@app.route("/submit",methods=["GET","POST"])
def submit():
    if request.method=="POST":
        fullName=request.form["fullName"].strip()
        phone=request.form["phone"].strip()
        nin=request.form.get("nin","").strip()
        school=request.form["school"].strip()
        neigh=request.form["neighborhood"].strip()
        if not fullName or not phone or not school:
            flash("Please fill required fields."); return redirect(url_for("submit"))
        photo=request.files.get("photo"); fn=""
        if photo and allowed_file(photo.filename):
            fn=secure_filename(photo.filename)
            photo.save(str(UPLOAD_FOLDER/fn))
        with get_db() as c:
            c.execute("insert into alumni(fullName,phone,nin,school,neighborhood,photo)values(?,?,?,?,?,?)",
                (fullName,phone,nin,school,neigh,fn))
            rid=c.lastrowid
        return redirect(url_for("thankyou",id=rid))
    return render_template_string(TEMPLATE,view="submit",t=t,user=session.get("user"))

@app.route("/thankyou")
def thankyou():
    i=request.args.get("id",type=int)
    if not i:return redirect(url_for("submit"))
    with get_db() as c: r=c.execute("select * from alumni where id=?",(i,)).fetchone()
    if not r:return redirect(url_for("submit"))
    return render_template_string(TEMPLATE,view="thankyou",t=t,user=session.get("user"),r=r)

@app.route("/register",methods=["GET","POST"])
def register():
    with get_db() as c:
        if c.execute("select count(*) from users").fetchone()[0]>0:
            flash("Closed"); return redirect(url_for("login"))
    if request.method=="POST":
        u=request.form["username"]; p=request.form["password"]
        with get_db() as c:
            c.execute("insert into users(username,password_hash,is_admin)values(?,?,1)",
                      (u,generate_password_hash(p)))
        flash("Created"); return redirect(url_for("login"))
    return render_template_string(TEMPLATE,view="register",t=t,user=None)

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        u,p=request.form["username"],request.form["password"]
        with get_db() as c:
            row=c.execute("select * from users where username=?",(u,)).fetchone()
        if row and check_password_hash(row["password_hash"],p):
            session["uid"]=row["id"]; session["user"]=u
            return redirect(url_for("dashboard"))
        flash("Invalid")
    return render_template_string(TEMPLATE,view="login",t=t,user=None)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    return render_template_string(TEMPLATE,view="dash",t=t,user=session.get("user"))

@app.route("/uploads/<fn>")
@login_required
def uploads(fn):
    return send_from_directory(UPLOAD_FOLDER,fn)

# ---- APIs ----
@app.route("/api/pending")
@admin_required
def api_pending():
    with get_db() as c:r=c.execute("select * from alumni where approved=0").fetchall()
    return jsonify([dict(x) for x in r])

@app.route("/api/approved")
@admin_required
def api_approved():
    q=request.args.get("q","")
    with get_db() as c:
        r=c.execute("select * from alumni where approved=1 and fullName like ?",(f"%{q}%",)).fetchall()
    return jsonify([dict(x) for x in r])

@app.route("/api/approve/<int:i>",methods=["POST"])
@admin_required
def api_approve(i):
    with get_db() as c:c.execute("update alumni set approved=1 where id=?",(i,))
    return jsonify({"ok":1})

@app.route("/download")
@admin_required
def download():
    with get_db() as c:r=c.execute("select * from alumni where approved=1").fetchall()
    wb=Workbook();ws=wb.active
    ws.append(["Full Name","Phone","NIN","School","Neighborhood","Photo"])
    for x in r: ws.append([x["fullName"],x["phone"],x["nin"],x["school"],x["neighborhood"],x["photo"]])
    b=io.BytesIO();wb.save(b);b.seek(0)
    z=io.BytesIO()
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("alumni.xlsx",b.getvalue())
        for x in r:
            if x["photo"]:
                p=UPLOAD_FOLDER/x["photo"]
                if p.exists():zf.write(p,arcname=f"photos/{x['photo']}")
    z.seek(0)
    resp=make_response(z.read())
    resp.headers["Content-Type"]="application/zip"
    resp.headers["Content-Disposition"]="attachment; filename=alumni.zip"
    return resp

# ---- TEMPLATE ----
TEMPLATE="""
<!doctype html><html><head>
<title>Alumni</title>
<style>
body{font-family:sans-serif;background:#f6e9d3;margin:0;padding:0}
header{background:#8b6b43;color:#fff;padding:10px}
.card{background:#fff;margin:20px auto;padding:20px;border-radius:8px;max-width:600px}
input,button{padding:8px;margin:5px 0;width:100%;border-radius:6px;border:1px solid #ccc}
button{background:#8b6b43;color:#fff;border:none}
</style></head><body>
<header>
  <form method="post" action="/setlang" style="float:right">
    <select name="lang" onchange="this.form.submit()">
      <option value="en">EN</option><option value="ha">HA</option>
    </select>
  </form>
  Alumni Portal
</header>
<div class="card">
{% if view=='submit' %}
<h2>{{t('submit')}}</h2>
<form method=post enctype=multipart/form-data>
<label>{{t('name')}}</label><input name=fullName required>
<label>{{t('phone')}}</label><input name=phone required>
<label>{{t('nin')}}</label><input name=nin>
<label>{{t('school')}}</label><input name=school required>
<label>{{t('neighborhood')}}</label><input name=neighborhood required>
<label>{{t('photo')}}</label><input type=file name=photo accept=image/* required>
<button>{{t('send')}}</button>
</form>
{% elif view=='thankyou' %}
<h3>{{t('thanks')}}</h3>
<p>{{r['fullName']}} - {{r['school']}}</p>
{% elif view=='register' %}
<h3>Register Admin</h3>
<form method=post><input name=username required><input name=password type=password required><button>Register</button></form>
{% elif view=='login' %}
<h3>Login</h3>
<form method=post><input name=username required><input name=password type=password required><button>Login</button></form>
{% elif view=='dash' %}
<h3>Admin Dashboard</h3>
<input id=q placeholder="Search name">
<button onclick="dl()">Download</button>
<div id=pending></div><hr><div id=approved></div>
<script>
async function j(u,o){let r=await fetch(u,o||{});return r.json();}
async function load(){
let p=await j('/api/pending');let a=await j('/api/approved');
let P=document.getElementById('pending'),A=document.getElementById('approved');
P.innerHTML='<h4>Pending</h4>'+p.map(x=>`<div>${x.fullName} <button onclick=ap(${x.id})>{{t('approve')}}</button></div>`).join('');
A.innerHTML='<h4>Approved</h4>'+a.map(x=>`<div>${x.fullName}</div>`).join('');
}
async function ap(i){await fetch('/api/approve/'+i,{method:'POST'});load();}
function dl(){window.location='/download';}
document.getElementById('q').oninput=()=>load();
load();
</script>
{% endif %}
</div>
</body></html>
"""

if __name__=="__main__":
    app.run(debug=True)

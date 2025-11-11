# app.py
import os
import io
import csv
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

# ---------------- Config ----------------
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "alumni.db"
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif"}
MAX_CONTENT_LENGTH = 6 * 1024 * 1024  # 6 MB

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-this-secret")
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.permanent_session_lifetime = timedelta(days=7)

ENV_ADMIN = os.environ.get("FLASK_ADMIN_USERNAME")  # optional override for first admin

# ---------------- DB helpers ----------------
def get_db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alumni (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fullName TEXT,
                phone TEXT,
                neighborhood TEXT,
                photo TEXT,
                approved INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
init_db()

# ---------------- Auth helpers ----------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("login"))
        with get_db_conn() as conn:
            row = conn.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
        if not row or row["is_admin"] != 1:
            flash("Access denied: admin only.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def current_user_is_admin():
    uid = session.get("user_id")
    if not uid:
        return False
    with get_db_conn() as conn:
        row = conn.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
    return bool(row and row["is_admin"] == 1)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# ---------------- Template ----------------
# Single-file HTML + CSS + JS. Two-column admin dashboard (Pending | Approved).
TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Alumni Portal</title>
<style>
  :root{
    --public-bg: #f3e6d1;        /* light brown for public */
    --admin-bg: #caa97f;         /* slightly darker for admin */
    --accent: #8b6b43;
    --card: #fff;
  }
  body{font-family: Inter, Arial, Helvetica, sans-serif; margin:0; color:#222}
  header{padding:14px;color:#fff}
  /* Public header uses accent darker, admin too but different shade handled inline */
  .wrap{max-width:1100px;margin:20px auto;padding:12px}
  .card{background:var(--card);padding:14px;border-radius:10px;box-shadow:0 6px 16px rgba(0,0,0,0.08)}
  form input, form button, textarea {padding:8px;margin:6px 0;border-radius:6px;border:1px solid #ccc;width:100%;box-sizing:border-box}
  .row{display:flex;gap:12px}
  .col{flex:1}
  .grid{display:flex;gap:12px;flex-wrap:wrap}
  .alumni-card{width:220px;background:var(--card);border-radius:10px;padding:12px;text-align:center;box-shadow:0 4px 10px rgba(0,0,0,0.08)}
  .alumni-card img{width:110px;height:110px;border-radius:50%;object-fit:cover;border:3px solid #fff;margin-top:-10px;box-shadow:0 2px 6px rgba(0,0,0,0.12)}
  .actions{margin-top:8px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
  button.primary{background:var(--accent);color:#fff;border:none;padding:8px 12px;border-radius:6px;cursor:pointer}
  button.warn{background:crimson;color:#fff;border:none;padding:6px 10px;border-radius:6px;cursor:pointer}
  .small{font-size:0.9rem;color:#555}
  .searchbox{max-width:360px;padding:8px;border-radius:8px;border:1px solid #aaa}
  .two-col{display:flex;gap:12px}
  .pane{flex:1}
  .pending-header{display:flex;justify-content:space-between;align-items:center}
  .muted{color:#666;font-size:0.9rem}
  .note{font-size:0.9rem;color:#444;margin-bottom:8px}
  @media(max-width:900px){ .two-col{flex-direction:column} .alumni-card{width:90%} }
</style>
</head>
<body style="background: {% if view == 'submit' or view == 'thankyou' %}var(--public-bg){% else %}var(--admin-bg){% endif %};">
<header style="background: {% if view == 'submit' or view == 'thankyou' %}var(--accent){% else %}#7a5836{% endif %};">
  <div style="max-width:1100px;margin:0 auto;padding:6px 12px;display:flex;justify-content:space-between;align-items:center">
    <div style="color:#fff;font-weight:700">Alumni Portal</div>
    <div style="color:#fff;font-size:0.95rem">
      {% if user %}
        Logged in as <strong>{{user}}</strong>
        {% if is_admin %} • <span style="color:#ffd">Admin</span> {% endif %}
        • <a href="{{ url_for('logout') }}" style="color:#ffd;text-decoration:none">Logout</a>
      {% else %}
        <a href="{{ url_for('login') }}" style="color:#ffd;text-decoration:none;margin-right:10px">Admin Login</a>
        <a href="{{ url_for('submit') }}" style="color:#ffd;text-decoration:none">Submit Info</a>
      {% endif %}
    </div>
  </div>
</header>

<div class="wrap">
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div class="card" style="margin-bottom:12px"><ul>{% for m in messages %}<li style="color:crimson">{{ m }}</li>{% endfor %}</ul></div>
    {% endif %}
  {% endwith %}

  {% if view == 'submit' %}
    <div class="card">
      <h2>Submit Your Info</h2>
      <p class="note">Fill your full name, phone, neighborhood and upload a passport photo (png/jpg). Your submission will be reviewed by the admin.</p>
      <form action="{{ url_for('submit') }}" method="post" enctype="multipart/form-data">
        <label>Full name</label>
        <input name="fullName" required>
        <label>Phone</label>
        <input name="phone" required>
        <label>Neighborhood</label>
        <input name="neighborhood" required>
        <label>Passport photo (png/jpg/jpeg/gif) — max 6MB</label>
        <input type="file" name="photo" accept="image/*" required>
        <div style="display:flex;gap:8px;margin-top:8px">
          <button class="primary" type="submit">Submit</button>
          <a href="{{ url_for('login') }}"><button type="button">Admin Login</button></a>
        </div>
      </form>
    </div>

  {% elif view == 'thankyou' %}
    <div class="card">
      <h2>Thank you — Submission received</h2>
      <p class="note">Your submission is pending review by the admin. Below is a summary of what you submitted.</p>
      <div style="display:flex;gap:18px;align-items:center">
        <div style="width:140px">
          <img src="{{ photo_url }}" style="width:120px;height:120px;border-radius:50%;object-fit:cover;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.12)">
        </div>
        <div>
          <div><strong>{{ fullName }}</strong></div>
          <div class="small"><b>Phone:</b> {{ phone }}</div>
          <div class="small"><b>Neighborhood:</b> {{ neighborhood }}</div>
          <div class="small" style="margin-top:8px;color:#666">You will appear in the directory once the admin approves your submission.</div>
        </div>
      </div>
    </div>

  {% elif view == 'login' %}
    <div class="card" style="max-width:420px;margin:0 auto">
      <h2>Admin Login</h2>
      <form method="post" action="{{ url_for('login') }}">
        <label>Username</label>
        <input name="username" required>
        <label>Password</label>
        <input name="password" type="password" required>
        <div style="display:flex;gap:8px;margin-top:8px">
          <button class="primary" type="submit">Login</button>
          <a href="{{ url_for('register') }}"><button type="button">Register</button></a>
        </div>
      </form>
    </div>

  {% elif view == 'register' %}
    <div class="card" style="max-width:420px;margin:0 auto">
      <h2>Register Admin</h2>
      <p class="note">If no users exist, the first registered user becomes admin automatically.</p>
      <form method="post" action="{{ url_for('register') }}">
        <label>Username</label>
        <input name="username" required>
        <label>Password</label>
        <input name="password" type="password" required>
        <div style="display:flex;gap:8px;margin-top:8px">
          <button class="primary" type="submit">Create account</button>
          <a href="{{ url_for('login') }}"><button type="button">Login</button></a>
        </div>
      </form>
    </div>

  {% elif view == 'dashboard' %}
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <h2>Admin Dashboard</h2>
          <div class="small">Approve pending submissions. Edit, delete, and download approved CSV + photos.</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <input id="q" class="searchbox" placeholder="Search approved by name..." />
          <a href="{{ url_for('download_zip') }}"><button class="primary">Download CSV+Photos (approved)</button></a>
        </div>
      </div>

      <hr style="margin:12px 0">

      <div class="two-col">
        <div class="pane">
          <div class="pending-header">
            <h3>Pending Submissions</h3>
            <div class="muted small">New & awaiting approval</div>
          </div>
          <div id="pendingList" style="margin-top:10px"></div>
        </div>

        <div class="pane">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h3>Approved Directory</h3>
            <div class="muted small">Visible to admin only</div>
          </div>
          <div id="approvedList" style="margin-top:10px"></div>
        </div>
      </div>
    </div>
  {% endif %}
</div>

<script>
const ufetch = (url, opts)=>fetch(url, opts).then(r=>r.ok?r.json():r.json().then(e=>{throw e}));

function escapeHtml(s){ if(!s) return ''; return s.toString().replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"\'":'&#39;'}[c])); }

async function loadPending(){
  const pending = await ufetch('/api/admin/pending');
  const wrap = document.getElementById('pendingList');
  wrap.innerHTML = '';
  pending.forEach(a=>{
    const d = document.createElement('div');
    d.className = 'alumni-card';
    const photo = a.photo ? '/uploads/' + encodeURIComponent(a.photo) : 'https://via.placeholder.com/110';
    d.innerHTML = `
      <img src="${photo}" onerror="this.src='https://via.placeholder.com/110'">
      <h4>${escapeHtml(a.fullName)}</h4>
      <div class="small"><b>Phone:</b> ${escapeHtml(a.phone)}</div>
      <div class="small"><b>Area:</b> ${escapeHtml(a.neighborhood)}</div>
      <div class="actions">
        <button class="primary" onclick='approve(${a.id})'>Approve</button>
        <button onclick='edit(${a.id})'>Edit</button>
        <button class="warn" onclick='del(${a.id})'>Delete</button>
      </div>
    `;
    wrap.appendChild(d);
  });
}

async function loadApproved(q=''){
  const approved = await ufetch('/api/admin/approved?q=' + encodeURIComponent(q || ''));
  const wrap = document.getElementById('approvedList');
  wrap.innerHTML = '';
  approved.forEach(a=>{
    const d = document.createElement('div');
    d.className = 'alumni-card';
    const photo = a.photo ? '/uploads/' + encodeURIComponent(a.photo) : 'https://via.placeholder.com/110';
    d.innerHTML = `
      <img src="${photo}" onerror="this.src='https://via.placeholder.com/110'">
      <h4>${escapeHtml(a.fullName)}</h4>
      <div class="small"><b>Phone:</b> ${escapeHtml(a.phone)}</div>
      <div class="small"><b>Area:</b> ${escapeHtml(a.neighborhood)}</div>
      <div class="actions">
        <button onclick='edit(${a.id})'>Edit</button>
        <button class="warn" onclick='del(${a.id})'>Delete</button>
      </div>
    `;
    wrap.appendChild(d);
  });
}

async function approve(id){
  if(!confirm('Approve this submission?')) return;
  const res = await fetch('/api/admin/approve/' + id, {method:'POST'});
  if(res.ok){ loadPending(); loadApproved(); }
  else alert('Failed to approve');
}

async function del(id){
  if(!confirm('Delete this record?')) return;
  const res = await fetch('/api/admin/' + id, {method:'DELETE'});
  if(res.ok){ loadPending(); loadApproved(); }
  else alert('Failed to delete');
}

async function edit(id){
  // fetch record and show native prompt edits (simple)
  const rec = await ufetch('/api/admin/' + id);
  const fullName = prompt('Full name', rec.fullName) || rec.fullName;
  const phone = prompt('Phone', rec.phone) || rec.phone;
  const neighborhood = prompt('Neighborhood', rec.neighborhood) || rec.neighborhood;
  // we won't change photo via prompt; admin can re-upload using separate UI in future
  const form = new FormData();
  form.append('fullName', fullName);
  form.append('phone', phone);
  form.append('neighborhood', neighborhood);
  const res = await fetch('/api/admin/' + id, {method:'PUT', body: form});
  if(res.ok){ loadPending(); loadApproved(); }
  else alert('Failed to update');
}

// wire search
document.getElementById('q')?.addEventListener('input', (e)=>{ const v=e.target.value; setTimeout(()=>loadApproved(v), 200); });

// initial loads for admin dashboard
if (document.getElementById('pendingList')) {
  loadPending();
  loadApproved();
}
</script>
</body>
</html>
"""

# ---------------- Routes: Public submit & thankyou ----------------
@app.route("/submit", methods=("GET", "POST"))
def submit():
    if request.method == "POST":
        fullName = request.form.get("fullName", "").strip()
        phone = request.form.get("phone", "").strip()
        neighborhood = request.form.get("neighborhood", "").strip()
        photo_file = request.files.get("photo")
        photo_filename = ""
        if not fullName or not phone:
            flash("Name and phone required.")
            return redirect(url_for("submit"))

        if photo_file and photo_file.filename:
            if not allowed_file(photo_file.filename):
                flash("File type not allowed.")
                return redirect(url_for("submit"))
            filename = secure_filename(photo_file.filename)
            filename = f"{int(os.times()[4]*1000)}_{filename}"
            dest = UPLOAD_FOLDER / filename
            photo_file.save(str(dest))
            photo_filename = filename

        with get_db_conn() as conn:
            cur = conn.execute(
                "INSERT INTO alumni (fullName, phone, neighborhood, photo, approved) VALUES (?,?,?,?,0)",
                (fullName, phone, neighborhood, photo_filename)
            )
            new_id = cur.lastrowid
        # redirect to thankyou summary
        return redirect(url_for("thankyou", id=new_id))
    return render_template_string(TEMPLATE, view="submit", user=session.get("username"), is_admin=current_user_is_admin())

@app.route("/thankyou")
def thankyou():
    aid = request.args.get("id", type=int)
    if not aid:
        return redirect(url_for("submit"))
    with get_db_conn() as conn:
        row = conn.execute("SELECT * FROM alumni WHERE id=?", (aid,)).fetchone()
        if not row:
            return redirect(url_for("submit"))
        photo_url = url_for('uploaded_file', filename=row["photo"]) if row["photo"] else ''
        return render_template_string(TEMPLATE, view="thankyou",
                                      fullName=row["fullName"], phone=row["phone"],
                                      neighborhood=row["neighborhood"], photo_url=photo_url,
                                      user=session.get("username"), is_admin=current_user_is_admin())

# ---------------- Auth: register/login/logout ----------------
@app.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Username and password required.")
            return redirect(url_for("register"))
        pw_hash = generate_password_hash(password)
        try:
            with get_db_conn() as conn:
                is_admin = 0
                if ENV_ADMIN and username == ENV_ADMIN:
                    is_admin = 1
                else:
                    row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
                    if row and row["c"] == 0:
                        is_admin = 1
                conn.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,?)", (username, pw_hash, is_admin))
            flash("Account created. Please login.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already taken.")
            return redirect(url_for("register"))
    return render_template_string(TEMPLATE, view="register", user=session.get("username"), is_admin=current_user_is_admin())

@app.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db_conn() as conn:
            row = conn.execute("SELECT id,password_hash FROM users WHERE username=?", (username,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            session.permanent = True
            session["user_id"] = row["id"]
            session["username"] = username
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password")
            return redirect(url_for("login"))
    return render_template_string(TEMPLATE, view="login", user=session.get("username"), is_admin=current_user_is_admin())

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- Admin dashboard ----------------
@app.route("/")
@login_required
def dashboard():
    return render_template_string(TEMPLATE, view="dashboard", user=session.get("username"), is_admin=current_user_is_admin())

# ---------------- Upload serving ----------------
@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ---------------- Admin APIs ----------------
@app.route("/api/admin/pending", methods=("GET",))
@admin_required
def api_pending():
    with get_db_conn() as conn:
        rows = conn.execute("SELECT * FROM alumni WHERE approved=0 ORDER BY created_at DESC").fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/admin/approved", methods=("GET",))
@admin_required
def api_approved():
    q = (request.args.get("q") or "").strip()
    with get_db_conn() as conn:
        if q:
            like = f"%{q}%"
            rows = conn.execute("SELECT * FROM alumni WHERE approved=1 AND fullName LIKE ? ORDER BY fullName", (like,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM alumni WHERE approved=1 ORDER BY fullName").fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/admin/approve/<int:aid>", methods=("POST",))
@admin_required
def api_approve(aid):
    with get_db_conn() as conn:
        conn.execute("UPDATE alumni SET approved=1 WHERE id=?", (aid,))
    return jsonify({"status":"approved"})

@app.route("/api/admin/<int:aid>", methods=("GET","PUT","DELETE"))
@admin_required
def api_admin_item(aid):
    if request.method == "GET":
        with get_db_conn() as conn:
            row = conn.execute("SELECT * FROM alumni WHERE id=?", (aid,)).fetchone()
            if not row:
                return jsonify({"message":"Not found"}), 404
            return jsonify(dict(row))
    elif request.method == "DELETE":
        with get_db_conn() as conn:
            row = conn.execute("SELECT photo FROM alumni WHERE id=?", (aid,)).fetchone()
            if row and row["photo"]:
                try:
                    (UPLOAD_FOLDER / row["photo"]).unlink()
                except FileNotFoundError:
                    pass
            conn.execute("DELETE FROM alumni WHERE id=?", (aid,))
        return jsonify({"status":"deleted"})
    else:  # PUT - update (multipart form allowed)
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            fullName = request.form.get("fullName", "").strip()
            phone = request.form.get("phone", "").strip()
            neighborhood = request.form.get("neighborhood", "").strip()
            photo_file = request.files.get("photo")
            photo_filename = None
            if photo_file and photo_file.filename:
                if not allowed_file(photo_file.filename):
                    return jsonify({"message":"File type not allowed"}), 400
                filename = secure_filename(photo_file.filename)
                filename = f"{int(os.times()[4]*1000)}_{filename}"
                dest = UPLOAD_FOLDER / filename
                photo_file.save(str(dest))
                photo_filename = filename
            with get_db_conn() as conn:
                if photo_filename:
                    old = conn.execute("SELECT photo FROM alumni WHERE id=?", (aid,)).fetchone()
                    if old and old["photo"]:
                        try:
                            (UPLOAD_FOLDER / old["photo"]).unlink()
                        except FileNotFoundError:
                            pass
                    conn.execute("UPDATE alumni SET fullName=?, phone=?, neighborhood=?, photo=? WHERE id=?",
                                 (fullName, phone, neighborhood, photo_filename, aid))
                else:
                    conn.execute("UPDATE alumni SET fullName=?, phone=?, neighborhood=? WHERE id=?",
                                 (fullName, phone, neighborhood, aid))
            return jsonify({"status":"updated"})
        else:
            data = request.get_json(force=True)
            fullName = data.get("fullName", "").strip()
            phone = data.get("phone", "").strip()
            neighborhood = data.get("neighborhood", "").strip()
            with get_db_conn() as conn:
                conn.execute("UPDATE alumni SET fullName=?, phone=?, neighborhood=? WHERE id=?",
                             (fullName, phone, neighborhood, aid))
            return jsonify({"status":"updated"})

# ---------------- Download CSV + photos (approved only) ----------------
@app.route("/download")
@admin_required
def download_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # CSV
        csv_buf = io.StringIO()
        w = csv.writer(csv_buf)
        w.writerow(["id","fullName","phone","neighborhood","photo_filename"])
        with get_db_conn() as conn:
            rows = conn.execute("SELECT * FROM alumni WHERE approved=1 ORDER BY fullName").fetchall()
            for r in rows:
                w.writerow([r["id"], r["fullName"], r["phone"], r["neighborhood"], r["photo"] or ""])
        zf.writestr("alumni.csv", csv_buf.getvalue())
        # photos
        for r in rows:
            if r["photo"]:
                p = UPLOAD_FOLDER / r["photo"]
                if p.exists():
                    zf.write(str(p), arcname=f"photos/{r['photo']}")
    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers.set("Content-Type","application/zip")
    resp.headers.set("Content-Disposition","attachment",filename="alumni_approved_export.zip")
    return resp

# ---------------- Run ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

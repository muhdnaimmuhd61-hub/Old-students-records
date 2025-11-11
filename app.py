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

# ---------- Config ----------
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "alumni.db"
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif"}
MAX_CONTENT_LENGTH = 6 * 1024 * 1024  # 6 MB max upload

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me-to-secret")
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.permanent_session_lifetime = timedelta(days=7)

# Optional env var: admin username (overrides default first-user logic)
ENV_ADMIN = os.environ.get("FLASK_ADMIN_USERNAME")  # if set, that username is admin

# ---------- DB helpers ----------
def get_db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_conn() as conn:
        # users table with is_admin flag
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
                photo TEXT
            )
        """)
init_db()

# ---------- Auth helpers ----------
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
            return redirect(url_for("dashboard"))
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

# ---------- HTML Template (single file view) ----------
# (Same template as before but shows/hides edit/add/download based on admin flag passed)
TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Alumni Portal</title>
<style>
  :root{--brown:#d2b48c;--dark:#8b6b43}
  body{font-family:Inter,Arial,Helvetica,sans-serif;margin:0;background:var(--brown);color:#222}
  header{background:var(--dark);color:#fff;padding:1rem;text-align:center}
  .wrap{max-width:1000px;margin:24px auto;padding:12px}
  .card{background:#fff;padding:16px;border-radius:10px;box-shadow:0 6px 18px rgba(0,0,0,0.12)}
  form input, form button, form select {padding:8px;margin:6px 0;border-radius:6px;border:1px solid #ccc;width:100%}
  .grid{display:flex;gap:12px;flex-wrap:wrap}
  .alumni-card{width:200px;background:#fff;border-radius:10px;padding:12px;text-align:center;box-shadow:0 4px 10px rgba(0,0,0,0.08)}
  .alumni-card img{width:100px;height:100px;border-radius:50%;object-fit:cover}
  .actions{margin-top:8px;display:flex;gap:6px;justify-content:center}
  button.primary{background:var(--dark);color:#fff;border:none;padding:8px 12px;border-radius:6px}
  button.warn{background:crimson;color:#fff;border:none;padding:6px 10px;border-radius:6px}
  .topbar{display:flex;gap:12px;align-items:center;justify-content:space-between}
  input[type="file"]{padding:4px}
  .small{font-size:0.9rem;color:#555}
  .right{float:right}
  .searchbox{max-width:360px}
  nav a{color:#fff;margin:0 8px;text-decoration:none}
  .notice{color:crimson}
  @media(max-width:640px){ .grid{justify-content:center} .alumni-card{width:90%} .topbar{flex-direction:column;align-items:flex-start} }
</style>
</head>
<body>
<header>
  <h1>Alumni Portal</h1>
  {% if user %}
    <div class="small">Logged in as <strong>{{user}}</strong>
      {% if is_admin %} • <span style="color:#ffd">Admin</span> {% endif %}
      • <a href="{{ url_for('logout') }}" style="color:#ffd;">Logout</a>
    </div>
  {% endif %}
</header>

<div class="wrap">
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div class="card"><ul>{% for m in messages %}<li style="color:crimson">{{ m }}</li>{% endfor %}</ul></div><br/>
    {% endif %}
  {% endwith %}

  {% if view == 'login' %}
    <div class="card">
      <h2>Login</h2>
      <form method="post" action="{{ url_for('login') }}">
        <label>Username</label>
        <input name="username" required>
        <label>Password</label>
        <input name="password" type="password" required>
        <button class="primary" type="submit">Login</button>
      </form>
      <p class="small">Or <a href="{{ url_for('register') }}">register</a> a new account.</p>
    </div>

  {% elif view == 'register' %}
    <div class="card">
      <h2>Register</h2>
      <form method="post" action="{{ url_for('register') }}">
        <label>Choose username</label>
        <input name="username" required>
        <label>Choose password</label>
        <input name="password" type="password" required>
        <button class="primary" type="submit">Create account</button>
      </form>
      <p class="small">Already have account? <a href="{{ url_for('login') }}">Login</a></p>
    </div>

  {% elif view == 'dashboard' %}
    <div class="card">
      <div class="topbar">
        <div style="flex:1">
          <h2>Dashboard — Tsoffin Dalibai</h2>
          <div class="small">Add, edit, delete alumni (admin only). Photos are stored on server.</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <input id="q" class="searchbox" placeholder="Search by name..." oninput="reload()" />
          {% if is_admin %}
            <button onclick="openAdd()" class="primary">Add Alumni</button>
            <a href="{{ url_for('download_zip') }}"><button class="primary" title="Download CSV + photos">Download ZIP</button></a>
          {% endif %}
        </div>
      </div>

      <hr/>

      <!-- Add/Edit Form (hidden toggle) -->
      <div id="formWrap" style="margin-top:12px;display:none;">
        <form id="alumniForm" enctype="multipart/form-data">
          <input type="hidden" id="al_id" name="id">
          <label>Full name</label>
          <input id="fullName" name="fullName" required>
          <label>Phone</label>
          <input id="phone" name="phone" required>
          <label>Neighborhood</label>
          <input id="neighborhood" name="neighborhood" required>
          <label>Passport photo (png/jpg/jpeg/gif) — leave empty to keep existing</label>
          <input id="photo" name="photo" type="file" accept="image/*">
          <div style="margin-top:8px;display:flex;gap:8px">
            <button class="primary" type="submit">Save</button>
            <button type="button" onclick="closeForm()">Cancel</button>
          </div>
        </form>
      </div>

      <div id="listWrap" style="margin-top:12px;">
        <div id="alumniList" class="grid"></div>
      </div>
    </div>
  {% endif %}
</div>

<script>
const ufetch = (url, opts)=>fetch(url, opts).then(r=>r.ok?r.json():r.json().then(e=>{throw e}));

function showNotice(msg){
  alert(msg);
}

function openAdd(){
  document.getElementById('al_id').value = '';
  document.getElementById('alumniForm').reset();
  document.getElementById('formWrap').style.display = 'block';
  window.scrollTo({top:0,behavior:'smooth'});
}
function closeForm(){
  document.getElementById('formWrap').style.display = 'none';
}

async function reload(){
  const q = encodeURIComponent(document.getElementById('q').value || '');
  const data = await ufetch('/api/alumni?q=' + q);
  const wrap = document.getElementById('alumniList');
  wrap.innerHTML = '';
  data.forEach(a=>{
    const card = document.createElement('div');
    card.className = 'alumni-card';
    const photo = a.photo ? '/uploads/' + encodeURIComponent(a.photo) : 'https://via.placeholder.com/100';
    card.innerHTML = `
      <img src="${photo}" onerror="this.src='https://via.placeholder.com/100'">
      <h3>${escapeHtml(a.fullName)}</h3>
      <div class="small"><b>Phone:</b> ${escapeHtml(a.phone)}</div>
      <div class="small"><b>Area:</b> ${escapeHtml(a.neighborhood)}</div>
      <div class="actions">
        ${ {{ 'true' if is_admin else 'false' }} === 'true' ? `<button onclick='onEdit(${a.id})'>Edit</button><button class="warn" onclick='onDelete(${a.id})'>Delete</button>` : '' }
      </div>
    `;
    wrap.appendChild(card);
  });
}

function escapeHtml(s){ if(!s) return ''; return s.replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

async function onDelete(id){
  if(!confirm('Delete record?')) return;
  const res = await fetch('/api/alumni/' + id, {method:'DELETE'});
  if(res.ok) reload();
  else showNotice('Failed to delete');
}

async function onEdit(id){
  const rec = await ufetch('/api/alumni/' + id);
  document.getElementById('al_id').value = rec.id;
  document.getElementById('fullName').value = rec.fullName;
  document.getElementById('phone').value = rec.phone;
  document.getElementById('neighborhood').value = rec.neighborhood;
  document.getElementById('formWrap').style.display = 'block';
  window.scrollTo({top:0,behavior:'smooth'});
}

document.getElementById && document.getElementById('alumniForm')?.addEventListener('submit', async function(e){
  e.preventDefault();
  const id = document.getElementById('al_id').value;
  const form = document.getElementById('alumniForm');
  const fd = new FormData(form);
  // if file input empty, remove field so backend doesn't overwrite photo
  const fileInput = document.getElementById('photo');
  if (!fileInput.value) fd.delete('photo');

  let url = '/api/alumni';
  let method = 'POST';
  if (id) { url = '/api/alumni/' + id; method = 'PUT'; }
  const res = await fetch(url, {method, body: fd});
  if (res.ok) {
    closeForm();
    reload();
  } else {
    const err = await res.json().catch(()=>({message:'Error'}));
    showNotice(err.message || 'Save failed');
  }
});

// initial load
if (document.getElementById('q')) {
  reload();
  let t;
  document.getElementById('q').addEventListener('input', ()=>{ clearTimeout(t); t=setTimeout(reload, 300); });
}
</script>
</body>
</html>
"""

# ---------- Routes: register/login/logout ----------
@app.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Username and password required")
            return redirect(url_for("register"))
        pw_hash = generate_password_hash(password)
        try:
            # determine if this new user should be admin:
            with get_db_conn() as conn:
                # if env admin username is set and matches, set admin
                is_admin = 0
                if ENV_ADMIN and username == ENV_ADMIN:
                    is_admin = 1
                else:
                    # if no users exist, first user becomes admin
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

# ---------- Dashboard view ----------
@app.route("/")
@login_required
def dashboard():
    return render_template_string(TEMPLATE, view="dashboard", user=session.get("username"), is_admin=current_user_is_admin())

# ---------- serve uploads (images) ----------
@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ---------- API: alumni collection (GET = all/search; POST = create) ----------
@app.route("/api/alumni", methods=("GET", "POST"))
@login_required
def api_alumni_collection():
    if request.method == "GET":
        q = (request.args.get("q") or "").strip()
        with get_db_conn() as conn:
            if q:
                qlike = f"%{q}%"
                rows = conn.execute("SELECT * FROM alumni WHERE fullName LIKE ? ORDER BY id DESC", (qlike,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM alumni ORDER BY id DESC").fetchall()
            results = [dict(r) for r in rows]
        return jsonify(results)

    # POST - create (admin only)
    if not current_user_is_admin():
        return jsonify({"message": "Only admin can add entries"}), 403

    fullName = request.form.get("fullName", "").strip()
    phone = request.form.get("phone", "").strip()
    neighborhood = request.form.get("neighborhood", "").strip()
    photo_file = request.files.get("photo")
    photo_filename = ""

    if photo_file and photo_file.filename:
        if not allowed_file(photo_file.filename):
            return jsonify({"message": "File type not allowed"}), 400
        filename = secure_filename(photo_file.filename)
        filename = f"{int(os.times()[4]*1000)}_{filename}"
        dest = UPLOAD_FOLDER / filename
        photo_file.save(str(dest))
        photo_filename = filename

    with get_db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO alumni (fullName, phone, neighborhood, photo) VALUES (?,?,?,?)",
            (fullName, phone, neighborhood, photo_filename)
        )
        new_id = cur.lastrowid
    return jsonify({"id": new_id, "status": "added"}), 201

# ---------- API: alumni item (GET, PUT, DELETE) ----------
@app.route("/api/alumni/<int:aid>", methods=("GET", "PUT", "DELETE"))
@login_required
def api_alumni_item(aid):
    if request.method == "GET":
        with get_db_conn() as conn:
            row = conn.execute("SELECT * FROM alumni WHERE id=?", (aid,)).fetchone()
            if not row:
                return jsonify({"message": "Not found"}), 404
            return jsonify(dict(row))

    # DELETE (admin only)
    if request.method == "DELETE":
        if not current_user_is_admin():
            return jsonify({"message": "Only admin can delete"}), 403
        with get_db_conn() as conn:
            row = conn.execute("SELECT photo FROM alumni WHERE id=?", (aid,)).fetchone()
            if row and row["photo"]:
                try:
                    (UPLOAD_FOLDER / row["photo"]).unlink()
                except FileNotFoundError:
                    pass
            conn.execute("DELETE FROM alumni WHERE id=?", (aid,))
        return jsonify({"status": "deleted"})

    # PUT (admin only)
    if request.method == "PUT":
        if not current_user_is_admin():
            return jsonify({"message": "Only admin can update"}), 403

        # support multipart form for file upload
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            fullName = request.form.get("fullName", "").strip()
            phone = request.form.get("phone", "").strip()
            neighborhood = request.form.get("neighborhood", "").strip()
            photo_file = request.files.get("photo")
            photo_filename = None
            if photo_file and photo_file.filename:
                if not allowed_file(photo_file.filename):
                    return jsonify({"message": "File type not allowed"}), 400
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
            return jsonify({"status": "updated"})
        else:
            data = request.get_json(force=True)
            fullName = data.get("fullName", "").strip()
            phone = data.get("phone", "").strip()
            neighborhood = data.get("neighborhood", "").strip()
            with get_db_conn() as conn:
                conn.execute("UPDATE alumni SET fullName=?, phone=?, neighborhood=? WHERE id=?",
                             (fullName, phone, neighborhood, aid))
            return jsonify({"status": "updated"})

# ---------- Download ZIP (CSV + photos) - admin only ----------
@app.route("/download")
@admin_required
def download_zip():
    # Create in-memory CSV and ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # write CSV
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["id", "fullName", "phone", "neighborhood", "photo_filename"])
        with get_db_conn() as conn:
            rows = conn.execute("SELECT * FROM alumni ORDER BY id").fetchall()
            for r in rows:
                writer.writerow([r["id"], r["fullName"], r["phone"], r["neighborhood"], r["photo"] or ""])
        zf.writestr("alumni.csv", csv_buf.getvalue())

        # add photos folder
        for r in rows:
            if r["photo"]:
                p = UPLOAD_FOLDER / r["photo"]
                if p.exists():
                    zf.write(str(p), arcname=f"photos/{r['photo']}")

    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers.set("Content-Type", "application/zip")
    resp.headers.set("Content-Disposition", "attachment", filename="alumni_export.zip")
    return resp

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

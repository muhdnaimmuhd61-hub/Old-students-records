from flask import Flask, render_template_string, request, redirect, url_for, session, send_from_directory
import os, sqlite3
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# === App setup ===
app = Flask(__name__)
app.secret_key = 'supersecretkey'
UPLOAD_FOLDER = 'uploads'
# Clean and recreate uploads folder safely
if os.path.exists('uploads') and not os.path.isdir('uploads'):
    os.remove('uploads')  # Delete file blocking the folder name
if not os.path.isdir('uploads'):
    os.makedirs('uploads')
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except FileExistsError:
    pass  # Ignore if folder already exists

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DB_NAME = 'alumni.db'

# === Database setup ===
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fullname TEXT,
                    school TEXT,
                    phone TEXT,
                    photo TEXT
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS admin (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT
                )''')

    # create default admin if not exist
    c.execute("SELECT * FROM admin WHERE username=?", ('admin',))
    if not c.fetchone():
        c.execute("INSERT INTO admin (username, password) VALUES (?, ?)",
                  ('admin', generate_password_hash('1234')))
    conn.commit()
    conn.close()

init_db()

# === HTML Template ===
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>🎓 Alumni Dashboard</title>
    <style>
        body {
            font-family: Arial;
            background-color: #d2b48c;
            margin: 0;
            padding: 0;
        }
        .container {
            width: 90%%;
            margin: 20px auto;
        }
        .header {
            background: #8b5e3c;
            color: white;
            padding: 15px;
            border-radius: 10px;
        }
        .card {
            background: white;
            padding: 15px;
            margin: 10px;
            border-radius: 10px;
            box-shadow: 0 0 5px rgba(0,0,0,0.3);
            display: inline-block;
            width: 220px;
            text-align: center;
            vertical-align: top;
        }
        img {
            width: 100px;
            height: 100px;
            border-radius: 50%%;
            object-fit: cover;
        }
        .search-bar {
            margin: 15px 0;
        }
        input[type="text"], input[type="password"], input[type="file"] {
            padding: 8px;
            border-radius: 5px;
            border: 1px solid #aaa;
            width: 200px;
        }
        button {
            background: #8b5e3c;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 5px;
            cursor: pointer;
        }
        a {
            color: white;
            text-decoration: none;
        }
        .login-section, .register-section {
            margin-top: 30px;
            background: white;
            padding: 20px;
            border-radius: 10px;
        }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🎓 Alumni Dashboard</h1>
        {% if 'username' in session %}
            <p>Welcome, {{ session['username'] }} | <a href="{{ url_for('logout') }}">Logout</a></p>
        {% endif %}
    </div>

    {% if not session.get('username') %}
        <div class="login-section">
            <h2>Login as Admin</h2>
            <form method="POST" action="{{ url_for('login') }}">
                <input type="text" name="username" placeholder="Username" required><br><br>
                <input type="password" name="password" placeholder="Password" required><br><br>
                <button>Login</button>
            </form>
        </div>

        <div class="register-section">
            <h2>Register as Alumni</h2>
            <form method="POST" action="{{ url_for('register') }}" enctype="multipart/form-data">
                <input type="text" name="fullname" placeholder="Full Name" required><br><br>
                <input type="text" name="school" placeholder="School Name" required><br><br>
                <input type="text" name="phone" placeholder="Phone Number" required><br><br>
                <input type="file" name="photo" required><br><br>
                <button type="submit">Register</button>
            </form>
        </div>
    {% else %}
        <div class="search-bar">
            <form method="GET">
                <input type="text" name="q" placeholder="Search name or school..." value="{{ request.args.get('q','') }}">
                <button type="submit">Search</button>
            </form>
        </div>

        <div>
        {% for s in students %}
            {% if not request.args.get('q') or request.args.get('q').lower() in s['fullname'].lower() or request.args.get('q').lower() in s['school'].lower() %}
                <div class="card">
                    <img src="{{ url_for('uploaded_file', filename=s['photo']) }}" alt="photo">
                    <h3>{{ s['fullname'] }}</h3>
                    <p><b>School:</b> {{ s['school'] }}</p>
                    <p><b>Phone:</b> {{ s['phone'] }}</p>
                </div>
            {% endif %}
        {% endfor %}
        </div>
    {% endif %}
</div>
</body>
</html>
"""

# === Routes ===
@app.route('/')
def home():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT fullname, school, phone, photo FROM students")
    rows = c.fetchall()
    conn.close()
    students = [{'fullname': r[0], 'school': r[1], 'phone': r[2], 'photo': r[3]} for r in rows]
    return render_template_string(TEMPLATE, students=students)

@app.route('/register', methods=['POST'])
def register():
    fullname = request.form['fullname']
    school = request.form['school']
    phone = request.form['phone']
    photo = request.files['photo']

    filename = secure_filename(photo.filename)
    photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO students (fullname, school, phone, photo) VALUES (?, ?, ?, ?)",
              (fullname, school, phone, filename))
    conn.commit()
    conn.close()

    return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT password FROM admin WHERE username=?", (username,))
    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user[0], password):
        session['username'] = username
        return redirect(url_for('home'))
    else:
        return "Invalid username or password", 401

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    print("✅ Uploads folder ready. App starting...")
    app.run(host='0.0.0.0', port=10000, debug=True)

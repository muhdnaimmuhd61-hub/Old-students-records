from flask import Flask, request, jsonify, render_template_string
import sqlite3, os

app = Flask(__name__)
DB_PATH = "alumni.db"

# 🔹 Create DB
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
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

# 🔹 Helper
def row_to_dict(row):
    return {"id": row[0], "fullName": row[1], "phone": row[2], "neighborhood": row[3], "photo": row[4]}

# 🔹 HTML Frontend (inline)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Alumni Dashboard</title>
<style>
    body {
        font-family: Arial, sans-serif;
        background-color: #d2b48c;
        margin: 0;
        padding: 0;
    }
    header {
        background-color: #8b6b43;
        color: white;
        text-align: center;
        padding: 1rem;
    }
    .container {
        padding: 20px;
    }
    form {
        background-color: #f9f4ef;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 20px;
        box-shadow: 0 0 10px rgba(0,0,0,0.2);
    }
    input, button {
        padding: 10px;
        margin: 5px;
        border-radius: 5px;
        border: 1px solid #ccc;
    }
    button {
        background-color: #8b6b43;
        color: white;
        cursor: pointer;
    }
    button:hover {
        background-color: #6b4a2b;
    }
    .card {
        background-color: #fff;
        border-radius: 10px;
        padding: 10px;
        margin: 10px;
        display: inline-block;
        text-align: center;
        width: 180px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
    }
    img {
        width: 100px;
        height: 100px;
        border-radius: 50%;
        object-fit: cover;
    }
    .actions button {
        background-color: #8b6b43;
        color: white;
        border: none;
        margin: 2px;
        padding: 5px 10px;
        border-radius: 5px;
    }
    .actions button.delete {
        background-color: crimson;
    }
</style>
</head>
<body>
<header>
    <h1>Alumni Dashboard</h1>
</header>
<div class="container">
    <form id="alumniForm">
        <input type="hidden" id="id">
        <input type="text" id="fullName" placeholder="Full Name" required>
        <input type="text" id="phone" placeholder="Phone Number" required>
        <input type="text" id="neighborhood" placeholder="Neighborhood" required>
        <input type="text" id="photo" placeholder="Photo URL (optional)">
        <button type="submit">Save Alumni</button>
        <button type="button" onclick="clearForm()">Clear</button>
    </form>

    <div id="alumniList"></div>
</div>

<script>
async function loadAlumni() {
    const res = await fetch('/api/alumni');
    const data = await res.json();
    const list = document.getElementById('alumniList');
    list.innerHTML = '';
    data.forEach(a => {
        const div = document.createElement('div');
        div.className = 'card';
        div.innerHTML = `
            <img src="${a.photo || 'https://via.placeholder.com/100'}">
            <h3>${a.fullName}</h3>
            <p><b>Phone:</b> ${a.phone}</p>
            <p><b>Area:</b> ${a.neighborhood}</p>
            <div class="actions">
                <button onclick="editAlumni(${a.id}, '${a.fullName}', '${a.phone}', '${a.neighborhood}', '${a.photo || ''}')">Edit</button>
                <button class="delete" onclick="deleteAlumni(${a.id})">Delete</button>
            </div>
        `;
        list.appendChild(div);
    });
}

async function deleteAlumni(id) {
    if (!confirm('Delete this record?')) return;
    await fetch('/api/alumni/' + id, { method: 'DELETE' });
    loadAlumni();
}

function editAlumni(id, fullName, phone, neighborhood, photo) {
    document.getElementById('id').value = id;
    document.getElementById('fullName').value = fullName;
    document.getElementById('phone').value = phone;
    document.getElementById('neighborhood').value = neighborhood;
    document.getElementById('photo').value = photo;
}

function clearForm() {
    document.getElementById('id').value = '';
    document.getElementById('alumniForm').reset();
}

document.getElementById('alumniForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('id').value;
    const data = {
        fullName: document.getElementById('fullName').value,
        phone: document.getElementById('phone').value,
        neighborhood: document.getElementById('neighborhood').value,
        photo: document.getElementById('photo').value
    };

    if (id) {
        await fetch('/api/alumni/' + id, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
    } else {
        await fetch('/api/alumni', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
    }

    clearForm();
    loadAlumni();
});

loadAlumni();
</script>
</body>
</html>
"""

# 🔹 API Routes
@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/alumni", methods=["GET"])
def get_alumni():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT * FROM alumni ORDER BY id DESC")
        rows = cur.fetchall()
    return jsonify([row_to_dict(r) for r in rows])

@app.route("/api/alumni", methods=["POST"])
def add_alumni():
    data = request.get_json(force=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO alumni (fullName, phone, neighborhood, photo) VALUES (?,?,?,?)",
            (data.get("fullName"), data.get("phone"), data.get("neighborhood"), data.get("photo")),
        )
    return jsonify({"status": "added"})

@app.route("/api/alumni/<int:aid>", methods=["PUT"])
def update_alumni(aid):
    data = request.get_json(force=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE alumni SET fullName=?, phone=?, neighborhood=?, photo=? WHERE id=?",
            (data.get("fullName"), data.get("phone"), data.get("neighborhood"), data.get("photo"), aid),
        )
    return jsonify({"status": "updated"})

@app.route("/api/alumni/<int:aid>", methods=["DELETE"])
def delete_alumni(aid):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM alumni WHERE id=?", (aid,))
    return jsonify({"status": "deleted"})

if __name__ == "__main__":
    app.run(debug=True)

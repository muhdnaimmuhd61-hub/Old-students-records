from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3, os
from pathlib import Path

app = Flask(__name__, static_folder="build", static_url_path="/")
CORS(app)

DB_PATH = "alumni.db"

def init_db():
    """Create database table if not exists"""
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

def row_to_dict(row):
    return {"id": row[0], "fullName": row[1], "phone": row[2], "neighborhood": row[3], "photo": row[4]}

@app.route("/api/alumni", methods=["GET"])
def get_alumni():
    """Return all alumni"""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT id, fullName, phone, neighborhood, photo FROM alumni ORDER BY id DESC")
        rows = cur.fetchall()
    return jsonify([row_to_dict(r) for r in rows])

@app.route("/api/alumni", methods=["POST"])
def add_alumni():
    """Add new alumni"""
    data = request.get_json(force=True)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO alumni (fullName, phone, neighborhood, photo) VALUES (?,?,?,?)",
            (data.get("fullName"), data.get("phone"), data.get("neighborhood"), data.get("photo")),
        )
        new_id = cur.lastrowid
    return jsonify({"id": new_id, "status": "added"}), 201

@app.route("/api/alumni/<int:aid>", methods=["PUT"])
def update_alumni(aid):
    """Update existing alumni"""
    data = request.get_json(force=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE alumni SET fullName=?, phone=?, neighborhood=?, photo=? WHERE id=?",
            (data.get("fullName"), data.get("phone"), data.get("neighborhood"), data.get("photo"), aid),
        )
    return jsonify({"status": "updated"})

@app.route("/api/alumni/<int:aid>", methods=["DELETE"])
def delete_alumni(aid):
    """Delete alumni by ID"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM alumni WHERE id=?", (aid,))
    return jsonify({"status": "deleted"})

# === Serve frontend build (optional) ===
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    """Serve React build if exists"""
    build_dir = Path(app.static_folder)
    if path and (build_dir / path).exists():
        return send_from_directory(app.static_folder, path)
    elif (build_dir / "index.html").exists():
        return send_from_directory(app.static_folder, "index.html")
    else:
        return jsonify({"message": "API running"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

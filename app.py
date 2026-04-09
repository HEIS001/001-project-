from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
import sqlite3, os, base64, math, secrets, string, hashlib, json

# Load .env file automatically
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
DB = "instance/worksight.db"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def gen_code(length=8):
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))

def init_db():
    os.makedirs("instance", exist_ok=True)
    os.makedirs("static/selfies", exist_ok=True)
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            owner_name    TEXT NOT NULL,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            join_code     TEXT UNIQUE NOT NULL,
            building_lat  REAL,
            building_lng  REAL,
            building_name TEXT,
            max_distance  INTEGER DEFAULT 300,
            registered_at TEXT NOT NULL,
            plan          TEXT DEFAULT 'free'
        );
        CREATE TABLE IF NOT EXISTS staff (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id    INTEGER NOT NULL,
            name          TEXT NOT NULL,
            staff_id_code TEXT,
            department    TEXT,
            email         TEXT,
            joined_at     TEXT NOT NULL,
            active        INTEGER DEFAULT 1,
            FOREIGN KEY(company_id) REFERENCES companies(id)
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id    INTEGER NOT NULL,
            staff_fk      INTEGER,
            name          TEXT NOT NULL,
            staff_code    TEXT,
            department    TEXT,
            purpose       TEXT,
            action        TEXT NOT NULL,
            timestamp     TEXT NOT NULL,
            latitude      REAL,
            longitude     REAL,
            gps_ok        INTEGER DEFAULT 0,
            distance_m    REAL,
            selfie_path   TEXT,
            FOREIGN KEY(company_id) REFERENCES companies(id)
        );
        """)

# ── Pages ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/staff")
def staff_portal():
    return render_template("staff.html")

@app.route("/admin")
def admin():
    if "company_id" not in session:
        return redirect(url_for("index"))
    return render_template("admin.html")

# ── Company register ──────────────────────────────────────────────────────────
@app.route("/api/company/register", methods=["POST"])
def company_register():
    d = request.json
    name     = d.get("company_name","").strip()
    owner    = d.get("owner_name","").strip()
    email    = d.get("email","").strip().lower()
    password = d.get("password","")
    bname    = d.get("building_name","").strip()
    lat      = d.get("latitude")
    lng      = d.get("longitude")
    if not all([name, owner, email, password, lat, lng]):
        return jsonify({"error": "All fields and building location are required."}), 400
    join_code = gen_code(8)
    try:
        with get_db() as conn:
            conn.execute("""INSERT INTO companies
                (name,owner_name,email,password_hash,join_code,building_lat,building_lng,building_name,registered_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (name, owner, email, hash_pw(password), join_code, lat, lng, bname,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        return jsonify({"success": True, "join_code": join_code, "company": name})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already registered."}), 409

# ── Company login ─────────────────────────────────────────────────────────────
@app.route("/api/company/login", methods=["POST"])
def company_login():
    d = request.json
    email    = d.get("email","").strip().lower()
    password = d.get("password","")
    with get_db() as conn:
        company = conn.execute(
            "SELECT * FROM companies WHERE email=? AND password_hash=?",
            (email, hash_pw(password))).fetchone()
    if not company:
        return jsonify({"error": "Invalid email or password."}), 401
    session["company_id"]   = company["id"]
    session["company_name"] = company["name"]
    session["owner_name"]   = company["owner_name"]
    return jsonify({"success": True, "company": company["name"], "join_code": company["join_code"]})

@app.route("/api/company/logout", methods=["POST"])
def company_logout():
    session.clear()
    return jsonify({"success": True})

# ── Staff join via code ───────────────────────────────────────────────────────
@app.route("/api/staff/join", methods=["POST"])
def staff_join():
    d         = request.json
    join_code = d.get("join_code","").strip().upper()
    name      = d.get("name","").strip()
    dept      = d.get("department","").strip()
    sid       = d.get("staff_id","").strip()
    email     = d.get("email","").strip()
    if not join_code or not name:
        return jsonify({"error": "Code and name required."}), 400
    with get_db() as conn:
        company = conn.execute("SELECT * FROM companies WHERE join_code=?", (join_code,)).fetchone()
        if not company:
            return jsonify({"error": "Invalid company code. Check with your admin."}), 404
        existing = conn.execute(
            "SELECT id FROM staff WHERE company_id=? AND name=?",
            (company["id"], name)).fetchone()
        if not existing:
            conn.execute("""INSERT INTO staff (company_id,name,staff_id_code,department,email,joined_at)
                VALUES (?,?,?,?,?,?)""",
                (company["id"], name, sid, dept, email, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return jsonify({
        "success": True,
        "message": f"Welcome to {company['name']}!",
        "company": company["name"],
        "company_id": company["id"],
        "building_lat": company["building_lat"],
        "building_lng": company["building_lng"],
        "max_distance": company["max_distance"],
        "building_name": company["building_name"] or "the building"
    })

# ── Attendance register ───────────────────────────────────────────────────────
@app.route("/api/attendance/register", methods=["POST"])
def attendance_register():
    d          = request.json
    company_id = d.get("company_id")
    name       = d.get("name","").strip()
    dept       = d.get("department","").strip()
    purpose    = d.get("purpose","").strip()
    action     = d.get("action","")
    lat        = d.get("latitude")
    lng        = d.get("longitude")
    selfie_b64 = d.get("selfie")
    staff_code = d.get("staff_id","").strip()
    if not company_id or not name or action not in ("in","out"):
        return jsonify({"error": "Missing required fields."}), 400
    with get_db() as conn:
        company = conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "Company not found."}), 404
    gps_ok = False
    distance_m = None
    if lat is not None and lng is not None:
        distance_m = haversine(lat, lng, company["building_lat"], company["building_lng"])
        if distance_m <= company["max_distance"]:
            gps_ok = True
        else:
            return jsonify({"error": f"You are {int(distance_m)}m from {company['building_name'] or 'the building'}. Must be within {company['max_distance']}m."}), 403
    selfie_path = None
    if selfie_b64:
        try:
            img_data = base64.b64decode(selfie_b64.split(",")[-1])
            fname = f"selfie_{company_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}.jpg"
            selfie_path = f"static/selfies/{fname}"
            with open(selfie_path, "wb") as f:
                f.write(img_data)
        except Exception as e:
            return jsonify({"error": f"Selfie save failed: {e}"}), 500
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        staff = conn.execute(
            "SELECT id FROM staff WHERE company_id=? AND name=?", (company_id, name)).fetchone()
        conn.execute("""INSERT INTO attendance
            (company_id,staff_fk,name,staff_code,department,purpose,action,timestamp,
             latitude,longitude,gps_ok,distance_m,selfie_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (company_id, staff["id"] if staff else None, name, staff_code,
             dept, purpose, action, ts, lat, lng, int(gps_ok), distance_m, selfie_path))
    return jsonify({"success": True, "message": f"{name} signed {action} successfully.", "timestamp": ts})

# ── Admin dashboard data ──────────────────────────────────────────────────────
@app.route("/api/admin/dashboard")
def admin_dashboard():
    if "company_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    cid  = session["company_id"]
    date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    with get_db() as conn:
        company      = dict(conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone())
        total_staff  = conn.execute("SELECT COUNT(*) FROM staff WHERE company_id=? AND active=1", (cid,)).fetchone()[0]
        today_recs   = [dict(r) for r in conn.execute(
            "SELECT * FROM attendance WHERE company_id=? AND timestamp LIKE ? ORDER BY timestamp DESC",
            (cid, f"{date}%")).fetchall()]
        in_names     = conn.execute("""
            SELECT DISTINCT name FROM attendance WHERE company_id=? AND timestamp LIKE ? AND action='in'
            AND name NOT IN (SELECT name FROM attendance WHERE company_id=? AND timestamp LIKE ? AND action='out')
        """, (cid, f"{date}%", cid, f"{date}%")).fetchall()
        currently_in = len(in_names)
        weekly = []
        for i in range(6, -1, -1):
            dobj = datetime.now() - timedelta(days=i)
            ds   = dobj.strftime("%Y-%m-%d")
            cnt  = conn.execute(
                "SELECT COUNT(DISTINCT name) FROM attendance WHERE company_id=? AND timestamp LIKE ? AND action='in'",
                (cid, f"{ds}%")).fetchone()[0]
            weekly.append({"date": ds, "label": dobj.strftime("%a"), "count": cnt})
        dept_stats = [dict(r) for r in conn.execute("""
            SELECT department, COUNT(*) as cnt FROM attendance
            WHERE company_id=? AND timestamp LIKE ? AND action='in'
            GROUP BY department ORDER BY cnt DESC LIMIT 8""", (cid, f"{date}%")).fetchall()]
        staff_list = [dict(r) for r in conn.execute(
            "SELECT * FROM staff WHERE company_id=? AND active=1 ORDER BY joined_at DESC", (cid,)).fetchall()]
    return jsonify({
        "company": company, "total_staff": total_staff,
        "currently_in": currently_in,
        "signed_out": len([r for r in today_recs if r["action"]=="out"]),
        "total_today": len(today_recs),
        "records": today_recs, "weekly": weekly,
        "dept_stats": dept_stats, "staff_list": staff_list
    })

@app.route("/api/admin/staff/remove", methods=["POST"])
def remove_staff():
    if "company_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    d = request.json
    with get_db() as conn:
        conn.execute("UPDATE staff SET active=0 WHERE id=? AND company_id=?",
                     (d.get("staff_id"), session["company_id"]))
    return jsonify({"success": True})

@app.route("/api/admin/settings", methods=["POST"])
def update_settings():
    if "company_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    d = request.json
    with get_db() as conn:
        conn.execute("UPDATE companies SET building_name=?, max_distance=? WHERE id=?",
                     (d.get("building_name"), d.get("max_distance", 300), session["company_id"]))
    return jsonify({"success": True})

# ── AI Insight (powered by Groq - free) ──────────────────────────────────────
@app.route("/api/ai/insight", methods=["POST"])
def ai_insight():
    if "company_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    import urllib.request
    import urllib.error
    cid  = session["company_id"]
    date = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        records     = conn.execute(
            "SELECT name, action, timestamp, department FROM attendance WHERE company_id=? AND timestamp LIKE ? ORDER BY timestamp",
            (cid, f"{date}%")).fetchall()
        total_staff = conn.execute("SELECT COUNT(*) FROM staff WHERE company_id=? AND active=1", (cid,)).fetchone()[0]
        company     = conn.execute("SELECT name FROM companies WHERE id=?", (cid,)).fetchone()
    summary = f"Company: {company['name']}. Total registered staff: {total_staff}. Date: {date}. Records today: {len(records)}.\n"
    for r in records:
        summary += f"- {r['name']} ({r['department'] or 'N/A'}) signed {r['action']} at {r['timestamp']}\n"
    prompt = f"""You are WorkSight AI, an intelligent workplace attendance analyst. Analyze the following attendance data and provide:
1. A brief attendance summary
2. Notable patterns or anomalies
3. Productivity insight
4. One actionable recommendation for management

Keep it concise, under 180 words, professional and insightful.

Data:
{summary}"""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return jsonify({"insight": "⚠ GROQ_API_KEY not set. Add it in Render Environment Variables."})
    payload = json.dumps({
        "model": "llama3-70b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
        "temperature": 0.7
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            text = result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        text = f"AI error: {body[:120]}"
    except Exception as e:
        text = f"AI insight temporarily unavailable. ({str(e)[:80]})"
    return jsonify({"insight": text})

if __name__ == "__main__":
    init_db()
    print("\n✦ WorkSight is running → http://localhost:5000\n")
    app.run(debug=True, port=5000)

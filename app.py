import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from ai_matcher import match_lost_item

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lost_found.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hackindia-demo-secret")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        color TEXT,
        location TEXT,
        event_date TEXT,
        image1 TEXT,
        image2 TEXT,
        image3 TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        claimant_id INTEGER NOT NULL,
        lost_location TEXT,
        lost_date TEXT,
        ownership_details TEXT,
        ai_score REAL DEFAULT 0,
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY(item_id) REFERENCES items(id),
        FOREIGN KEY(claimant_id) REFERENCES users(id)
    );
    """)

    # Lightweight schema migration for existing demo databases: add private
    # bill-photo columns to claims without deleting any existing data.
    claim_columns = {row[1] for row in conn.execute("PRAGMA table_info(claims)").fetchall()}
    for column in ("bill1", "bill2", "bill3"):
        if column not in claim_columns:
            conn.execute(f"ALTER TABLE claims ADD COLUMN {column} TEXT")
    conn.commit()

    # Demo admin account
    admin = conn.execute("SELECT id FROM users WHERE email=?", ("admin@lostfound.demo",)).fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO users(name,email,phone,password_hash,is_admin,created_at) VALUES(?,?,?,?,?,?)",
            ("System Admin", "admin@lostfound.demo", "9999999999",
             generate_password_hash("admin123"), 1, datetime.now().isoformat())
        )
    conn.commit()
    conn.close()

# Initialize the database on import so both Flask development mode and
# production servers such as Gunicorn have the required tables.
init_db()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_claim_score(item, lost_location, ownership_details):
    """Combine the public item description with claimant-only evidence.

    The claimant gets a strong score when their private details overlap with
    the found item's description, while location is treated as supporting evidence.
    """
    from ai_matcher import _score_query

    item_text = " ".join([
        item["title"] or "", item["description"] or "", item["category"] or "",
        item["color"] or "", item["location"] or ""
    ])
    evidence = " ".join([item_text, lost_location or "", ownership_details or ""])
    score, _ = _score_query(evidence, item)

    # Extra verification signals: claimant should know a detail already present
    # in the original listing.
    private_words = set((ownership_details or "").lower().split())
    public_words = set(item_text.lower().split())
    shared = private_words & public_words
    if shared:
        score += min(18, len(shared) * 4)

    if lost_location and item["location"]:
        lost_loc = lost_location.lower()
        found_loc = item["location"].lower()
        if any(word in found_loc for word in lost_loc.split() if len(word) > 3):
            score += 8

    return round(min(99.9, score), 1)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form["phone"].strip()
        password = request.form["password"]

        if not name or not email or not phone or len(password) < 6:
            flash("Please fill all fields. Password must be at least 6 characters.", "danger")
            return render_template("register.html")

        conn = db()
        try:
            conn.execute(
                "INSERT INTO users(name,email,phone,password_hash,created_at) VALUES(?,?,?,?,?)",
                (name, email, phone, generate_password_hash(password), datetime.now().isoformat())
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash("An account with that email already exists.", "danger")
            return render_template("register.html")
        conn.close()

        flash("Account created. For this hackathon MVP, OTP verification is simulated after login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["pending_user_id"] = user["id"]
            session["otp"] = "123456"  # DEMO ONLY
            return redirect(url_for("verify_otp"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")

@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if "pending_user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        entered = request.form["otp"].strip()
        if entered == session.get("otp"):
            conn = db()
            user = conn.execute("SELECT * FROM users WHERE id=?", (session["pending_user_id"],)).fetchone()
            conn.close()

            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["is_admin"] = bool(user["is_admin"])
            flash("OTP verified successfully.", "success")
            return redirect(url_for("admin" if user["is_admin"] else "dashboard"))

        flash("Incorrect OTP. Demo OTP is 123456.", "danger")

    return render_template("verify_otp.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    conn = db()
    user_items = conn.execute(
        "SELECT * FROM items WHERE user_id=? ORDER BY id DESC", (session["user_id"],)
    ).fetchall()
    my_claims = conn.execute("""
        SELECT claims.*, items.title, items.image1,
               finder.name AS finder_name, finder.email AS finder_email, finder.phone AS finder_phone
        FROM claims
        JOIN items ON claims.item_id=items.id
        JOIN users finder ON items.user_id=finder.id
        WHERE claims.claimant_id=? ORDER BY claims.id DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("dashboard.html", items=user_items, claims=my_claims)

@app.route("/found", methods=["GET", "POST"])
@login_required
def found():
    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form["description"].strip()
        category = request.form["category"].strip()
        color = request.form.get("color", "").strip()
        location = request.form.get("location", "").strip()
        event_date = request.form.get("event_date", "")

        if not title or not description or not category:
            flash("Title, description and category are required.", "danger")
            return render_template("found.html")

        image_paths = []
        for field in ("image1", "image2", "image3"):
            file = request.files.get(field)
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(
                    f"{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{file.filename}"
                )
                file.save(os.path.join(UPLOAD_DIR, filename))
                image_paths.append(f"uploads/{filename}")
            else:
                image_paths.append(None)

        conn = db()
        conn.execute("""
            INSERT INTO items
            (user_id,item_type,title,description,category,color,location,event_date,image1,image2,image3,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            session["user_id"], "found", title, description, category, color,
            location, event_date, image_paths[0], image_paths[1], image_paths[2],
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()

        flash("Found item published successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("found.html")

@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    results = []
    query = ""

    if request.method == "POST":
        query = request.form["query"].strip()
        conn = db()
        items = conn.execute("""
            SELECT items.*, users.name AS finder_name
            FROM items JOIN users ON items.user_id=users.id
            WHERE items.status='active' AND items.item_type='found'
            ORDER BY items.id DESC
        """).fetchall()
        conn.close()

        results = match_lost_item(query, items)

    return render_template("search.html", results=results, query=query)

@app.route("/item/<int:item_id>")
@login_required
def item_detail(item_id):
    conn = db()
    item = conn.execute("""
        SELECT items.*, users.name AS finder_name
        FROM items JOIN users ON items.user_id=users.id
        WHERE items.id=?
    """, (item_id,)).fetchone()
    conn.close()

    if not item:
        flash("Item not found.", "danger")
        return redirect(url_for("search"))

    return render_template("item_detail.html", item=item)

@app.route("/claim/<int:item_id>", methods=["GET", "POST"])
@login_required
def claim(item_id):
    conn = db()
    item = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()

    if not item:
        flash("Item not found.", "danger")
        return redirect(url_for("search"))

    if item["user_id"] == session["user_id"]:
        flash("You cannot claim your own found item.", "warning")
        return redirect(url_for("item_detail", item_id=item_id))

    if request.method == "POST":
        lost_location = request.form["lost_location"].strip()
        lost_date = request.form["lost_date"]
        ownership_details = request.form["ownership_details"].strip()

        bill_paths = []
        for field in ("bill1", "bill2", "bill3"):
            file = request.files.get(field)
            if file and file.filename:
                if not allowed_file(file.filename):
                    flash("Bill photos must be PNG, JPG, JPEG or WEBP images.", "danger")
                    return render_template("claim.html", item=item)
                filename = secure_filename(
                    f"claim_{session['user_id']}_{item_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{file.filename}"
                )
                file.save(os.path.join(UPLOAD_DIR, filename))
                bill_paths.append(f"uploads/{filename}")
            else:
                bill_paths.append(None)

        # A bill photo is now required as an additional ownership signal.
        if not any(bill_paths):
            flash("Please upload at least one photo of the original bill or purchase receipt.", "danger")
            return render_template("claim.html", item=item)

        # AI score used for admin prioritization.
        score = calculate_claim_score(item, lost_location, ownership_details)

        conn = db()
        conn.execute("""
            INSERT INTO claims
            (item_id,claimant_id,lost_location,lost_date,ownership_details,bill1,bill2,bill3,ai_score,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (
            item_id, session["user_id"], lost_location, lost_date,
            ownership_details, bill_paths[0], bill_paths[1], bill_paths[2],
            score, datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()

        flash("Claim submitted. An admin will verify the ownership before contact details are released.", "success")
        return redirect(url_for("dashboard"))

    return render_template("claim.html", item=item)

@app.route("/admin/claim-proof/<path:filename>")
@login_required
@admin_required
def admin_claim_proof(filename):
    """Serve uploaded bill/receipt images only to authenticated admins."""
    from flask import send_from_directory
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/admin")
@login_required
@admin_required
def admin():
    conn = db()
    raw_claims = conn.execute("""
        SELECT claims.*, items.title, items.description, items.category,
               items.color, items.location, items.image1,
               claimant.name AS claimant_name, claimant.email AS claimant_email,
               claimant.phone AS claimant_phone,
               finder.name AS finder_name, finder.email AS finder_email,
               finder.phone AS finder_phone,
               claims.bill1, claims.bill2, claims.bill3
        FROM claims
        JOIN items ON claims.item_id=items.id
        JOIN users claimant ON claims.claimant_id=claimant.id
        JOIN users finder ON items.user_id=finder.id
        ORDER BY CASE WHEN claims.status='pending' THEN 0 ELSE 1 END, claims.id DESC
    """).fetchall()

    # Recalculate the displayed score so older demo claims also benefit from
    # the improved matching logic after a code update.
    claims = []
    for row in raw_claims:
        data = dict(row)
        data["ai_score"] = calculate_claim_score(
            row, row["lost_location"], row["ownership_details"]
        )
        claims.append(data)
    conn.close()
    return render_template("admin.html", claims=claims)

@app.route("/admin/claim/<int:claim_id>/<action>", methods=["POST"])
@login_required
@admin_required
def admin_claim_action(claim_id, action):
    if action not in {"approve", "reject"}:
        return jsonify({"error": "invalid action"}), 400

    status = "approved" if action == "approve" else "rejected"
    conn = db()
    conn.execute("UPDATE claims SET status=? WHERE id=?", (status, claim_id))
    if status == "approved":
        conn.execute("""
            UPDATE items SET status='claimed'
            WHERE id=(SELECT item_id FROM claims WHERE id=?)
        """, (claim_id,))
    conn.commit()
    conn.close()
    flash(
        "Claim approved — verified return coordination is now available to the claimant."
        if status == "approved" else "Claim rejected.",
        "success" if status == "approved" else "warning"
    )
    return redirect(url_for("admin"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)

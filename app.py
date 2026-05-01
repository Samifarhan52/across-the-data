import os
import sqlite3
from datetime import datetime, date
from functools import wraps
from urllib.parse import quote_plus
from werkzeug.utils import secure_filename
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, g, abort, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

APP_NAME = os.getenv("APP_NAME", "ACROSS THE DATA")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "farhanulla.shaik@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@12345")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "917676808068")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "farhanulla.shaik@gmail.com")
UPI_ID = os.getenv("UPI_ID", "farhanulla.shaik@upi")
BASE_DIR = os.path.dirname(__file__)
DATABASE = os.path.join(BASE_DIR, "across_the_data.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "demo_files")
ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv", "pdf", "txt"}

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-before-deployment")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- DB ----------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def query(sql, args=(), one=False, commit=False):
    db = get_db()
    cur = db.execute(sql, args)
    if commit:
        db.commit()
        return cur.lastrowid
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows

def table_columns(cursor, table_name):
    return [r[1] for r in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()]

def add_column_if_missing(cursor, table_name, column_name, column_sql):
    if column_name not in table_columns(cursor, table_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")

def init_db():
    db = sqlite3.connect(DATABASE)
    c = db.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        company TEXT,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'customer',
        discount INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        type TEXT NOT NULL,
        description TEXT,
        price INTEGER DEFAULT 0,
        discount INTEGER DEFAULT 0,
        demo_data TEXT,
        views INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category_id INTEGER,
        name TEXT,
        phone TEXT,
        amount INTEGER,
        transaction_id TEXT,
        status TEXT DEFAULT 'Pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        company TEXT,
        message TEXT NOT NULL,
        image_url TEXT,
        status TEXT DEFAULT 'New',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    CREATE TABLE IF NOT EXISTS ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        body TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT,
        discount INTEGER DEFAULT 0,
        deadline TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Safe migrations for older database copies
    add_column_if_missing(c, "categories", "demo_link", "demo_link TEXT")
    add_column_if_missing(c, "categories", "demo_file", "demo_file TEXT")
    add_column_if_missing(c, "categories", "offer_deadline", "offer_deadline TEXT")
    add_column_if_missing(c, "users", "address", "address TEXT")
    add_column_if_missing(c, "users", "city", "city TEXT")
    add_column_if_missing(c, "users", "state", "state TEXT")
    add_column_if_missing(c, "users", "pincode", "pincode TEXT")
    add_column_if_missing(c, "users", "profile_notes", "profile_notes TEXT")
    add_column_if_missing(c, "users", "preferred_data", "preferred_data TEXT")
    add_column_if_missing(c, "users", "email_notifications", "email_notifications INTEGER DEFAULT 1")
    add_column_if_missing(c, "users", "whatsapp_updates", "whatsapp_updates INTEGER DEFAULT 1")

    admin = c.execute("SELECT id FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone()
    if not admin:
        c.execute("INSERT INTO users(name,email,phone,password,role,discount) VALUES(?,?,?,?,?,?)",
                  ("Admin", ADMIN_EMAIL, "7676808068", generate_password_hash(ADMIN_PASSWORD), "admin", 20))

    defaults = [
        ("Telangana", "telangana", "State", "Student and admission interest data from Telangana region.", 4999, 8, "Hyderabad | Intermediate | Interested in BBA/MBA | Demo only"),
        ("Andhra Pradesh", "andhra-pradesh", "State", "Verified enquiry data from Andhra Pradesh.", 4999, 8, "Vijayawada | Degree | Interested in MCA | Demo only"),
        ("Bangalore", "bangalore", "City", "Premium Bangalore education leads for colleges and consultancies.", 6999, 10, "Bangalore | CBSE | Interested in UG admissions | Demo only"),
        ("Pune", "pune", "City", "Student data for Pune education market.", 5999, 5, "Pune | ICSE | Interested in engineering | Demo only"),
        ("Chennai", "chennai", "City", "Chennai student lead category.", 5999, 5, "Chennai | State Board | Interested in arts/science | Demo only"),
        ("Mumbai", "mumbai", "City", "Mumbai admission and counselling lead category.", 7999, 10, "Mumbai | HSC | Interested in finance/MBA | Demo only"),
        ("Delhi", "delhi", "City", "Delhi NCR student enquiry leads.", 7999, 10, "Delhi | CBSE | Interested in abroad studies | Demo only"),
        ("Gujarat", "gujarat", "State", "Gujarat education lead data.", 5999, 6, "Ahmedabad | Commerce | Interested in BBA | Demo only"),
        ("Maharashtra", "maharashtra", "State", "Maharashtra region data category.", 6999, 8, "Nagpur | Science | Interested in medical | Demo only"),
        ("KSSEB", "ksseb", "Board", "Karnataka School Examination and Assessment Board related data.", 5499, 7, "Karnataka | SSLC/PUC | Demo only"),
        ("CBSE", "cbse", "Board", "Central Board of Secondary Education student data.", 7499, 10, "CBSE | Class 12 | Interested in UG admissions | Demo only"),
        ("ICSE", "icse", "Board", "Indian Certificate of Secondary Education category.", 7499, 10, "ICSE | Class 10/12 | Demo only"),
        ("NIOS", "nios", "Board", "National Institute of Open Schooling category.", 6499, 9, "NIOS | Open schooling | Demo only"),
        ("IB", "ib", "Board", "International Baccalaureate premium category.", 9999, 12, "IB | International curriculum | Demo only"),
        ("IGCSE", "igcse", "Board", "International General Certificate of Secondary Education category.", 9999, 12, "IGCSE | Global curriculum | Demo only"),
        ("Other States", "other-states", "State", "Custom data requirement for other Indian states.", 3999, 5, "Custom region | Demo only"),
    ]
    for item in defaults:
        exists = c.execute("SELECT id FROM categories WHERE slug=?", (item[1],)).fetchone()
        if not exists:
            c.execute("INSERT INTO categories(name,slug,type,description,price,discount,demo_data) VALUES(?,?,?,?,?,?,?)", item)

    default_settings = {
        "brand_tagline": "Premium segmented education data for counsellors, agents and admission teams.",
        "logo_text": "",
        "app_name": APP_NAME,
        "support_email": SUPPORT_EMAIL,
        "whatsapp_number": WHATSAPP_NUMBER,
        "upi_id": UPI_ID,
        "business_address": "Bangalore, Karnataka",
        "footer_note": "Premium segmented education data marketplace for counsellors, agents and admission teams.",
        "popup_title": "Login to unlock member pricing",
        "popup_body": "Create your account to receive category discounts, faster support, saved enquiries and premium access benefits."
    }
    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))

    c.execute("INSERT OR IGNORE INTO ads(id,title,body,active) VALUES(1,'Verified Data. Better Conversions.','Login to unlock special discounts and faster access to premium categories.',1)")
    c.execute("INSERT OR IGNORE INTO offers(id,title,body,discount,deadline,active) VALUES(1,'Launch Member Offer','Signup and login to unlock special member pricing on selected education data categories.',5,'2026-12-31',1)")
    db.commit()
    db.close()

with app.app_context():
    init_db()

# ---------------- Helpers ----------------
def current_user():
    uid = session.get("user_id")
    if uid:
        return query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    return None

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user["role"] != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper

def settings_dict():
    return {r["key"]: r["value"] for r in query("SELECT * FROM settings")}

def get_setting(key, default=""):
    row = query("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return row["value"] if row and row["value"] is not None else default

def app_display_name():
    return get_setting("app_name", APP_NAME) or APP_NAME

def whatsapp_number():
    return get_setting("whatsapp_number", WHATSAPP_NUMBER) or WHATSAPP_NUMBER

def support_email_setting():
    return get_setting("support_email", SUPPORT_EMAIL) or SUPPORT_EMAIL

def upi_id_setting():
    return get_setting("upi_id", UPI_ID) or UPI_ID

def active_offer():
    today = date.today().isoformat()
    return query("SELECT * FROM offers WHERE active=1 AND (deadline IS NULL OR deadline='' OR deadline>=?) ORDER BY id DESC LIMIT 1", (today,), one=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_demo_file(file_obj):
    if not file_obj or not file_obj.filename:
        return None
    if not allowed_file(file_obj.filename):
        flash("Only Excel, CSV, PDF and TXT demo files are allowed.")
        return None
    safe = secure_filename(file_obj.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{timestamp}_{safe}"
    file_obj.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename

@app.context_processor
def inject_globals():
    s = settings_dict()
    return dict(
        app_name=s.get("app_name") or APP_NAME,
        user=current_user(),
        settings=s,
        whatsapp=s.get("whatsapp_number") or WHATSAPP_NUMBER,
        support_email=s.get("support_email") or SUPPORT_EMAIL,
        active_offer=active_offer()
    )

# ---------------- UI Template ----------------
BASE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title or app_name }}</title>
<style>
:root{--bg:#090b10;--panel:#121722;--panel2:#171f2d;--text:#eef3ff;--muted:#9fb0c8;--gold:#d7b56d;--blue:#4ca3ff;--green:#38d39f;--danger:#ff6b6b;--line:rgba(255,255,255,.11)}
*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial;background:radial-gradient(circle at top left,#182844 0,#090b10 35%,#07080c 100%);color:var(--text)}
a{color:inherit;text-decoration:none}.wrap{max-width:1180px;margin:auto;padding:0 20px}.nav{position:sticky;top:0;z-index:50;background:rgba(9,11,16,.84);backdrop-filter:blur(18px);border-bottom:1px solid var(--line)}.navin{display:flex;align-items:center;justify-content:space-between;padding:14px 0}.brand{display:flex;gap:12px;align-items:center;font-weight:900;letter-spacing:.5px}.logo{width:42px;height:42px;border:1px solid rgba(215,181,109,.5);border-radius:14px;display:grid;place-items:center;background:linear-gradient(135deg,#131a27,#27344d);box-shadow:0 0 30px rgba(215,181,109,.18)}.links{display:flex;gap:16px;align-items:center}.links a{color:var(--muted);font-size:14px}.links a:hover,.active{color:var(--gold)!important}.btn{border:0;border-radius:14px;padding:11px 16px;font-weight:800;cursor:pointer;background:linear-gradient(135deg,var(--gold),#fff0b6);color:#111;box-shadow:0 10px 30px rgba(215,181,109,.18);display:inline-block}.btn.secondary{background:#182235;color:var(--text);border:1px solid var(--line);box-shadow:none}.btn.danger{background:var(--danger);color:white}.hero{padding:72px 0 46px;position:relative;overflow:hidden}.hero:before{content:"";position:absolute;inset:auto -10% -30% auto;width:520px;height:520px;background:radial-gradient(circle,rgba(76,163,255,.18),transparent 70%);filter:blur(4px)}.grid{display:grid;grid-template-columns:1.15fr .85fr;gap:26px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{background:linear-gradient(180deg,rgba(255,255,255,.07),rgba(255,255,255,.035));border:1px solid var(--line);border-radius:26px;padding:24px;box-shadow:0 24px 80px rgba(0,0,0,.3)}h1{font-size:54px;line-height:1.02;margin:0 0 16px}h2{font-size:32px;margin:0 0 16px}h3{margin:0 0 10px}.muted{color:var(--muted);line-height:1.65}.pill{display:inline-flex;padding:8px 12px;border-radius:999px;border:1px solid rgba(215,181,109,.35);color:#ffe5a6;background:rgba(215,181,109,.08);font-size:13px;margin-bottom:16px}.offer{border-color:rgba(56,211,159,.35);background:rgba(56,211,159,.08);color:#b9ffe8}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:22px}.stat{padding:16px;border:1px solid var(--line);border-radius:18px;background:rgba(255,255,255,.04)}.stat b{font-size:24px}.searchbox{display:flex;gap:10px;margin:18px 0}.input,select,textarea{width:100%;padding:13px 14px;border-radius:14px;background:#0d1320;border:1px solid var(--line);color:var(--text);outline:none}.input:focus,select:focus,textarea:focus{border-color:var(--gold)}label{font-size:14px;color:var(--muted)}.suggest{display:flex;flex-wrap:wrap;gap:10px}.chip{padding:9px 12px;border-radius:999px;background:#111928;border:1px solid var(--line);color:var(--muted)}.chip:hover{color:var(--gold);border-color:rgba(215,181,109,.55);transform:translateY(-2px)}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:24px 0}.cat{transition:.25s}.cat:hover{transform:translateY(-7px);border-color:rgba(215,181,109,.55)}.price{font-size:24px;font-weight:900;color:#fff}.strike{text-decoration:line-through;color:#73839b;font-size:14px}.tag{font-size:12px;color:#a9c7ff;background:rgba(76,163,255,.1);border:1px solid rgba(76,163,255,.22);padding:6px 10px;border-radius:999px}.section{padding:46px 0}.footer{border-top:1px solid var(--line);padding:30px 0;color:var(--muted);background:#07090d}.flash{padding:12px 14px;border-radius:14px;background:#17253d;border:1px solid var(--line);margin:14px 0}.table{width:100%;border-collapse:collapse}.table th,.table td{border-bottom:1px solid var(--line);padding:12px;text-align:left;font-size:14px;vertical-align:top}.admin{display:grid;grid-template-columns:250px 1fr;gap:22px}.side{position:sticky;top:82px;height:max-content}.side a{display:block;padding:12px 14px;margin:6px 0;border-radius:14px;color:var(--muted)}.side a:hover{background:#151d2b;color:var(--gold)}.popup{position:fixed;inset:0;background:rgba(0,0,0,.62);z-index:100;display:none;align-items:center;justify-content:center;padding:20px}.popup.show{display:flex}.modal{max-width:520px;background:linear-gradient(145deg,#111827,#0b1019);border:1px solid rgba(215,181,109,.35);border-radius:28px;padding:28px;box-shadow:0 30px 120px rgba(0,0,0,.65)}.reveal{animation:rise .75s ease both}@keyframes rise{from{opacity:0;transform:translateY(22px) scale(.98)}to{opacity:1;transform:none}}.entry{position:fixed;inset:0;background:#07080c;z-index:200;display:grid;place-items:center;animation:hide 1.6s ease forwards}.entry div{font-size:28px;font-weight:950;letter-spacing:1px;background:linear-gradient(90deg,#fff,var(--gold),#78b7ff);-webkit-background-clip:text;color:transparent}@keyframes hide{0%,65%{opacity:1}100%{opacity:0;visibility:hidden}}@media(max-width:850px){.grid,.grid3,.admin{grid-template-columns:1fr}.cards{grid-template-columns:1fr}.links{display:none}h1{font-size:38px}.stats{grid-template-columns:1fr}.navin{gap:12px}.table{display:block;overflow:auto}}
</style>
</head>
<body>
<div class="entry"><div>{{ app_name }}</div></div>
<nav class="nav"><div class="wrap navin"><a class="brand" href="{{ url_for('home') }}"><span class="logo">{{ (settings.get('logo_text') or 'AD')[:2] }}</span><span>{{ app_name }}</span></a><div class="links"><a href="{{ url_for('home') }}">Home</a><a href="{{ url_for('categories') }}">Categories</a><a href="{{ url_for('pricing') }}">Pricing</a><a href="{{ url_for('support') }}">Support</a>{% if user and user.role=='admin' %}<a href="{{ url_for('admin') }}">Admin</a>{% endif %}{% if user %}<a href="{{ url_for('profile') }}">Profile</a><a href="{{ url_for('logout') }}">Logout</a>{% else %}<a href="{{ url_for('login') }}">Login</a><a class="btn" href="{{ url_for('signup') }}">Signup</a>{% endif %}</div></div></nav>
<div class="wrap">{% for m in get_flashed_messages() %}<div class="flash">{{m}}</div>{% endfor %}</div>
{{ body|safe }}
<footer class="footer"><div class="wrap"><b>{{ app_name }}</b><p>{{ settings.get('footer_note') }}</p><p>WhatsApp: +{{ whatsapp }} | Email: {{ support_email }}</p></div></footer>
{% if not user %}<div id="loginPop" class="popup"><div class="modal reveal"><span class="pill">Exclusive Access</span><h2>{{ settings.get('popup_title') }}</h2><p class="muted">{{ settings.get('popup_body') }}</p>{% if active_offer %}<p class="pill offer">{{ active_offer.discount }}% offer valid till {{ active_offer.deadline }}</p>{% endif %}<div style="display:flex;gap:10px;flex-wrap:wrap"><a class="btn" href="{{ url_for('signup') }}">Create Account</a><a class="btn secondary" href="{{ url_for('login') }}">Login</a><button class="btn secondary" onclick="closePop()">Continue Browsing</button></div></div></div><script>setTimeout(()=>{if(!localStorage.seenAcrossPop){document.getElementById('loginPop').classList.add('show');localStorage.seenAcrossPop='1'}},1900);function closePop(){document.getElementById('loginPop').classList.remove('show')}</script>{% endif %}
</body></html>
"""

def page(body, title=None):
    return render_template_string(BASE, body=body, title=title)

# ---------------- Routes ----------------
@app.route("/")
def home():
    cats = query("SELECT * FROM categories WHERE active=1 ORDER BY views DESC, id ASC LIMIT 9")
    ad = query("SELECT * FROM ads WHERE active=1 ORDER BY id DESC LIMIT 1", one=True)
    offer = active_offer()
    body = render_template_string(r"""
<section class="hero"><div class="wrap grid"><div class="reveal"><span class="pill">Verified • Segmented • Affordable</span><h1>Education data made simple for serious counsellors.</h1><p class="muted">{{ settings.get('brand_tagline') }}</p>{% if offer %}<div class="pill offer">{{ offer.title }} — {{ offer.discount }}% discount valid till {{ offer.deadline }}</div>{% endif %}<div class="searchbox"><form action="{{ url_for('categories') }}" style="display:flex;gap:10px;width:100%"><input class="input" name="q" placeholder="Search states, boards, cities, CBSE, ICSE, NIOS..."><button class="btn">Search</button></form></div><div class="suggest">{% for c in cats[:8] %}<a class="chip" href="{{ url_for('category_detail', slug=c.slug) }}">{{ c.name }}</a>{% endfor %}</div><div class="stats"><div class="stat"><b>{{ cats|length }}+</b><br><span class="muted">Live categories</span></div><div class="stat"><b>Demo</b><br><span class="muted">Excel preview</span></div><div class="stat"><b>UPI</b><br><span class="muted">Quick payment</span></div></div></div><div class="card reveal"><span class="pill">{{ ad.title if ad else 'Premium Access' }}</span><h2>{{ ad.body if ad else 'Login to unlock discounts and priority support.' }}</h2><p class="muted">Customers can browse demo data without login. Logged-in customers receive special discounts and can track their payment requests.</p><div style="display:flex;gap:10px;flex-wrap:wrap"><a class="btn" href="{{ url_for('categories') }}">Explore Categories</a><a class="btn secondary" href="{{ url_for('signup') }}">Signup for Discounts</a></div></div></div></section>
<section class="section"><div class="wrap"><h2>Most viewed categories</h2><div class="cards">{% for c in cats %}<div class="card cat"><span class="tag">{{ c.type }}</span><h3>{{ c.name }}</h3><p class="muted">{{ c.description }}</p><p><span class="price">₹{{ c.price }}</span> <span class="muted">starting</span></p>{% if c.offer_deadline %}<p class="pill offer">Offer valid till {{ c.offer_deadline }}</p>{% endif %}<a class="btn secondary" href="{{ url_for('category_detail', slug=c.slug) }}">View Demo</a></div>{% endfor %}</div></div></section>
""", cats=cats, ad=ad, offer=offer)
    return page(body, "Home")

@app.route("/categories")
def categories():
    q = request.args.get("q", "").strip()
    if q:
        cats = query("SELECT * FROM categories WHERE active=1 AND (name LIKE ? OR type LIKE ? OR description LIKE ?) ORDER BY views DESC", (f"%{q}%", f"%{q}%", f"%{q}%"))
    else:
        cats = query("SELECT * FROM categories WHERE active=1 ORDER BY type,name")
    suggestions = query("SELECT name,slug FROM categories WHERE active=1 ORDER BY views DESC,name LIMIT 16")
    body = render_template_string(r"""
<section class="section"><div class="wrap"><h2>Browse Data Categories</h2><p class="muted">Search by state, city, board or requirement. Suggestions are visible even before searching.</p><form class="searchbox"><input class="input" name="q" value="{{ request.args.get('q','') }}" placeholder="Try CBSE, Bangalore, Telangana, IB..."><button class="btn">Search</button></form><div class="suggest">{% for s in suggestions %}<a class="chip" href="{{ url_for('category_detail', slug=s.slug) }}">{{ s.name }}</a>{% endfor %}</div><div class="cards">{% for c in cats %}<div class="card cat"><span class="tag">{{ c.type }}</span><h3>{{ c.name }}</h3><p class="muted">{{ c.description }}</p><p><span class="price">₹{{ c.price }}</span>{% if user %}<br><span class="muted">Login discount: {{ c.discount + user.discount }}%</span>{% else %}<br><span class="muted">Signup/Login to unlock discount</span>{% endif %}</p>{% if c.offer_deadline %}<p class="pill offer">Deadline: {{ c.offer_deadline }}</p>{% endif %}<a class="btn" href="{{ url_for('category_detail', slug=c.slug) }}">View Details</a></div>{% else %}<p>No categories found.</p>{% endfor %}</div></div></section>
""", cats=cats, suggestions=suggestions)
    return page(body, "Categories")

@app.route("/category/<slug>")
def category_detail(slug):
    c = query("SELECT * FROM categories WHERE slug=? AND active=1", (slug,), one=True)
    if not c: abort(404)
    query("UPDATE categories SET views=views+1 WHERE id=?", (c["id"],), commit=True)
    u = current_user()
    offer = active_offer()
    extra_offer_discount = offer["discount"] if offer else 0
    disc = (c["discount"] + (u["discount"] if u else 0) + (extra_offer_discount if u else 0)) if u else 0
    final = max(0, int(c["price"] - (c["price"] * disc / 100)))
    body = render_template_string(r"""
<section class="section"><div class="wrap grid"><div class="card"><span class="tag">{{ c.type }}</span><h1>{{ c.name }}</h1><p class="muted">{{ c.description }}</p><h3>Demo Data Preview</h3><div class="card" style="background:#0c121d"><p>{{ c.demo_data }}</p>{% if c.demo_file %}<p><a class="btn secondary" href="{{ url_for('download_demo', filename=c.demo_file) }}">Download Demo File</a></p>{% endif %}{% if c.demo_link %}<p><a class="btn secondary" target="_blank" href="{{ c.demo_link }}">Open Demo Link</a></p>{% endif %}<p class="muted">Clients can view and download demo data. Full verified data is shared after payment confirmation.</p></div></div><div class="card"><h2>Pricing</h2>{% if user %}<p><span class="strike">₹{{ c.price }}</span></p><p class="price">₹{{ final }}</p><p class="muted">Your total discount: {{ disc }}%</p>{% if offer %}<p class="pill offer">{{ offer.title }} valid till {{ offer.deadline }}</p>{% endif %}{% else %}<p class="price">₹{{ c.price }}</p><p class="muted">Signup or login to unlock category discount, offer benefits and saved payment tracking.</p>{% endif %}{% if c.offer_deadline %}<p class="pill offer">Category offer deadline: {{ c.offer_deadline }}</p>{% endif %}<a class="btn" href="{{ url_for('payment', category_id=c.id) }}">Proceed to Payment</a><br><br><a class="btn secondary" href="https://wa.me/{{ whatsapp }}?text={{ ('I am interested in '+c.name+' data from '+app_name)|urlencode }}">Contact on WhatsApp</a></div></div></section>
""", c=c, final=final, disc=disc, offer=offer)
    return page(body, c["name"])

@app.route("/demo-download/<filename>")
def download_demo(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

@app.route("/pricing")
def pricing():
    cats = query("SELECT * FROM categories WHERE active=1 ORDER BY price")
    offer = active_offer()
    body = render_template_string(r"""<section class="section"><div class="wrap"><h2>Transparent Pricing</h2>{% if offer %}<div class="card" style="margin-bottom:18px"><span class="pill offer">Active Offer</span><h3>{{offer.title}}</h3><p class="muted">{{offer.body}}</p><p><b>{{offer.discount}}% discount</b> valid till {{offer.deadline}}</p></div>{% endif %}<table class="table"><tr><th>Category</th><th>Type</th><th>Base Price</th><th>Discount</th><th>Deadline</th><th>Action</th></tr>{% for c in cats %}<tr><td>{{c.name}}</td><td>{{c.type}}</td><td>₹{{c.price}}</td><td>{{c.discount}}%</td><td>{{c.offer_deadline or '-'}}</td><td><a class="btn secondary" href="{{ url_for('category_detail', slug=c.slug) }}">View</a></td></tr>{% endfor %}</table></div></section>""", cats=cats, offer=offer)
    return page(body, "Pricing")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        try:
            query("INSERT INTO users(name,email,phone,company,password,role,discount,preferred_data,email_notifications,whatsapp_updates) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (request.form["name"], request.form["email"].lower(), request.form.get("phone"), request.form.get("company"), generate_password_hash(request.form["password"]), "customer", 5, request.form.get("preferred_data"), 1, 1), commit=True)
            flash("Account created successfully. Please login to unlock discounts.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already registered.")
    body = r"""<section class="section"><div class="wrap"><div class="card" style="max-width:620px;margin:auto"><h2>Create Customer Account</h2><p class="muted">Signup to unlock discounts, save payment requests, manage profile settings and receive priority support.</p><form method="post"><input class="input" name="name" placeholder="Full name" required><br><br><input class="input" name="email" type="email" placeholder="Email" required><br><br><input class="input" name="phone" placeholder="Phone number"><br><br><input class="input" name="company" placeholder="Company / Organization"><br><br><input class="input" name="preferred_data" placeholder="Preferred data requirement, e.g., CBSE Bangalore leads"><br><br><input class="input" name="password" type="password" placeholder="Password" required><br><br><button class="btn">Create Account</button></form><p class="muted">Already have an account? <a href="/login" style="color:#d7b56d">Login here</a></p></div></div></section>"""
    return page(body, "Signup")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = query("SELECT * FROM users WHERE email=?", (request.form["email"].lower(),), one=True)
        if u and check_password_hash(u["password"], request.form["password"]):
            session["user_id"] = u["id"]
            flash("Login successful.")
            return redirect(url_for("admin" if u["role"]=="admin" else "profile"))
        flash("Invalid email or password.")
    body = r"""<section class="section"><div class="wrap"><div class="card" style="max-width:520px;margin:auto"><h2>Login</h2><form method="post"><input class="input" name="email" type="email" placeholder="Email" required><br><br><input class="input" name="password" type="password" placeholder="Password" required><br><br><button class="btn">Login</button></form><p class="muted">New customer? <a href="/signup" style="color:#d7b56d">Create account to unlock discounts</a></p></div></div></section>"""
    return page(body, "Login")

@app.route("/logout")
def logout():
    session.clear(); flash("Logged out."); return redirect(url_for("home"))

@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    u = current_user()
    if request.method == "POST":
        action = request.form.get("action", "profile")
        if action == "password":
            if not check_password_hash(u["password"], request.form.get("current_password", "")):
                flash("Current password is incorrect.")
            elif request.form.get("new_password") != request.form.get("confirm_password"):
                flash("New password and confirm password do not match.")
            else:
                query("UPDATE users SET password=? WHERE id=?", (generate_password_hash(request.form["new_password"]), u["id"]), commit=True)
                flash("Password updated successfully.")
        else:
            query("""UPDATE users SET name=?, phone=?, company=?, address=?, city=?, state=?, pincode=?, preferred_data=?, profile_notes=?, email_notifications=?, whatsapp_updates=? WHERE id=?""", (
                request.form["name"], request.form.get("phone"), request.form.get("company"), request.form.get("address"), request.form.get("city"), request.form.get("state"), request.form.get("pincode"), request.form.get("preferred_data"), request.form.get("profile_notes"), 1 if request.form.get("email_notifications") else 0, 1 if request.form.get("whatsapp_updates") else 0, u["id"]
            ), commit=True)
            flash("Profile settings updated.")
        return redirect(url_for("profile"))
    u = current_user()
    payments = query("SELECT p.*, c.name category FROM payments p LEFT JOIN categories c ON c.id=p.category_id WHERE p.user_id=? ORDER BY p.id DESC", (u["id"],))
    content = render_template_string(r"""
<section class="section"><div class="wrap"><div class="grid3"><div class="card"><h3>Member Discount</h3><h2>{{u.discount}}%</h2><p class="muted">Your login-based customer discount.</p></div><div class="card"><h3>Payment Requests</h3><h2>{{payments|length}}</h2><p class="muted">Track all submitted payments.</p></div><div class="card"><h3>Account Type</h3><h2>{{u.role|title}}</h2><p class="muted">Active customer account.</p></div></div><div class="grid" style="margin-top:18px"><div class="card"><h2>Profile & Business Settings</h2><form method="post"><input type="hidden" name="action" value="profile"><label>Full Name</label><input class="input" name="name" value="{{u.name}}" required><br><br><label>Phone Number</label><input class="input" name="phone" value="{{u.phone or ''}}" placeholder="Phone"><br><br><label>Company / Organization</label><input class="input" name="company" value="{{u.company or ''}}" placeholder="Company"><br><br><label>Address</label><textarea name="address" rows="2" placeholder="Office / billing address">{{u.address or ''}}</textarea><br><br><div class="grid3"><div><label>City</label><input class="input" name="city" value="{{u.city or ''}}"></div><div><label>State</label><input class="input" name="state" value="{{u.state or ''}}"></div><div><label>Pincode</label><input class="input" name="pincode" value="{{u.pincode or ''}}"></div></div><br><label>Preferred Data Requirement</label><input class="input" name="preferred_data" value="{{u.preferred_data or ''}}" placeholder="Example: CBSE Bangalore, Telangana leads"><br><br><label>Internal Notes / Requirements</label><textarea name="profile_notes" rows="3">{{u.profile_notes or ''}}</textarea><br><br><label><input type="checkbox" name="email_notifications" {% if u.email_notifications %}checked{% endif %}> Receive email updates</label><br><label><input type="checkbox" name="whatsapp_updates" {% if u.whatsapp_updates %}checked{% endif %}> Receive WhatsApp updates</label><br><br><button class="btn">Save Profile Settings</button></form></div><div><div class="card"><h2>Security Settings</h2><form method="post"><input type="hidden" name="action" value="password"><input class="input" name="current_password" type="password" placeholder="Current password" required><br><br><input class="input" name="new_password" type="password" placeholder="New password" required><br><br><input class="input" name="confirm_password" type="password" placeholder="Confirm new password" required><br><br><button class="btn secondary">Update Password</button></form></div><div class="card" style="margin-top:18px"><h2>Payment Requests</h2><table class="table"><tr><th>Category</th><th>Amount</th><th>Status</th></tr>{% for p in payments %}<tr><td>{{p.category}}</td><td>₹{{p.amount}}</td><td>{{p.status}}</td></tr>{% else %}<tr><td colspan=3>No payments yet.</td></tr>{% endfor %}</table></div></div></div></div></section>
""", u=u, payments=payments)
    return page(content, "Profile")

@app.route("/payment/<int:category_id>", methods=["GET","POST"])
def payment(category_id):
    c = query("SELECT * FROM categories WHERE id=?", (category_id,), one=True)
    if not c: abort(404)
    u = current_user()
    offer = active_offer()
    extra_offer_discount = offer["discount"] if offer else 0
    disc = (c["discount"] + (u["discount"] if u else 0) + (extra_offer_discount if u else 0)) if u else 0
    amount = max(0, int(c["price"] - (c["price"] * disc / 100)))
    upi = upi_id_setting()
    upi_link = f"upi://pay?pa={quote_plus(upi)}&pn={quote_plus(app_display_name())}&am={amount}&cu=INR&tn={quote_plus('Payment for '+c['name'])}"
    if request.method == "POST":
        uid = u["id"] if u else None
        query("INSERT INTO payments(user_id,category_id,name,phone,amount,transaction_id,status) VALUES(?,?,?,?,?,?,?)",
              (uid, c["id"], request.form["name"], request.form["phone"], amount, request.form.get("transaction_id"), "Pending Review"), commit=True)
        flash("Payment request submitted. Admin will verify and confirm.")
        return redirect(url_for("profile") if u else url_for("home"))
    body = render_template_string(r"""<section class="section"><div class="wrap grid"><div class="card"><h2>Payment for {{c.name}}</h2><p class="price">₹{{amount}}</p><p class="muted">Pay using any UPI app: Google Pay, PhonePe, Paytm, Navi, BHIM or bank UPI apps.</p><p><b>UPI ID:</b> {{upi}}</p><a class="btn" href="{{upi_link}}">Open UPI App</a><p class="muted">After payment, submit transaction ID below for verification.</p></div><div class="card"><h2>Submit Payment Details</h2><form method="post"><input class="input" name="name" value="{{user.name if user else ''}}" placeholder="Name" required><br><br><input class="input" name="phone" value="{{user.phone if user else ''}}" placeholder="Phone" required><br><br><input class="input" name="transaction_id" placeholder="UPI Transaction ID / Reference"><br><br><button class="btn">Submit for Verification</button></form></div></div></section>""", c=c, amount=amount, upi=upi, upi_link=upi_link)
    return page(body, "Payment")

@app.route("/support", methods=["GET","POST"])
def support():
    if request.method == "POST":
        name=request.form["name"]; phone=request.form["phone"]; company=request.form.get("company",""); msg=request.form["message"]; img=request.form.get("image_url","")
        query("INSERT INTO support_tickets(name,phone,company,message,image_url) VALUES(?,?,?,?,?)", (name,phone,company,msg,img), commit=True)
        wa = f"https://wa.me/{whatsapp_number()}?text=" + quote_plus(f"Support Request\nName: {name}\nPhone: {phone}\nCompany: {company}\nMessage: {msg}\nImage/Link: {img}")
        flash("Support request saved. WhatsApp will open with your message.")
        return redirect(wa)
    body = r"""<section class="section"><div class="wrap"><div class="card" style="max-width:720px;margin:auto"><h2>Support & Custom Data Request</h2><p class="muted">Send your requirement, category request, bulk data enquiry or issue.</p><form method="post"><input class="input" name="name" placeholder="Your name" required><br><br><input class="input" name="phone" placeholder="Phone number" required><br><br><input class="input" name="company" placeholder="Company / Organization"><br><br><textarea name="message" rows="5" placeholder="Tell us what data you need" required></textarea><br><br><input class="input" name="image_url" placeholder="Optional image/file link"><br><br><button class="btn">Send to WhatsApp & Save Record</button></form><p class="muted">Your request is stored in admin dashboard and sent to WhatsApp.</p></div></div></section>"""
    return page(body, "Support")

# ---------------- Admin ----------------
def admin_layout(content):
    return page(render_template_string(r"""<section class="section"><div class="wrap admin"><div class="card side"><h3>Admin Panel</h3><a href="{{url_for('admin')}}">Dashboard</a><a href="{{url_for('admin_categories')}}">Manage Categories</a><a href="{{url_for('admin_customers')}}">Customers</a><a href="{{url_for('admin_payments')}}">Payments</a><a href="{{url_for('admin_support')}}">Support Tickets</a><a href="{{url_for('admin_ads')}}">Advertisements</a><a href="{{url_for('admin_offers')}}">Discount Offers</a><a href="{{url_for('admin_settings')}}">Settings</a></div><div>{{content|safe}}</div></div></section>""", content=content), "Admin")

@app.route("/admin")
@admin_required
def admin():
    stats = {
        "customers": query("SELECT COUNT(*) n FROM users WHERE role='customer'", one=True)["n"],
        "categories": query("SELECT COUNT(*) n FROM categories", one=True)["n"],
        "payments": query("SELECT COUNT(*) n FROM payments", one=True)["n"],
        "tickets": query("SELECT COUNT(*) n FROM support_tickets", one=True)["n"],
        "offers": query("SELECT COUNT(*) n FROM offers", one=True)["n"],
    }
    content = render_template_string(r"""<div class="grid3"><div class="card"><h2>{{stats.customers}}</h2><p class="muted">Customers</p></div><div class="card"><h2>{{stats.categories}}</h2><p class="muted">Categories</p></div><div class="card"><h2>{{stats.payments}}</h2><p class="muted">Payments</p></div><div class="card"><h2>{{stats.tickets}}</h2><p class="muted">Support Tickets</p></div><div class="card"><h2>{{stats.offers}}</h2><p class="muted">Discount Offers</p></div></div><div class="card" style="margin-top:18px"><h2>Admin Control Center</h2><p class="muted">Manage data categories, uploaded demo sheets, demo links, prices, discount deadlines, offers, advertisements, customer records, payment verification and support tickets.</p></div>""", stats=stats)
    return admin_layout(content)

@app.route("/admin/categories", methods=["GET","POST"])
@admin_required
def admin_categories():
    if request.args.get("delete"):
        query("DELETE FROM categories WHERE id=?", (request.args.get("delete"),), commit=True)
        flash("Category deleted.")
        return redirect(url_for("admin_categories"))
    if request.method == "POST":
        cid = request.form.get("id")
        existing = query("SELECT * FROM categories WHERE id=?", (cid,), one=True) if cid else None
        uploaded = save_demo_file(request.files.get("demo_file"))
        demo_file = uploaded or (existing["demo_file"] if existing else None)
        data=(request.form["name"], request.form["slug"], request.form["type"], request.form["description"], request.form["price"], request.form["discount"], request.form["demo_data"], request.form.get("demo_link"), demo_file, request.form.get("offer_deadline"), 1 if request.form.get("active") else 0)
        if cid:
            query("UPDATE categories SET name=?,slug=?,type=?,description=?,price=?,discount=?,demo_data=?,demo_link=?,demo_file=?,offer_deadline=?,active=? WHERE id=?", (*data,cid), commit=True)
        else:
            query("INSERT INTO categories(name,slug,type,description,price,discount,demo_data,demo_link,demo_file,offer_deadline,active) VALUES(?,?,?,?,?,?,?,?,?,?,?)", data, commit=True)
        flash("Category saved.")
        return redirect(url_for("admin_categories"))
    cats=query("SELECT * FROM categories ORDER BY id DESC")
    edit=query("SELECT * FROM categories WHERE id=?", (request.args.get("edit"),), one=True) if request.args.get("edit") else None
    content=render_template_string(r"""<div class="card"><h2>{{'Edit' if edit else 'Add'}} Category</h2><form method="post" enctype="multipart/form-data"><input type="hidden" name="id" value="{{edit.id if edit else ''}}"><label>Name</label><input class="input" name="name" value="{{edit.name if edit else ''}}" placeholder="Name" required><br><br><label>Slug</label><input class="input" name="slug" value="{{edit.slug if edit else ''}}" placeholder="slug-like-this" required><br><br><label>Type</label><input class="input" name="type" value="{{edit.type if edit else ''}}" placeholder="State / City / Board" required><br><br><label>Description</label><textarea name="description" rows="3" placeholder="Description">{{edit.description if edit else ''}}</textarea><br><br><div class="grid3"><div><label>Price</label><input class="input" name="price" type="number" value="{{edit.price if edit else 0}}" placeholder="Price"></div><div><label>Category Discount %</label><input class="input" name="discount" type="number" value="{{edit.discount if edit else 0}}" placeholder="Discount %"></div><div><label>Offer Deadline</label><input class="input" name="offer_deadline" type="date" value="{{edit.offer_deadline if edit else ''}}"></div></div><br><label>Demo Data Preview Text</label><textarea name="demo_data" rows="3" placeholder="Demo data preview">{{edit.demo_data if edit else ''}}</textarea><br><br><label>Demo Excel / CSV / PDF / TXT Upload</label><input class="input" type="file" name="demo_file" accept=".xlsx,.xls,.csv,.pdf,.txt">{% if edit and edit.demo_file %}<p class="muted">Current file: <a href="{{ url_for('download_demo', filename=edit.demo_file) }}">{{edit.demo_file}}</a></p>{% endif %}<br><label>Demo Data Link</label><input class="input" name="demo_link" value="{{edit.demo_link if edit else ''}}" placeholder="Google Sheet / Drive / Excel online link"><br><br><label><input type="checkbox" name="active" {% if not edit or edit.active %}checked{% endif %}> Active</label><br><br><button class="btn">Save Category</button></form></div><div class="card" style="margin-top:18px"><h2>All Categories</h2><table class="table"><tr><th>Name</th><th>Type</th><th>Price</th><th>Discount</th><th>Deadline</th><th>Demo</th><th>Action</th></tr>{% for c in cats %}<tr><td>{{c.name}}</td><td>{{c.type}}</td><td>₹{{c.price}}</td><td>{{c.discount}}%</td><td>{{c.offer_deadline or '-'}}</td><td>{% if c.demo_file %}File{% endif %}{% if c.demo_link %} Link{% endif %}</td><td><a href="?edit={{c.id}}">Edit</a> | <a href="?delete={{c.id}}" onclick="return confirm('Delete this category?')">Delete</a></td></tr>{% endfor %}</table></div>""", cats=cats, edit=edit)
    return admin_layout(content)

@app.route("/admin/customers", methods=["GET","POST"])
@admin_required
def admin_customers():
    if request.args.get("delete"):
        uid = request.args.get("delete")
        user_row = query("SELECT * FROM users WHERE id=?", (uid,), one=True)
        if user_row and user_row["role"] != "admin":
            query("DELETE FROM users WHERE id=?", (uid,), commit=True)
            flash("Customer deleted.")
        else:
            flash("Admin account cannot be deleted here.")
        return redirect(url_for("admin_customers"))
    if request.method=="POST":
        query("UPDATE users SET name=?,phone=?,company=?,discount=?,address=?,city=?,state=?,pincode=?,preferred_data=?,profile_notes=? WHERE id=?", (request.form["name"],request.form.get("phone"),request.form.get("company"),request.form.get("discount",0),request.form.get("address"),request.form.get("city"),request.form.get("state"),request.form.get("pincode"),request.form.get("preferred_data"),request.form.get("profile_notes"),request.form["id"]), commit=True)
        flash("Customer updated.")
        return redirect(url_for("admin_customers"))
    users=query("SELECT * FROM users ORDER BY id DESC")
    edit=query("SELECT * FROM users WHERE id=?", (request.args.get("edit"),), one=True) if request.args.get("edit") else None
    content=render_template_string(r"""{% if edit %}<div class="card"><h2>Edit Customer</h2><form method="post"><input type="hidden" name="id" value="{{edit.id}}"><label>Name</label><input class="input" name="name" value="{{edit.name}}" required><br><br><label>Phone</label><input class="input" name="phone" value="{{edit.phone or ''}}"><br><br><label>Company</label><input class="input" name="company" value="{{edit.company or ''}}"><br><br><label>Discount %</label><input class="input" type="number" name="discount" value="{{edit.discount or 0}}"><br><br><label>Address</label><textarea name="address" rows="2">{{edit.address or ''}}</textarea><br><br><div class="grid3"><input class="input" name="city" value="{{edit.city or ''}}" placeholder="City"><input class="input" name="state" value="{{edit.state or ''}}" placeholder="State"><input class="input" name="pincode" value="{{edit.pincode or ''}}" placeholder="Pincode"></div><br><label>Preferred Data</label><input class="input" name="preferred_data" value="{{edit.preferred_data or ''}}"><br><br><label>Notes</label><textarea name="profile_notes" rows="3">{{edit.profile_notes or ''}}</textarea><br><br><button class="btn">Save Customer</button></form></div>{% endif %}<div class="card" style="margin-top:18px"><h2>Customers & Credentials</h2><table class="table"><tr><th>Name</th><th>Email</th><th>Phone</th><th>Company</th><th>Discount</th><th>Role</th><th>Action</th></tr>{% for u in users %}<tr><td>{{u.name}}</td><td>{{u.email}}</td><td>{{u.phone}}</td><td>{{u.company}}</td><td>{{u.discount}}%</td><td>{{u.role}}</td><td><a href="?edit={{u.id}}">Edit</a>{% if u.role!='admin' %} | <a href="?delete={{u.id}}" onclick="return confirm('Delete this customer?')">Delete</a>{% endif %}</td></tr>{% endfor %}</table><p class="muted">Passwords are securely hashed. Admin can update customer profile, discount and business details, but cannot view raw passwords.</p></div>""", users=users, edit=edit)
    return admin_layout(content)

@app.route("/admin/payments", methods=["GET","POST"])
@admin_required
def admin_payments():
    if request.method=="POST":
        query("UPDATE payments SET status=? WHERE id=?", (request.form["status"],request.form["id"]), commit=True)
        flash("Payment status updated.")
        return redirect(url_for("admin_payments"))
    payments=query("SELECT p.*, c.name category, u.email FROM payments p LEFT JOIN categories c ON c.id=p.category_id LEFT JOIN users u ON u.id=p.user_id ORDER BY p.id DESC")
    content=render_template_string(r"""<div class="card"><h2>Payment Verification</h2><table class="table"><tr><th>Name</th><th>Phone</th><th>Category</th><th>Amount</th><th>Txn ID</th><th>Status</th><th>Update</th></tr>{% for p in payments %}<tr><td>{{p.name}}</td><td>{{p.phone}}</td><td>{{p.category}}</td><td>₹{{p.amount}}</td><td>{{p.transaction_id}}</td><td>{{p.status}}</td><td><form method="post" style="display:flex;gap:6px"><input type="hidden" name="id" value="{{p.id}}"><select name="status"><option {% if p.status=='Pending Review' %}selected{% endif %}>Pending Review</option><option {% if p.status=='Paid' %}selected{% endif %}>Paid</option><option {% if p.status=='Rejected' %}selected{% endif %}>Rejected</option><option {% if p.status=='Delivered' %}selected{% endif %}>Delivered</option></select><button class="btn secondary">Save</button></form></td></tr>{% endfor %}</table></div>""", payments=payments)
    return admin_layout(content)

@app.route("/admin/support")
@admin_required
def admin_support():
    tickets=query("SELECT * FROM support_tickets ORDER BY id DESC")
    content=render_template_string(r"""<div class="card"><h2>Support Tickets</h2><table class="table"><tr><th>Name</th><th>Phone</th><th>Company</th><th>Message</th><th>Image/Link</th><th>Date</th></tr>{% for t in tickets %}<tr><td>{{t.name}}</td><td>{{t.phone}}</td><td>{{t.company}}</td><td>{{t.message}}</td><td>{{t.image_url}}</td><td>{{t.created_at}}</td></tr>{% endfor %}</table></div>""", tickets=tickets)
    return admin_layout(content)

@app.route("/admin/ads", methods=["GET","POST"])
@admin_required
def admin_ads():
    if request.args.get("delete"):
        query("DELETE FROM ads WHERE id=?", (request.args.get("delete"),), commit=True)
        flash("Advertisement deleted.")
        return redirect(url_for("admin_ads"))
    if request.args.get("toggle"):
        ad = query("SELECT * FROM ads WHERE id=?", (request.args.get("toggle"),), one=True)
        if ad:
            query("UPDATE ads SET active=? WHERE id=?", (0 if ad["active"] else 1, ad["id"]), commit=True)
        return redirect(url_for("admin_ads"))
    if request.method=="POST":
        aid = request.form.get("id")
        if aid:
            query("UPDATE ads SET title=?,body=?,active=? WHERE id=?", (request.form["title"],request.form["body"],1 if request.form.get("active") else 0,aid), commit=True)
            flash("Advertisement updated.")
        else:
            query("INSERT INTO ads(title,body,active) VALUES(?,?,?)", (request.form["title"],request.form["body"],1 if request.form.get("active") else 0), commit=True)
            flash("Advertisement added.")
        return redirect(url_for("admin_ads"))
    ads=query("SELECT * FROM ads ORDER BY id DESC")
    edit=query("SELECT * FROM ads WHERE id=?", (request.args.get("edit"),), one=True) if request.args.get("edit") else None
    content=render_template_string(r"""<div class="card"><h2>{{'Edit' if edit else 'Add'}} Advertisement</h2><form method="post"><input type="hidden" name="id" value="{{edit.id if edit else ''}}"><input class="input" name="title" value="{{edit.title if edit else ''}}" placeholder="Title" required><br><br><textarea name="body" rows="3" placeholder="Ad message" required>{{edit.body if edit else ''}}</textarea><br><br><label><input type="checkbox" name="active" {% if not edit or edit.active %}checked{% endif %}> Active</label><br><br><button class="btn">Save Ad</button></form></div><div class="card" style="margin-top:18px"><table class="table"><tr><th>Title</th><th>Body</th><th>Active</th><th>Action</th></tr>{% for a in ads %}<tr><td>{{a.title}}</td><td>{{a.body}}</td><td>{{a.active}}</td><td><a href="?edit={{a.id}}">Edit</a> | <a href="?toggle={{a.id}}">Toggle</a> | <a href="?delete={{a.id}}" onclick="return confirm('Delete this ad?')">Delete</a></td></tr>{% endfor %}</table></div>""", ads=ads, edit=edit)
    return admin_layout(content)

@app.route("/admin/offers", methods=["GET","POST"])
@admin_required
def admin_offers():
    if request.args.get("delete"):
        query("DELETE FROM offers WHERE id=?", (request.args.get("delete"),), commit=True)
        flash("Discount offer deleted.")
        return redirect(url_for("admin_offers"))
    if request.args.get("toggle"):
        offer = query("SELECT * FROM offers WHERE id=?", (request.args.get("toggle"),), one=True)
        if offer:
            query("UPDATE offers SET active=? WHERE id=?", (0 if offer["active"] else 1, offer["id"]), commit=True)
        return redirect(url_for("admin_offers"))
    if request.method == "POST":
        oid = request.form.get("id")
        data = (request.form["title"], request.form.get("body"), request.form.get("discount",0), request.form.get("deadline"), 1 if request.form.get("active") else 0)
        if oid:
            query("UPDATE offers SET title=?,body=?,discount=?,deadline=?,active=? WHERE id=?", (*data, oid), commit=True)
            flash("Discount offer updated.")
        else:
            query("INSERT INTO offers(title,body,discount,deadline,active) VALUES(?,?,?,?,?)", data, commit=True)
            flash("Discount offer added.")
        return redirect(url_for("admin_offers"))
    offers = query("SELECT * FROM offers ORDER BY id DESC")
    edit = query("SELECT * FROM offers WHERE id=?", (request.args.get("edit"),), one=True) if request.args.get("edit") else None
    content = render_template_string(r"""<div class="card"><h2>{{'Edit' if edit else 'Add'}} Discount Offer</h2><form method="post"><input type="hidden" name="id" value="{{edit.id if edit else ''}}"><label>Offer Title</label><input class="input" name="title" value="{{edit.title if edit else ''}}" placeholder="Example: Festive Offer" required><br><br><label>Offer Message</label><textarea name="body" rows="3" placeholder="Offer description">{{edit.body if edit else ''}}</textarea><br><br><div class="grid3"><div><label>Discount %</label><input class="input" type="number" name="discount" value="{{edit.discount if edit else 0}}"></div><div><label>Deadline</label><input class="input" type="date" name="deadline" value="{{edit.deadline if edit else ''}}"></div><div><label>Status</label><br><label><input type="checkbox" name="active" {% if not edit or edit.active %}checked{% endif %}> Active</label></div></div><br><button class="btn">Save Offer</button></form></div><div class="card" style="margin-top:18px"><h2>All Discount Offers</h2><table class="table"><tr><th>Title</th><th>Discount</th><th>Deadline</th><th>Active</th><th>Action</th></tr>{% for o in offers %}<tr><td>{{o.title}}<br><span class="muted">{{o.body}}</span></td><td>{{o.discount}}%</td><td>{{o.deadline or '-'}}</td><td>{{o.active}}</td><td><a href="?edit={{o.id}}">Edit</a> | <a href="?toggle={{o.id}}">Toggle</a> | <a href="?delete={{o.id}}" onclick="return confirm('Delete this offer?')">Delete</a></td></tr>{% endfor %}</table></div>""", offers=offers, edit=edit)
    return admin_layout(content)

@app.route("/admin/settings", methods=["GET","POST"])
@admin_required
def admin_settings():
    if request.method=="POST":
        keys = ["app_name","logo_text","brand_tagline","support_email","whatsapp_number","upi_id","business_address","footer_note","popup_title","popup_body"]
        for k in keys:
            query("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, request.form.get(k,"")), commit=True)
        flash("Settings updated.")
        return redirect(url_for("admin_settings"))
    s=settings_dict()
    content=render_template_string(r"""<div class="card"><h2>Website & Business Settings</h2><form method="post"><label>Project / Website Name</label><input class="input" name="app_name" value="{{s.get('app_name','')}}" placeholder="ACROSS THE DATA"><br><br><label>Logo Text / Initials</label><input class="input" name="logo_text" value="{{s.get('logo_text','')}}" placeholder="Leave empty now"><br><br><label>Brand Tagline</label><textarea name="brand_tagline" rows="3">{{s.get('brand_tagline','')}}</textarea><br><br><div class="grid3"><div><label>Support Email</label><input class="input" name="support_email" value="{{s.get('support_email','')}}"></div><div><label>WhatsApp Number with country code</label><input class="input" name="whatsapp_number" value="{{s.get('whatsapp_number','')}}"></div><div><label>UPI ID</label><input class="input" name="upi_id" value="{{s.get('upi_id','')}}"></div></div><br><label>Business Address</label><input class="input" name="business_address" value="{{s.get('business_address','')}}"><br><br><label>Footer Note</label><textarea name="footer_note" rows="2">{{s.get('footer_note','')}}</textarea><br><br><label>Login Popup Title</label><input class="input" name="popup_title" value="{{s.get('popup_title','')}}"><br><br><label>Login Popup Body</label><textarea name="popup_body" rows="3">{{s.get('popup_body','')}}</textarea><br><br><button class="btn">Save Settings</button></form><p class="muted">Now you can change project name, logo initials, contact, UPI, popup content and footer directly from admin dashboard.</p></div>""", s=s)
    return admin_layout(content)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

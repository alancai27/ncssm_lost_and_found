"""
NCSSM Durham Lost & Found

Two features:
  1. Post a found item -- upload a photo, a vision model catalogues it.
  2. Search -- describe what you lost in plain English, get ranked matches
     with the finder's contact info.
"""

import io
import os
import re
import secrets

# Read .env first: ai.py and auth.py both read os.environ at import time.
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from datetime import timedelta

from flask import (
    Flask, Response, abort, flash, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from PIL import Image, ImageOps
from werkzeug.exceptions import RequestEntityTooLarge

import ai
import auth
import db
import storage

# iPhone photos are often HEIC; most browsers convert on upload, but if
# pillow-heif is installed we can accept them directly.
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
MAX_EDGE = 1600
THUMB_EDGE = 600
CAMPUSES = {"durham", "morganton"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def _secret_key():
    """
    Sessions are what keep people signed in, so the key has to survive a
    restart. Use SECRET_KEY if it is set; otherwise keep a generated one in
    a gitignored file so local development does not log everyone out on
    every reload.
    """
    from_env = os.environ.get("SECRET_KEY")
    if from_env:
        return from_env
    path = os.path.join(BASE_DIR, ".secret_key")
    if os.path.exists(path):
        with open(path) as fh:
            return fh.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as fh:
        fh.write(key)
    os.chmod(path, 0o600)
    return key


app.secret_key = _secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Sent over plain HTTP in local development; required over TLS in production.
    SESSION_COOKIE_SECURE=os.environ.get("HTTPS_ONLY", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

os.makedirs(UPLOAD_DIR, exist_ok=True)
db.init()

# Fail at boot rather than on a student's first upload.
if storage.using_s3():
    for _note in storage.config_warnings():
        print(f"  ! {_note}")
    storage.check()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def current_campus():
    campus = request.args.get("campus") or request.cookies.get("campus") or "durham"
    return campus if campus in CAMPUSES else "durham"


@app.context_processor
def inject_globals():
    return {
        "campus": current_campus(),
        "ai_on": ai.available(),
        "model": ai.MODEL,
        "stats": db.counts(),
        "user": auth.current_user(),
        "auth_enabled": auth.enabled(),
        "auth_domain": auth.ALLOWED_DOMAIN,
    }


def save_photo(file_storage):
    """
    Normalise an upload: fix EXIF rotation, cap the long edge, write a JPEG
    plus a thumbnail. Returns (image_name, thumb_name, jpeg_bytes).
    """
    raw = file_storage.read()
    if not raw:
        raise ValueError("The uploaded file was empty.")

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img.load()
    except Exception:
        raise ValueError("That file could not be read as an image. Try a JPG or PNG.")

    if img.mode not in ("RGB", "L"):
        # Flatten transparency onto white rather than onto black.
        background = Image.new("RGB", img.size, (255, 255, 255))
        alpha = img.convert("RGBA").split()[-1]
        background.paste(img.convert("RGB"), mask=alpha)
        img = background
    else:
        img = img.convert("RGB")

    img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

    stem = secrets.token_hex(8)
    image_name = f"{stem}.jpg"
    thumb_name = f"{stem}_t.jpg"

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85, optimize=True)
    jpeg_bytes = buf.getvalue()
    storage.save(image_name, jpeg_bytes)

    thumb = img.copy()
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.LANCZOS)
    tbuf = io.BytesIO()
    thumb.save(tbuf, "JPEG", quality=80, optimize=True)
    storage.save(thumb_name, tbuf.getvalue())

    return image_name, thumb_name, jpeg_bytes


def build_search_text(**parts):
    return " ".join(str(v) for v in parts.values() if v).lower()


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.route("/")
@auth.view_login_required
def index():
    return render_template("index.html")


@app.route("/search")
@auth.view_login_required
def search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return redirect(url_for("index"))

    campus = current_campus()
    pool = db.list_items(campus=campus)

    # Score everything lexically first -- cheap, and it decides what the
    # model actually has to look at.
    scored = []
    for item in pool:
        item["keyword_score"] = ai.keyword_score(query, item)
        scored.append(item)
    scored.sort(key=lambda i: i["keyword_score"], reverse=True)

    ai_note = None
    results = []

    if ai.available() and pool:
        # Hand the model the lexical top slice plus the newest items, since
        # a good match can use words nobody thought to type.
        shortlist = scored[:30]
        seen = {i["id"] for i in shortlist}
        shortlist += [i for i in pool[:10] if i["id"] not in seen]
        try:
            ranked = ai.rank_matches(query, shortlist)
            by_id = {i["id"]: i for i in shortlist}
            for item_id, info in sorted(ranked.items(), key=lambda kv: -kv[1]["score"]):
                item = by_id[item_id]
                item["score"] = info["score"]
                item["reason"] = info["reason"]
                results.append(item)
        except ai.AIError as exc:
            ai_note = f"AI matching is unavailable right now ({exc}) — showing keyword matches instead."

    if not results:
        # No key, model failed, or the model found nothing it liked.
        for item in scored:
            if item["keyword_score"] >= 25:
                item["score"] = item["keyword_score"]
                item["reason"] = ""
                results.append(item)
        if ai.available() and not ai_note and not results:
            ai_note = "The AI didn't find a confident match. Try fewer words, or browse everything."

    return render_template(
        "results.html",
        query=query,
        results=results,
        ai_note=ai_note,
        pool_size=len(pool),
    )


@app.route("/post", methods=["GET", "POST"])
@auth.login_required
def post_item():
    if request.method == "GET":
        return render_template("post.html")

    photo = request.files.get("photo")
    if not photo or not photo.filename:
        flash("Please choose a photo of the item.", "error")
        return render_template("post.html", form=request.form), 400

    try:
        image_name, thumb_name, jpeg_bytes = save_photo(photo)
    except ValueError as exc:
        flash(str(exc), "error")
        return render_template("post.html", form=request.form), 400

    form = request.form
    manual_title = (form.get("title") or "").strip()
    note = (form.get("note") or "").strip()

    described = {}
    if ai.available():
        try:
            described = ai.describe_image(jpeg_bytes, "image/jpeg")
        except ai.AIError as exc:
            flash(f"Saved, but the AI could not describe the photo ({exc}).", "error")

    user = auth.current_user()
    campus = form.get("campus") if form.get("campus") in CAMPUSES else current_campus()
    title = manual_title or described.get("title") or (note[:60] if note else "Found item")

    description = described.get("description") or ""
    if described.get("distinguishing_marks"):
        description = f"{description} Distinguishing marks: {described['distinguishing_marks']}".strip()

    item_id = db.add_item(
        image=image_name,
        thumb=thumb_name,
        campus=campus,
        title=title,
        category=described.get("category"),
        color=described.get("color"),
        brand=described.get("brand"),
        ai_description=description or None,
        user_note=note or None,
        tags=described.get("tags") or [],
        search_text=build_search_text(
            t=title, c=described.get("category"), col=described.get("color"),
            b=described.get("brand"), d=description, n=note,
            loc=form.get("location"), tags=" ".join(described.get("tags") or []),
        ),
        found_location=(form.get("location") or "").strip() or None,
        found_at=(form.get("found_at") or "").strip() or None,
        # Identity comes from the verified session, not from the form. The
        # contact field is only an optional override ("front desk").
        finder_name=user["name"],
        finder_contact=(form.get("finder_contact") or "").strip() or None,
        posted_by=user["email"],
        posted_by_name=user["name"],
    )

    flash("Posted. Thanks for turning it in.", "ok")
    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/browse")
@auth.view_login_required
def browse():
    status = request.args.get("status", "unclaimed")
    status = status if status in {"unclaimed", "claimed"} else "unclaimed"
    items = db.list_items(campus=current_campus(), status=status)
    return render_template("browse.html", items=items, status=status)


@app.route("/item/<int:item_id>")
@auth.view_login_required
def item_detail(item_id):
    item = db.get_item(item_id)
    if not item:
        return render_template("notfound.html"), 404
    return render_template("item.html", item=item)


@app.route("/item/<int:item_id>/claim", methods=["POST"])
@auth.login_required
def claim(item_id):
    item = db.get_item(item_id)
    if not item:
        return render_template("notfound.html"), 404
    new_status = "unclaimed" if item["status"] == "claimed" else "claimed"
    db.set_status(item_id, new_status, by_email=auth.current_user()["email"])
    flash(
        "Marked as returned to its owner." if new_status == "claimed"
        else "Moved back to the unclaimed list.",
        "ok",
    )
    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/login")
def login():
    """Landing page with the Google button, so errors have somewhere to show."""
    if auth.current_user():
        return redirect(url_for("index"))

    if not auth.configured():
        flash(
            "Google sign-in is not set up on this server. See the README "
            "section on Google sign-in.",
            "error",
        )
        return redirect(url_for("index"))

    return render_template(
        "login.html",
        next_url=auth.safe_next(request.args.get("next")),
        redirect_uri=_redirect_uri(),
    )


@app.route("/login/google")
def login_google():
    try:
        return redirect(auth.begin(_redirect_uri(), request.args.get("next")))
    except auth.AuthError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))


@app.route("/auth/callback")
def auth_callback():
    try:
        user = auth.complete(_redirect_uri())
    except auth.AuthError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))

    auth.sign_in(user)
    flash(f"Signed in as {user['email']}.", "ok")
    return redirect(auth.pop_next() or url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    auth.sign_out()
    flash("Signed out.", "ok")
    return redirect(url_for("index"))


def _redirect_uri():
    """
    Must match the redirect URI registered with the provider exactly.
    Set OAUTH_REDIRECT_URI when running behind a proxy or a custom domain.
    """
    return os.environ.get("OAUTH_REDIRECT_URI") or url_for("auth_callback", _external=True)


@app.route("/privacy")
def privacy():
    """Google requires a reachable privacy policy URL to publish the OAuth app."""
    return render_template("privacy.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/favicon.ico")
def favicon():
    """Browsers ask for this at the root whatever the <link> tags say."""
    return send_from_directory(os.path.join(BASE_DIR, "static", "assets"), "favicon.ico")


@app.route("/uploads/<path:name>")
def uploads(name):
    """
    Streams from wherever photos actually live. Keeps a private bucket
    private, and means the URL is the same in every environment.
    """
    # Names are generated by us (hex + .jpg); refuse anything else outright
    # rather than trusting the storage layer to be path-traversal safe.
    if not re.fullmatch(r"[0-9a-z_]+\.(jpg|jpeg|png|webp)", name):
        abort(404)

    data, content_type = storage.load(name)
    if data is None:
        abort(404)

    resp = Response(data, mimetype=content_type)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@app.errorhandler(RequestEntityTooLarge)
def too_large(_exc):
    flash("That photo is over 16 MB. Try a smaller one.", "error")
    return render_template("post.html"), 413


@app.errorhandler(404)
def not_found(_exc):
    return render_template("notfound.html"), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  NCSSM Lost & Found  ->  http://127.0.0.1:{port}")
    print(f"  Database: {db.backend_name()}")
    print(f"  Photos:   {storage.backend_name()}")
    print(f"  Vision matching: {'ON (' + ai.MODEL + ')' if ai.available() else 'OFF — set GEMINI_API_KEY for AI search'}")
    if auth.configured():
        print(f"  Sign-in: Google, @{auth.ALLOWED_DOMAIN} only")
    for note in auth.warn_if_insecure():
        print(f"  ! {note}")
    # Always print these. Google matches redirect URIs byte for byte, and
    # localhost is not the same string as 127.0.0.1, so a mismatch is the most
    # common setup failure by a wide margin.
    print("\n  Authorized redirect URIs -- these must be registered on the OAuth")
    print("  client, under \"Authorized redirect URIs\", NOT \"JavaScript origins\":")
    print(f"      http://localhost:{port}/auth/callback")
    print(f"      http://127.0.0.1:{port}/auth/callback")
    print()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=port)

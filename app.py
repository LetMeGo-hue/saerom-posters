"""
새롬고등학교 포스터 플랫폼 — Supabase(poster-hub) 연동
로컬 실행: python app.py
배포 실행: gunicorn app:app
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

import auth
import categories
import db

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["UPLOAD_FOLDER"] = db.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

# Render, Fly.io 등 HTTPS 프록시 뒤에서 올바른 URL 생성
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

db.init_db()


def site_url() -> str:
    configured = os.getenv("SITE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    try:
        return request.url_root.rstrip("/")
    except RuntimeError:
        return "http://127.0.0.1:5000"


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def poster_image_src(poster, external: bool = False) -> str | None:
    """Supabase Storage 공개 URL 우선, 없으면 로컬 /uploads 경로."""
    if isinstance(poster, dict):
        image_url = poster.get("image_url")
        image_path = poster.get("image_path")
    else:
        image_url = poster["image_url"] if "image_url" in poster.keys() else None
        image_path = poster["image_path"]

    for candidate in (image_url, image_path):
        if candidate and str(candidate).startswith(("http://", "https://")):
            return str(candidate)

    filename = db.image_filename(image_path)
    if not filename:
        return None
    return url_for("uploaded_file", filename=filename, _external=external)


def poster_image_url(poster, _external=False) -> str | None:
    return poster_image_src(poster, external=_external)


def poster_public_url(poster) -> str:
    return f"{site_url()}/p/{poster['slug']}"


def poster_to_dict(poster) -> dict:
    return {
        "id": poster["id"],
        "slug": poster["slug"],
        "title": poster["title"],
        "description": poster["description"],
        "category": poster["category"],
        "location": poster["location"],
        "start_date": poster["start_date"],
        "end_date": poster["end_date"],
        "detail_url": poster["detail_url"],
        "image_url": poster_image_url(poster, _external=True),
        "public_url": poster_public_url(poster),
        "embed_url": f"{site_url()}/embed/{poster['slug']}",
        "created_at": poster["created_at"],
        "updated_at": poster["updated_at"],
    }


def event_json_ld(poster, public_url: str, image_url: str | None) -> dict:
    data = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": poster["title"],
        "description": poster["description"],
        "url": public_url,
        "organizer": {
            "@type": "Organization",
            "name": "새롬고등학교",
            "url": site_url(),
        },
    }
    if poster["start_date"]:
        data["startDate"] = poster["start_date"]
    if poster["end_date"]:
        data["endDate"] = poster["end_date"]
    if image_url:
        data["image"] = image_url
    if poster["location"]:
        data["location"] = {"@type": "Place", "name": poster["location"]}
    return data


def send_webhooks(poster_dict: dict) -> None:
    urls = os.getenv("EXTERNAL_WEBHOOK_URLS", "").strip()
    if not urls:
        return
    payload = json.dumps(poster_dict, ensure_ascii=False).encode("utf-8")
    for raw in urls.split(","):
        url = raw.strip()
        if not url:
            continue
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except (urllib.error.URLError, TimeoutError) as exc:
            app.logger.warning("Webhook failed %s: %s", url, exc)


app.jinja_env.globals["poster_image_src"] = poster_image_src


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(db.UPLOAD_FOLDER, filename)


# ── 관리 화면 ──────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    posters = db.get_all_posters()
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template(
        "index.html",
        posters=posters,
        today=today,
        site_url=site_url(),
        categories=categories.get_category_options(),
        category_custom=categories.CUSTOM_OPTION,
        is_admin=auth.is_admin_logged_in(),
    )


@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("admin_password", "")
    if auth.login_admin(password):
        flash("관리자로 로그인했습니다. 비밀번호 없이 포스터를 삭제할 수 있습니다.", "success")
    else:
        flash("관리자 비밀번호가 올바르지 않습니다.", "error")
    return redirect(url_for("index"))


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    auth.logout_admin()
    flash("관리자 로그아웃되었습니다.", "success")
    return redirect(url_for("index"))


@app.route("/upload", methods=["POST"])
def upload():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category = categories.resolve_category(request.form)
    location = request.form.get("location", "").strip() or None
    start_date = request.form.get("start_date", "").strip() or None
    end_date = request.form.get("end_date", "").strip() or None
    detail_url = request.form.get("detail_url", "").strip() or None
    delete_pin = request.form.get("delete_pin", "").strip()
    photo = request.files.get("photo")

    if not title or not description:
        flash("제목과 설명은 필수입니다.", "error")
        return redirect(url_for("index"))

    if len(delete_pin) < 4:
        flash("삭제 비밀번호는 4자 이상 입력해 주세요.", "error")
        return redirect(url_for("index"))

    image_path = None
    image_url = None
    if photo and photo.filename:
        if not allowed_file(photo.filename):
            flash("png, jpg, jpeg, gif, webp 형식만 업로드할 수 있습니다.", "error")
            return redirect(url_for("index"))
        filename = secure_filename(photo.filename) or "poster.jpg"
        file_bytes = photo.read()
        content_type = photo.mimetype or "application/octet-stream"
        try:
            image_path, image_url = db.upload_image(file_bytes, filename, content_type)
        except Exception as exc:
            app.logger.exception("Supabase Storage 업로드 실패")
            flash(f"이미지 업로드에 실패했습니다: {exc}", "error")
            return redirect(url_for("index"))

    try:
        poster = db.insert_poster(
            {
                "title": title,
                "description": description,
                "category": category,
                "location": location,
                "start_date": start_date,
                "end_date": end_date,
                "detail_url": detail_url,
                "image_path": image_path,
                "image_url": image_url,
                "delete_pin_hash": auth.hash_delete_pin(delete_pin),
            }
        )
    except Exception as exc:
        app.logger.exception("Supabase 포스터 저장 실패")
        flash(f"포스터 저장에 실패했습니다: {exc}", "error")
        return redirect(url_for("index"))
    send_webhooks(poster_to_dict(poster))
    flash(f"포스터가 저장되었습니다! 공개 URL: {poster_public_url(poster)}", "success")
    return redirect(url_for("index"))


@app.route("/delete/<slug>", methods=["GET", "POST"])
def delete_poster(slug):
    if request.method == "GET":
        return redirect(url_for("index"))

    wants_json = (
        request.headers.get("X-Requested-With") == "fetch"
        or "application/json" in (request.headers.get("Accept") or "")
    )

    def fail(message: str, status: int = 400):
        if wants_json:
            return jsonify({"ok": False, "error": message}), status
        flash(message, "error")
        return redirect(url_for("index"))

    def ok(message: str):
        if wants_json:
            return jsonify({"ok": True, "message": message, "slug": slug})
        flash(message, "success")
        return redirect(url_for("index"))

    try:
        poster = db.get_poster_by_slug(slug)
    except Exception as exc:
        app.logger.exception("포스터 조회 실패")
        return fail(f"포스터를 불러오지 못했습니다: {exc}", 500)

    if not poster:
        return fail("포스터를 찾을 수 없습니다.", 404)

    password = request.form.get("delete_password", "").strip()
    try:
        allowed = auth.can_delete_poster(poster, password)
    except Exception:
        app.logger.exception("삭제 권한 확인 실패")
        return fail("삭제 확인 중 오류가 났습니다. 관리자 로그인 후 삭제해 주세요.", 500)

    if not allowed:
        if not poster.get("delete_pin_hash") and not auth.is_admin_logged_in():
            return fail("이 포스터에는 삭제 비밀번호가 없습니다. 관리자 로그인 후 삭제해 주세요.")
        return fail("삭제 비밀번호가 올바르지 않습니다. 등록 시 설정한 비밀번호만 사용할 수 있습니다.")

    try:
        db.delete_poster(slug)
    except Exception as exc:
        app.logger.exception("포스터 삭제 실패")
        return fail(f"삭제 중 오류가 발생했습니다: {exc}", 500)

    return ok(f"포스터 '{poster['title']}'가 삭제되었습니다.")


# ── 공개 포스터 페이지 ─────────────────────────────────────

@app.route("/p/<slug>")
def public_poster(slug):
    poster = db.get_poster_by_slug(slug)
    if not poster:
        abort(404)
    public = poster_public_url(poster)
    image = poster_image_url(poster, _external=True)
    return render_template(
        "poster.html",
        poster=poster,
        site_url=site_url(),
        public_url=public,
        image_url=image,
        event_json_ld=event_json_ld(poster, public, image),
    )


@app.route("/embed/<slug>")
def embed_poster(slug):
    poster = db.get_poster_by_slug(slug)
    if not poster:
        abort(404)
    return render_template(
        "embed.html",
        poster=poster,
        public_url=poster_public_url(poster),
        image_url=poster_image_url(poster, _external=True),
    )


# ── JSON API ────────────────────────────────────────────────

@app.route("/api/posters")
def api_posters():
    posters = [poster_to_dict(p) for p in db.get_all_posters()]
    return jsonify({"posters": posters, "count": len(posters)})


@app.route("/api/posters/<slug>")
def api_poster(slug):
    poster = db.get_poster_by_slug(slug)
    if not poster:
        abort(404)
    return jsonify(poster_to_dict(poster))


@app.route("/api/feed.json")
def api_feed():
    posters = [poster_to_dict(p) for p in db.get_all_posters()]
    return jsonify(
        {
            "site": site_url(),
            "title": "새롬고등학교 포스터 피드",
            "updated_at": datetime.now().isoformat(),
            "posters": posters,
        }
    )


# ── 검색/포털 노출용 피드 ───────────────────────────────────

@app.route("/sitemap.xml")
def sitemap():
    posters = db.get_all_posters()
    urls = [f"  <url><loc>{site_url()}/</loc></url>"]
    for p in posters:
        urls.append(f"  <url><loc>{poster_public_url(p)}</loc></url>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    return Response(xml, mimetype="application/xml")


@app.route("/rss.xml")
def rss_feed():
    posters = db.get_all_posters()
    items = []
    for p in posters:
        pub = (p["start_date"] or str(p["created_at"])[:10])
        desc = p["description"][:300].replace("&", "&amp;").replace("<", "&lt;")
        items.append(
            f"<item>"
            f"<title>{p['title']}</title>"
            f"<link>{poster_public_url(p)}</link>"
            f"<guid>{poster_public_url(p)}</guid>"
            f"<pubDate>{pub}</pubDate>"
            f"<description>{desc}</description>"
            f"</item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>새롬고등학교 포스터</title>"
        f"<link>{site_url()}</link>"
        f"<description>학교 행사·홍보 포스터 피드</description>"
        + "".join(items)
        + "</channel></rss>"
    )
    return Response(xml, mimetype="application/rss+xml")


@app.route("/robots.txt")
def robots():
    content = (
        f"User-agent: *\n"
        f"Allow: /\n"
        f"Sitemap: {site_url()}/sitemap.xml\n"
    )
    return Response(content, mimetype="text/plain")


if __name__ == "__main__":
    use_https = os.getenv("USE_HTTPS", "false").lower() in ("1", "true", "yes")
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "true").lower() in ("1", "true", "yes")
    scheme = "https" if use_https else "http"
    ssl_ctx = "adhoc" if use_https else None

    print(f" * 로컬 접속: {scheme}://{host}:{port}")
    print(" * 공개 배포는 Render/Fly.io 사용 → https://your-app.onrender.com 형태")

    app.run(debug=debug, host=host, port=port, ssl_context=ssl_ctx)

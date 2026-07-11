"""Supabase 데이터베이스 — 포스터 CRUD (poster-hub 프로젝트 연동)"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 로컬 임시 업로드 폴더 (Storage 전송 전 버퍼용 — 선택)
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")

STORAGE_BUCKET = "posters"

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL과 SUPABASE_KEY를 .env에 설정해 주세요. "
            "poster-hub에서 쓰던 Supabase 프로젝트 값을 넣으면 됩니다."
        )
    _client = create_client(url, key)
    return _client


def init_db() -> None:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    # 연결만 확인 (테이블은 supabase_schema.sql로 생성)
    get_supabase()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    title = (row.get("title") or row.get("club_name") or "").strip() or "제목 없음"
    description = (row.get("description") or row.get("event_content") or "").strip()
    image_url = row.get("image_url") or None
    image_path = row.get("image_path") or None
    # 템플릿·기존 코드는 image_path를 쓰므로, 공개 URL이 있으면 함께 맞춤
    display_image = image_url or image_path
    return {
        "id": row.get("id"),
        "slug": row.get("slug") or f"poster-{row.get('id')}",
        "title": title,
        "description": description,
        "category": row.get("category"),
        "location": row.get("location"),
        "start_date": row.get("start_date"),
        "end_date": row.get("end_date"),
        "detail_url": row.get("detail_url"),
        "image_path": display_image,
        "image_url": image_url or (display_image if _is_http(display_image) else None),
        "storage_path": image_path if image_path and not _is_http(image_path) else _storage_path_from_url(image_url),
        "delete_pin_hash": row.get("delete_pin_hash"),
        "created_at": row.get("created_at") or "",
        "updated_at": row.get("updated_at") or row.get("created_at") or "",
        "club_name": row.get("club_name"),
        "event_content": row.get("event_content"),
    }


def _is_http(value: str | None) -> bool:
    return bool(value and str(value).startswith(("http://", "https://")))


def _storage_path_from_url(url: str | None) -> str | None:
    if not url:
        return None
    marker = f"/object/public/{STORAGE_BUCKET}/"
    if marker in url:
        return url.split(marker, 1)[1].split("?", 1)[0]
    return None


def image_filename(image_path: str | None) -> str | None:
    """하위 호환 — 로컬 파일명 또는 Storage 경로/URL에서 식별자 추출."""
    if not image_path:
        return None
    if _is_http(image_path):
        return _storage_path_from_url(image_path) or image_path
    return image_path.replace("uploads/", "", 1).lstrip("/")


def make_slug(title: str) -> str:
    slug = re.sub(r"\s+", "-", title.strip())
    slug = re.sub(r"[^\w\-가-힣]", "", slug, flags=re.UNICODE)
    if not slug:
        slug = f"poster-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    base, n = slug, 1
    client = get_supabase()
    while True:
        existing = (
            client.table("posters")
            .select("id")
            .eq("slug", slug)
            .limit(1)
            .execute()
        )
        if not existing.data:
            return slug
        slug = f"{base}-{n}"
        n += 1


def upload_image(file_bytes: bytes, filename: str, content_type: str | None = None) -> tuple[str, str]:
    """Storage에 업로드 후 (storage_path, public_url) 반환."""
    client = get_supabase()
    safe = re.sub(r"[^\w.\-가-힣]", "_", filename, flags=re.UNICODE)
    storage_path = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe}"
    options: dict[str, str] = {"upsert": "false"}
    if content_type:
        options["content-type"] = content_type
    client.storage.from_(STORAGE_BUCKET).upload(storage_path, file_bytes, options)
    public_url = client.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)
    if isinstance(public_url, dict):
        public_url = (
            public_url.get("publicUrl")
            or public_url.get("public_url")
            or ""
        )
    return storage_path, str(public_url)


def delete_storage_object(storage_path: str | None) -> None:
    if not storage_path:
        return
    try:
        get_supabase().storage.from_(STORAGE_BUCKET).remove([storage_path])
    except Exception:
        pass


def insert_poster(data: dict) -> dict[str, Any]:
    client = get_supabase()
    now = _now_iso()
    slug = make_slug(data["title"])
    title = data["title"]
    description = data["description"]
    image_url = data.get("image_url")
    image_path = data.get("image_path")  # Storage object path

    payload = {
        "slug": slug,
        "title": title,
        "description": description,
        "category": data.get("category"),
        "location": data.get("location"),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "detail_url": data.get("detail_url"),
        "image_url": image_url,
        "image_path": image_path,
        "delete_pin_hash": data.get("delete_pin_hash"),
        "updated_at": now,
        # poster-hub 호환 필드
        "club_name": data.get("category") or title,
        "event_content": description,
    }

    result = client.table("posters").insert(payload).select("*").execute()
    if not result.data:
        raise RuntimeError("포스터 저장에 실패했습니다.")
    row = _as_dict(result.data[0])
    assert row is not None
    return row


def get_all_posters() -> list[dict[str, Any]]:
    result = (
        get_supabase()
        .table("posters")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return [d for row in (result.data or []) if (d := _as_dict(row))]


def get_poster_by_slug(slug: str) -> dict[str, Any] | None:
    result = (
        get_supabase()
        .table("posters")
        .select("*")
        .eq("slug", slug)
        .limit(1)
        .execute()
    )
    if result.data:
        return _as_dict(result.data[0])

    # 예전 poster-hub 행: slug가 없고 id만 있는 경우 /p/poster-123 형태 지원
    if slug.startswith("poster-"):
        try:
            poster_id = int(slug.removeprefix("poster-"))
        except ValueError:
            return None
        by_id = (
            get_supabase()
            .table("posters")
            .select("*")
            .eq("id", poster_id)
            .limit(1)
            .execute()
        )
        if by_id.data:
            return _as_dict(by_id.data[0])
    return None


def get_distinct_categories() -> list[str]:
    result = (
        get_supabase()
        .table("posters")
        .select("category")
        .neq("category", "")
        .execute()
    )
    seen: set[str] = set()
    categories: list[str] = []
    for row in result.data or []:
        cat = (row.get("category") or "").strip()
        if cat and cat not in seen:
            seen.add(cat)
            categories.append(cat)
    return sorted(categories)


def delete_poster(slug: str) -> bool:
    poster = get_poster_by_slug(slug)
    if not poster:
        return False

    storage_path = poster.get("storage_path")
    poster_id = poster.get("id")
    if poster_id is None:
        return False

    try:
        get_supabase().table("posters").delete().eq("id", poster_id).execute()
    except Exception as exc:
        raise RuntimeError(
            "Supabase 삭제 실패. SQL Editor에서 DELETE 정책(supabase_delete_policy.sql)을 실행해 주세요. "
            f"상세: {exc}"
        ) from exc

    try:
        delete_storage_object(storage_path)
    except Exception:
        pass
    return True

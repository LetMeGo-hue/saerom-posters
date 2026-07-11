"""카테고리 목록 — data/categories.json 수정으로 기본 항목 추가 가능"""

import json
import os

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CATEGORIES_FILE = os.path.join(BASE_DIR, "data", "categories.json")
CUSTOM_OPTION = "__custom__"


def load_default_categories() -> list[str]:
    if not os.path.exists(CATEGORIES_FILE):
        return []
    with open(CATEGORIES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return [str(item).strip() for item in data if str(item).strip()]


def get_distinct_categories_from_db() -> list[str]:
    return db.get_distinct_categories()


def get_category_options() -> list[str]:
    """기본 카테고리 + DB에 저장된 사용자 추가 카테고리"""
    defaults = load_default_categories()
    seen = set()
    options = []
    for cat in defaults + get_distinct_categories_from_db():
        if cat not in seen:
            seen.add(cat)
            options.append(cat)
    return options


def resolve_category(form) -> str | None:
    choice = form.get("category_choice", "").strip()
    custom = form.get("category_custom", "").strip()
    if choice == CUSTOM_OPTION:
        return custom or None
    return choice or None

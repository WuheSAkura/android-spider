from __future__ import annotations

from pathlib import Path
from typing import Any

from src.storage.analysis_store import AnalysisStore


class DictionaryService:
    """黑话字典服务。"""

    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path

    def list_categories(self) -> list[dict[str, Any]]:
        store = AnalysisStore(self.sqlite_path)
        try:
            return store.list_keyword_categories()
        finally:
            store.close()

    def create_category(self, *, name: str, description: str, sort_order: int) -> dict[str, Any]:
        store = AnalysisStore(self.sqlite_path)
        try:
            return store.create_keyword_category(name=name, description=description, sort_order=sort_order)
        finally:
            store.close()

    def update_category(self, category_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        store = AnalysisStore(self.sqlite_path)
        try:
            return store.update_keyword_category(category_id, payload)
        finally:
            store.close()

    def delete_category(self, category_id: int) -> None:
        store = AnalysisStore(self.sqlite_path)
        try:
            store.delete_keyword_category(category_id)
        finally:
            store.close()

    def create_subcategory(
        self,
        *,
        category_id: int,
        name: str,
        description: str,
        sort_order: int,
    ) -> dict[str, Any]:
        store = AnalysisStore(self.sqlite_path)
        try:
            return store.create_keyword_subcategory(
                category_id=category_id,
                name=name,
                description=description,
                sort_order=sort_order,
            )
        finally:
            store.close()

    def update_subcategory(self, subcategory_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        store = AnalysisStore(self.sqlite_path)
        try:
            return store.update_keyword_subcategory(subcategory_id, payload)
        finally:
            store.close()

    def delete_subcategory(self, subcategory_id: int) -> None:
        store = AnalysisStore(self.sqlite_path)
        try:
            store.delete_keyword_subcategory(subcategory_id)
        finally:
            store.close()

    def create_keyword(
        self,
        *,
        category_id: int,
        subcategory_id: int,
        keyword: str,
        meaning: str,
        sort_order: int,
    ) -> dict[str, Any]:
        store = AnalysisStore(self.sqlite_path)
        try:
            return store.create_keyword(
                category_id=category_id,
                subcategory_id=subcategory_id,
                keyword=keyword,
                meaning=meaning,
                sort_order=sort_order,
            )
        finally:
            store.close()

    def update_keyword(self, keyword_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        store = AnalysisStore(self.sqlite_path)
        try:
            return store.update_keyword(keyword_id, payload)
        finally:
            store.close()

    def delete_keyword(self, keyword_id: int) -> None:
        store = AnalysisStore(self.sqlite_path)
        try:
            store.delete_keyword(keyword_id)
        finally:
            store.close()

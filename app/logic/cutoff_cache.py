"""In-memory cache for cutoff records with disk snapshot fallback."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("app.logic.cutoff_cache")


class CutoffCache:
    """Thread-safe cache storing the full cutoff dataset in memory."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rows: list[dict] = []
        self._last_refresh_ts: float = 0.0
        self._last_source: str = "empty"

    def _normalise_row(self, row: dict) -> dict:
        normalized = dict(row)

        if "category" not in normalized and "caste" in normalized:
            normalized["category"] = normalized.get("caste")

        if "last_rank" not in normalized:
            if "cutoff_rank" in normalized:
                normalized["last_rank"] = normalized.get("cutoff_rank")
            elif "first_rank" in normalized:
                normalized["last_rank"] = normalized.get("first_rank")

        if "cutoff_rank" not in normalized:
            normalized["cutoff_rank"] = normalized.get("last_rank")

        for key in ("year", "round", "first_rank", "last_rank", "cutoff_rank"):
            value = normalized.get(key)
            if value is None:
                continue
            try:
                normalized[key] = int(value)
            except (TypeError, ValueError):
                normalized[key] = None

        for key in ("branch", "category", "gender", "quota"):
            value = normalized.get(key)
            if value is None:
                continue
            normalized[key] = str(value).strip()

        return normalized

    def _replace_rows(self, rows: list[dict], source: str) -> None:
        normalized = [self._normalise_row(row) for row in rows]
        with self._lock:
            self._rows = normalized
            self._last_refresh_ts = time.time()
            self._last_source = source

    def save_snapshot(self, snapshot_path: str | Path) -> None:
        path = Path(snapshot_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "meta": {
                    "last_refresh_ts": self._last_refresh_ts,
                    "last_source": self._last_source,
                    "record_count": len(self._rows),
                },
                "rows": self._rows,
            }
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def load_snapshot(self, snapshot_path: str | Path) -> bool:
        path = Path(snapshot_path)
        if not path.exists():
            return False

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("rows") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                logger.warning("Invalid cutoff snapshot format in %s", path)
                return False
            self._replace_rows(rows, source="snapshot")
            return True
        except Exception as exc:
            logger.error("Failed to load cutoff snapshot %s: %s", path, exc)
            return False

    def refresh_from_firestore(
        self,
        get_db_func: Callable[[], object | None],
        collection_name: str,
        snapshot_path: str | Path | None = None,
    ) -> bool:
        try:
            db = get_db_func()
            if db is None:
                logger.warning("Firestore unavailable, cutoff cache refresh skipped")
                return False

            docs = db.collection(collection_name).stream()
            rows = [doc.to_dict() for doc in docs]
            self._replace_rows(rows, source="firestore")
            if snapshot_path:
                self.save_snapshot(snapshot_path)

            logger.info("Cutoff cache refreshed from Firestore with %s rows", len(rows))
            return True
        except Exception as exc:
            logger.error("Failed refreshing cutoff cache from Firestore: %s", exc)
            return False

    def hydrate(
        self,
        get_db_func: Callable[[], object | None],
        collection_name: str,
        snapshot_path: str | Path,
        fallback_rows: list[dict],
    ) -> str:
        if self.refresh_from_firestore(get_db_func, collection_name, snapshot_path=snapshot_path):
            return "firestore"

        if self.load_snapshot(snapshot_path):
            logger.info("Cutoff cache hydrated from snapshot")
            return "snapshot"

        self._replace_rows(fallback_rows, source="seed")
        try:
            self.save_snapshot(snapshot_path)
        except Exception as exc:
            logger.warning("Failed writing fallback cutoff snapshot: %s", exc)
        logger.info("Cutoff cache hydrated from embedded seed data")
        return "seed"

    def query(
        self,
        *,
        branch: str | None = None,
        category: str | None = None,
        gender: str | None = None,
        year: int | None = None,
        round_num: int | None = None,
        quota: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        with self._lock:
            source_rows = list(self._rows)

        out: list[dict] = []
        for row in source_rows:
            if branch and str(row.get("branch") or "") != branch:
                continue
            if category and str(row.get("category") or "") != category:
                continue
            if gender and str(row.get("gender") or "") != gender:
                continue
            if year and int(row.get("year") or 0) != int(year):
                continue
            if round_num and int(row.get("round") or 0) != int(round_num):
                continue
            if quota and str(row.get("quota") or "") != quota:
                continue
            out.append(dict(row))

        out.sort(
            key=lambda r: (
                r.get("year", 0),
                r.get("branch", ""),
                r.get("category", ""),
                r.get("round", 0),
            ),
            reverse=True,
        )

        if limit and limit > 0:
            return out[:limit]
        return out

    def list_branches(self, quota: str | None = None) -> list[str]:
        with self._lock:
            rows = list(self._rows)
        values = {
            str(row.get("branch") or "").strip()
            for row in rows
            if row.get("branch") and (not quota or str(row.get("quota") or "") == quota)
        }
        return sorted(values)

    def list_categories(self, branch: str | None = None, quota: str | None = None) -> list[str]:
        with self._lock:
            rows = list(self._rows)
        values = {
            str(row.get("category") or "").strip()
            for row in rows
            if row.get("category")
            and (not branch or str(row.get("branch") or "") == branch)
            and (not quota or str(row.get("quota") or "") == quota)
        }
        return sorted(values)

    def list_genders(
        self,
        branch: str | None = None,
        category: str | None = None,
        quota: str | None = None,
    ) -> list[str]:
        with self._lock:
            rows = list(self._rows)
        values = {
            str(row.get("gender") or "").strip()
            for row in rows
            if row.get("gender")
            and (not branch or str(row.get("branch") or "") == branch)
            and (not category or str(row.get("category") or "") == category)
            and (not quota or str(row.get("quota") or "") == quota)
        }
        return sorted(values)

    def list_years(
        self,
        branch: str | None = None,
        category: str | None = None,
        gender: str | None = None,
        quota: str | None = None,
    ) -> list[int]:
        with self._lock:
            rows = list(self._rows)

        years: set[int] = set()
        for row in rows:
            if branch and str(row.get("branch") or "") != branch:
                continue
            if category and str(row.get("category") or "") != category:
                continue
            if gender and str(row.get("gender") or "") != gender:
                continue
            if quota and str(row.get("quota") or "") != quota:
                continue
            year = row.get("year")
            if year is None:
                continue
            try:
                years.add(int(year))
            except (TypeError, ValueError):
                continue

        return sorted(years, reverse=True)

    def stats(self) -> dict:
        with self._lock:
            return {
                "record_count": len(self._rows),
                "last_refresh_ts": self._last_refresh_ts,
                "last_source": self._last_source,
            }


_CACHE = CutoffCache()


def get_cutoff_cache() -> CutoffCache:
    return _CACHE


def hydrate_cutoff_cache(
    *,
    get_db_func: Callable[[], object | None],
    collection_name: str,
    snapshot_path: str | Path,
    fallback_rows: list[dict],
) -> str:
    return _CACHE.hydrate(
        get_db_func=get_db_func,
        collection_name=collection_name,
        snapshot_path=snapshot_path,
        fallback_rows=fallback_rows,
    )


def refresh_cutoff_cache_from_firestore(
    *,
    get_db_func: Callable[[], object | None],
    collection_name: str,
    snapshot_path: str | Path | None = None,
) -> bool:
    return _CACHE.refresh_from_firestore(
        get_db_func=get_db_func,
        collection_name=collection_name,
        snapshot_path=snapshot_path,
    )

"""客户端事件采集与批量上报管理"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional

from .backend_client import BackendClient
from .config import SettingsManager

logger = logging.getLogger(__name__)


class AnalyticsManager:
    """轻量级事件队列，支持定期批量上报"""

    def __init__(self, settings_manager: SettingsManager) -> None:
        self._settings_manager = settings_manager
        self._analytics_config = settings_manager.settings.analytics
        self._backend_client = BackendClient(settings_manager)
        self._queue: Deque[Dict] = deque()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

        self._cache_enabled = bool(getattr(self._analytics_config, "cache_enabled", True))
        max_cache = int(getattr(self._analytics_config, "max_cache_events", self._analytics_config.max_queue_size))
        self._max_cache_events = max(max_cache, self._analytics_config.max_queue_size, 1)
        self._retry_backoff = max(float(getattr(self._analytics_config, "retry_backoff_seconds", 1.0)), 0.5)
        self._cache_path: Optional[Path] = None
        if self._cache_enabled:
            cache_name = getattr(self._analytics_config, "cache_file", "analytics_cache.json")
            settings_path = getattr(self._settings_manager, "path", None)
            base_dir = None
            if isinstance(settings_path, Path):
                base_dir = settings_path.parent
            else:
                try:
                    base_dir = Path(settings_path).parent  # type: ignore[arg-type]
                except Exception:
                    base_dir = None
            if base_dir is None:
                base_dir = Path.home()
            self._cache_path = base_dir / cache_name
            loaded = self._load_cached_events()
            if loaded:
                logger.info("AnalyticsManager 从离线缓存恢复 %s 条事件", loaded)

        if self._analytics_config.enabled:
            self._worker = threading.Thread(target=self._flush_loop, name="AnalyticsFlusher", daemon=True)
            self._worker.start()
            logger.info("AnalyticsManager 启动，队列大小限制 %s", self._analytics_config.max_queue_size)
        else:
            logger.info("AnalyticsManager 已禁用")

    def track(self, name: str, properties: Optional[Dict] = None) -> None:
        if not self._analytics_config.enabled:
            return

        event = {
            "name": name,
            "properties": properties.copy() if properties else {},
            "timestamp": time.time(),
            "client_ts": datetime.now(timezone.utc).isoformat(),
        }

        dropped = None
        with self._lock:
            if self._analytics_config.max_queue_size and len(self._queue) >= self._analytics_config.max_queue_size:
                dropped = self._queue.popleft()
            self._queue.append(event)
            queue_size = len(self._queue)

        if dropped:
            if self._cache_enabled:
                logger.debug("事件队列已满，将最早事件写入离线缓存: %s", dropped.get("name"))
                self._update_cache(prepend=[dropped])
            else:
                logger.debug("事件队列已满，丢弃最早事件: %s", dropped.get("name"))

        threshold = max(int(self._analytics_config.max_queue_size * 0.8), 1)
        if queue_size >= threshold or (
            self._cache_enabled and queue_size >= self._max_cache_events
        ):
            self.flush()

    def flush(self) -> None:
        if not self._analytics_config.enabled:
            return

        while True:
            with self._lock:
                if self._queue:
                    batch = list(self._queue)
                    self._queue.clear()
                else:
                    batch = None

            if not batch:
                if self._cache_enabled:
                    loaded = self._load_cached_events()
                    if loaded:
                        logger.debug("离线缓存回填 %s 条事件，继续刷新", loaded)
                        continue
                    self._persist_cache()
                return

            success = self._post_with_retry(batch)
            if not success:
                logger.warning("事件上报多次失败，将事件重新放回队列并写入缓存")
                with self._lock:
                    for event in reversed(batch):
                        self._queue.appendleft(event)
                if self._cache_enabled:
                    self._persist_cache()
                return

            if self._cache_enabled:
                self._persist_cache()

    def _post_with_retry(self, batch: List[Dict]) -> bool:
        success = self._backend_client.post_events(batch)
        if success:
            return True

        retry_left = max(int(self._analytics_config.max_retry), 0)
        backoff = self._retry_backoff
        while retry_left > 0 and not success:
            time.sleep(backoff)
            success = self._backend_client.post_events(batch)
            retry_left -= 1
            backoff = min(backoff * 2, 30.0)
        return success

    def _persist_cache(self) -> None:
        if not self._cache_enabled or not self._cache_path:
            return

        with self._lock:
            snapshot = list(self._queue)

        self._update_cache(snapshot=snapshot)

    def _event_cache_key(self, event: Dict) -> str:
        try:
            return json.dumps(event, sort_keys=True, ensure_ascii=False)
        except TypeError:
            return str(event)

    def _update_cache(
        self,
        *,
        snapshot: Optional[List[Dict]] = None,
        prepend: Optional[List[Dict]] = None,
    ) -> None:
        if not self._cache_enabled or not self._cache_path:
            return

        existing: List[Dict] = []
        if self._cache_path.exists():
            try:
                with self._cache_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, list):
                    existing = data
            except Exception as exc:
                logger.warning("读取离线缓存失败，将重建缓存: %s", exc)
                existing = []

        combined: List[Dict] = []
        seen = set()

        sources: List[List[Dict]] = []
        if prepend:
            sources.append(prepend)
        if existing:
            sources.append(existing)
        if snapshot is not None:
            sources.append(snapshot)

        for source in sources:
            for event in source:
                if not isinstance(event, dict):
                    continue
                key = self._event_cache_key(event)
                if key in seen:
                    continue
                combined.append(event)
                seen.add(key)

        if not combined:
            try:
                if self._cache_path.exists():
                    self._cache_path.unlink()
            except OSError as exc:
                logger.debug("清理离线缓存失败: %s", exc)
            return

        combined = combined[: self._max_cache_events]
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._cache_path.with_name(self._cache_path.name + ".tmp")
            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(combined, fh, ensure_ascii=False)
            tmp_path.replace(self._cache_path)
        except Exception as exc:
            logger.warning("写入离线缓存失败: %s", exc)

    def _load_cached_events(self) -> int:
        if not self._cache_enabled or not self._cache_path or not self._cache_path.exists():
            return 0

        try:
            with self._cache_path.open("r", encoding="utf-8") as fh:
                cached = json.load(fh)
            if not isinstance(cached, list):
                cached = []
            cached = cached[: self._max_cache_events]
            if not cached:
                self._cache_path.unlink()
                return 0

            with self._lock:
                for event in reversed(cached):
                    self._queue.appendleft(event)
            self._cache_path.unlink()
            return len(cached)
        except Exception as exc:
            logger.warning("离线缓存恢复失败，将删除缓存文件: %s", exc)
            try:
                self._cache_path.unlink()
            except Exception:
                pass
            return 0

    def _flush_loop(self) -> None:
        interval = max(self._analytics_config.flush_interval_seconds, 1.0)
        while not self._stop_event.wait(interval):
            try:
                self.flush()
            except Exception as exc:
                logger.error("定时上报失败: %s", exc)

    def shutdown(self) -> None:
        if not self._analytics_config.enabled:
            return

        self._stop_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        self.flush()
        if self._cache_enabled:
            self._persist_cache()
        self._backend_client.close()

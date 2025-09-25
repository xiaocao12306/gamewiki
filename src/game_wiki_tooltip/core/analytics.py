"""客户端事件采集与批量上报管理"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional

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
            "properties": properties or {},
            "timestamp": time.time(),
        }

        with self._lock:
            if len(self._queue) >= self._analytics_config.max_queue_size:
                # 丢弃最早的事件，保证队列不会无限增长
                dropped = self._queue.popleft()
                logger.debug("事件队列已满，丢弃最早事件: %s", dropped.get("name"))
            self._queue.append(event)

        # 当队列接近满载时尝试主动刷新一次
        if len(self._queue) >= self._analytics_config.max_queue_size * 0.8:
            self.flush()

    def flush(self) -> None:
        if not self._analytics_config.enabled:
            return

        with self._lock:
            if not self._queue:
                return
            batch = list(self._queue)
            self._queue.clear()

        success = self._backend_client.post_events(batch)
        if not success:
            # 失败则按重试策略重新入队（简单回退一次）
            retry_left = self._analytics_config.max_retry
            while retry_left > 0 and not success:
                time.sleep(1)
                success = self._backend_client.post_events(batch)
                retry_left -= 1

            if not success:
                logger.warning("事件上报多次失败，将事件重新放回队列")
                with self._lock:
                    for event in batch:
                        if len(self._queue) < self._analytics_config.max_queue_size:
                            self._queue.appendleft(event)
                        else:
                            break

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
        self._backend_client.close()


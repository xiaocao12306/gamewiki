"""后端 API 客户端：负责远程配置获取与事件上报"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests

from .config import SettingsManager

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self, settings_manager: SettingsManager) -> None:
        self._settings_manager = settings_manager
        self._session = requests.Session()

    @property
    def _backend_config(self):
        return self._settings_manager.settings.backend

    def _build_url(self, path: str) -> Optional[str]:
        base_url = self._backend_config.resolved_base_url().rstrip("/")
        if not base_url:
            return None
        return urljoin(f"{base_url}/", path.lstrip("/"))

    def _default_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"User-Agent": "GameWiki-MVP/0.1"}
        api_key = self._backend_config.resolved_api_key()
        if api_key:
            headers["x-api-key"] = api_key
            masked = f"{api_key[:4]}***{api_key[-2:]}" if len(api_key) > 6 else "***"
            logger.info("BackendClient 已加载 API Key: %s", masked)
        else:
            logger.warning("BackendClient 未找到 API Key，将无法访问需要认证的接口")
        return headers

    def fetch_remote_config(self) -> Optional[Dict]:
        endpoint = self._backend_config.config_endpoint
        url = self._build_url(endpoint)
        if not url:
            logger.warning("后端 base_url 未配置，跳过远程配置拉取")
            return None

        try:
            response = self._session.get(
                url,
                headers=self._default_headers(),
                timeout=self._backend_config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            logger.info("远程配置获取成功")
            return data
        except Exception as exc:
            logger.warning("远程配置获取失败：%s", exc)
            return None

    def post_events(self, events: List[Dict]) -> bool:
        if not events:
            return True

        endpoint = self._backend_config.events_endpoint
        url = self._build_url(endpoint)
        if not url:
            logger.debug("后端 base_url 未配置，事件不上报")
            return False

        payload = {"events": events}
        try:
            response = self._session.post(
                url,
                json=payload,
                headers=self._default_headers(),
                timeout=self._backend_config.timeout,
            )
            response.raise_for_status()
            logger.debug("成功上报 %s 条事件", len(events))
            return True
        except Exception as exc:
            logger.warning("事件上报失败：%s", exc)
            return False

    def close(self) -> None:
        self._session.close()

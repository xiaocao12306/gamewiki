"""后端 API 客户端：负责远程配置获取与事件上报"""

from __future__ import annotations

import logging
import os
import socket
import hashlib
import platform
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests

from .config import SettingsManager

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self, settings_manager: SettingsManager) -> None:
        self._settings_manager = settings_manager
        self._session = requests.Session()
        # 生成稳定的设备指纹，供后端速率/配额控制与埋点使用
        raw_device = f"{platform.node()}|{platform.system()}|{platform.release()}|{uuid.getnode()}"
        self._device_id = hashlib.sha256(raw_device.encode()).hexdigest()[:16]
        self._client_version = "1.0.0"
        self._local_ip = self._resolve_local_ip()

    @property
    def _backend_config(self):
        return self._settings_manager.settings.backend

    def _build_url(self, path: str) -> Optional[str]:
        base_url = self._backend_config.resolved_base_url().rstrip("/")
        if not base_url:
            return None
        return urljoin(f"{base_url}/", path.lstrip("/"))

    def _resolve_local_ip(self) -> str:
        """推断当前设备用于访问后端的真实出口 IP"""

        # 允许通过环境变量强制指定，便于桌面环境无法自动判断时使用
        explicit_ip = os.getenv("GW_DEVICE_IP")
        if explicit_ip:
            return explicit_ip

        try:
            base_url = self._backend_config.resolved_base_url()
            hostname = urlparse(base_url).hostname or "8.8.8.8"
            port = 80
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(0.2)
                sock.connect((hostname, port))
                candidate = sock.getsockname()[0]
                if candidate and not candidate.startswith("127."):
                    return candidate
        except Exception as exc:
            logger.debug(f"Failed to detect local ip automatically: {exc}")

        # 兜底返回回环地址，至少保证字段存在
        return "127.0.0.1"

    def _default_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "User-Agent": "Guidor-MVP/0.1",
            "x-device-id": self._device_id,
            "x-app-version": self._client_version,
            "x-platform": platform.system().lower(),
        }
        api_key = self._backend_config.resolved_api_key()
        if api_key:
            headers["x-api-key"] = api_key
            masked = f"{api_key[:4]}***{api_key[-2:]}" if len(api_key) > 6 else "***"
            logger.info("BackendClient 已加载 API Key: %s", masked)
        else:
            logger.warning("BackendClient 未找到 API Key，将无法访问需要认证的接口")
        return headers

    def telemetry_context(self) -> Dict[str, Any]:
        """生成埋点与通用请求需要携带的设备信息"""

        return {
            "device_id": self._device_id,
            "device_name": platform.node(),
            "device_platform": platform.platform(),
            "app_version": self._client_version,
            # 使用推断的本机出口 IP，服务端可结合请求头再次校验
            "ip": self._local_ip,
        }

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

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: Optional[float] = None,
        include_raw: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """调用后端聊天代理"""

        endpoint = getattr(self._backend_config, "chat_endpoint", "/api/v1/chat")
        url = self._build_url(endpoint)
        if not url:
            logger.error("后端 base_url 未配置，无法调用聊天接口")
            return None

        payload: Dict[str, Any] = {"messages": messages, "include_raw": include_raw}
        if model:
            payload["model"] = model
        if provider:
            payload["provider"] = provider
        if temperature is not None:
            payload["temperature"] = temperature

        try:
            response = self._session.post(
                url,
                json=payload,
                headers=self._default_headers(),
                timeout=max(self._backend_config.timeout, 60.0),
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "云端模型响应成功 provider=%s model=%s",
                data.get("provider"),
                data.get("model"),
            )
            return data
        except Exception as exc:
            logger.warning("云端模型调用失败：%s", exc)
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

"""QuotaManager: 客户端配额与A/B实验分流管理

职责：
- 从 SettingsManager 读取/写入 usage_quota 状态
- 解析远程配置 paywall_points，生成 QuotaConfig
- 基于 device_id+cohort_seed 做稳定分流
- 维护 total/daily/since_last_paywall 计数与冷却判断
- 向上层返回 QuotaDecision，驱动 UI 与埋点

注意：
- 本模块仅做逻辑与持久化，不直接依赖 UI 组件
- 失败时使用 DEFAULT_STATE 与安全兜底，不让调用方崩溃
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from copy import deepcopy

from .backend_client import BackendClient
from .config import SettingsManager


# ----------------- 类型定义 -----------------

@dataclass
class QuotaConfig:
    plan_id: Optional[str]
    variant: Optional[str]  # 实际生效的分组（control/points/...），供 UI/埋点使用
    total_limit: Optional[int]
    daily_limit: Optional[int]  # None 表示不限制每日
    cooldown_minutes: int
    grace_messages: int
    restrictions: Dict[str, Any]
    copy: Dict[str, Any]
    cta: Any


@dataclass
class QuotaDecision:
    blocked: bool
    reason: str
    analytics_payload: Dict[str, Any]
    variant: Optional[str]
    config: QuotaConfig
    cooldown_seconds: Optional[int] = None


class QuotaManager:
    """配额与实验分流管理器"""

    DEFAULT_STATE: Dict[str, Any] = {
        "cohort": {"variant": None, "assigned_at": None, "plan_id": None},
        "counters": {
            "total": 0,
            "daily": {"date": None, "count": 0},
            "since_last_paywall": 0,
        },
        "last_trigger": {"shown_at": None, "trigger_count": 0},
    }

    DEFAULT_PAYWALL_CONFIG: Dict[str, Any] = {
        "plan_id": "points_default",
        "experiment": {
            "cohort_seed": "local-default",
            "allocation": [
                {"variant": "points", "weight": 70},
                {"variant": "subscription", "weight": 30},
            ],
            "fallback_variant": "points",
        },
        "quota": {
            "total_limit": 20,
            "daily_limit": None,
            "cooldown_minutes": 30,
            "grace_messages": 0,
        },
        "copy": {
            "title": "AI 使用次数已达上限",
            "body": "升级套餐或稍后重试，以继续使用 AI 服务。",
            "highlight": "获取更多积分即可立即解锁",
        },
        "cta": [
            {
                "label": "了解积分套餐",
                "action": "open_url",
                "payload": "https://example.com/points",
                "value": "points_pack_default",
            }
        ],
        "restrictions": {
            "disable_chat_after_trigger": True,
            "show_reminder_on_close": True,
        },
        "layout": {
            "theme": "light",
            "illustration": None,
        },
    }

    DEFAULT_SUBSCRIPTION_CONFIG: Dict[str, Any] = {
        "plan_id": "subscription_default",
        "quota": {
            "total_limit": 20,
            "daily_limit": None,
            "cooldown_minutes": 30,
            "grace_messages": 0,
        },
        "copy": {
            "title": "解锁完整订阅权益",
            "body": "订阅即享无限次 AI 指导、专属攻略与同步更新。",
            "highlight": "立即订阅，体验旗舰功能",
        },
        "cta": [
            {
                "label": "订阅月度计划（¥29）",
                "action": "open_url",
                "payload": "https://example.com/subscription/monthly",
                "value": "subscription_monthly",
            }
        ],
        "restrictions": {
            "disable_chat_after_trigger": True,
            "show_reminder_on_close": True,
        },
        "layout": {
            "theme": "light",
            "illustration": None,
        },
    }

    def __init__(self, settings_manager: SettingsManager, backend_client: BackendClient) -> None:
        self._settings = settings_manager
        self._backend = backend_client
        self._state = self.load_state()
        self._remote_config: Dict[str, Any] = {}
        self._variant_configs: Dict[str, Dict[str, Any]] = {}

        remote = getattr(self._settings.settings, "remote_config", {}) or {}
        self._remote_config = remote
        self._config = self.refresh_config(remote)

        # 确保分组已分配
        self.assign_variant(remote)
        # 分配完成后按变体刷新配置
        self._config = self.refresh_config(remote, override_variant=(self._state.get("cohort", {}) or {}).get("variant"))

    # ----------------- 基础读写 -----------------
    def load_state(self) -> Dict[str, Any]:
        try:
            data = getattr(self._settings.settings, "usage_quota", None)
            if not isinstance(data, dict) or not data:
                return deepcopy(self.DEFAULT_STATE)
            # 合并默认键，避免旧版本缺字段
            merged = deepcopy(QuotaManager.DEFAULT_STATE)
            merged.update({k: data.get(k, v) for k, v in QuotaManager.DEFAULT_STATE.items()})
            # 深层 keys 简化处理
            if "counters" in data:
                merged["counters"].update(data["counters"])  # type: ignore
            if "last_trigger" in data:
                merged["last_trigger"].update(data["last_trigger"])  # type: ignore
            if "cohort" in data:
                merged["cohort"].update(data["cohort"])  # type: ignore
            return merged
        except Exception:
            return deepcopy(self.DEFAULT_STATE)

    def save_state(self) -> None:
        try:
            self._settings.update({"usage_quota": self._state})
            self._settings.save()
        except Exception:
            # 保存失败仅记录，避免影响主流程
            pass

    # ----------------- 时间/哈希工具 -----------------
    @staticmethod
    def get_now_iso() -> str:
        return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

    @staticmethod
    def get_today() -> str:
        return datetime.utcnow().date().isoformat()

    @staticmethod
    def hash_variant(device_id: str, allocation: Any, cohort_seed: str) -> Optional[str]:
        try:
            weights = [int(x.get("weight", 0)) for x in allocation if int(x.get("weight", 0)) > 0]
            if not weights:
                return None
            total = sum(weights)
            m = hashlib.sha256()
            m.update(f"{device_id}|{cohort_seed}".encode("utf-8"))
            mod = int(m.hexdigest(), 16) % total
            # 命中区间
            acc = 0
            for item in allocation:
                w = int(item.get("weight", 0))
                if w <= 0:
                    continue
                if acc <= mod < acc + w:
                    return item.get("variant")
                acc += w
            return None
        except Exception:
            return None

    # ----------------- 配置刷新与分组 -----------------
    @staticmethod
    def _merge_dict(default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(override, dict):
            return deepcopy(default)

        merged = deepcopy(default)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = QuotaManager._merge_dict(merged[key], value)
            else:
                merged[key] = value
        return merged

    def refresh_config(
        self,
        remote_config: Dict[str, Any],
        *,
        override_variant: Optional[str] = None,
    ) -> QuotaConfig:
        self._remote_config = remote_config or {}

        points_raw = (self._remote_config or {}).get("paywall_points", {}) or {}
        subscription_raw = (self._remote_config or {}).get("paywall_subscription", {}) or {}

        points_cfg = self._merge_dict(self.DEFAULT_PAYWALL_CONFIG, points_raw)
        subscription_cfg = self._merge_dict(self.DEFAULT_SUBSCRIPTION_CONFIG, subscription_raw)
        self._variant_configs = {
            "points": points_cfg,
            "subscription": subscription_cfg,
        }

        fallback_variant = (
            override_variant
            or (self._state.get("cohort", {}) or {}).get("variant")
            or points_cfg.get("experiment", {}).get("fallback_variant")
            or "points"
        )
        selected_cfg = self._variant_configs.get(fallback_variant) or points_cfg

        quota = selected_cfg.get("quota", {}) or {}
        total_limit = quota.get("total_limit")
        daily_limit = quota.get("daily_limit")
        cooldown_minutes = int(quota.get("cooldown_minutes", 30) or 30)
        grace_messages = int(quota.get("grace_messages", 0) or 0)

        restrictions = selected_cfg.get("restrictions", {}) or {
            "disable_chat_after_trigger": True,
            "show_reminder_on_close": True,
        }
        copy = selected_cfg.get("copy", {}) or {}
        cta = selected_cfg.get("cta", []) or []

        config = QuotaConfig(
            plan_id=selected_cfg.get("plan_id") or points_cfg.get("plan_id"),
            variant=fallback_variant,
            total_limit=total_limit,
            daily_limit=daily_limit,
            cooldown_minutes=cooldown_minutes,
            grace_messages=grace_messages,
            restrictions=restrictions,
            copy=copy,
            cta=cta,
        )

        return config

    def assign_variant(self, remote_config: Dict[str, Any]) -> None:
        points_raw = (remote_config or {}).get("paywall_points", {}) or {}
        points = self._variant_configs.get("points") or self._merge_dict(self.DEFAULT_PAYWALL_CONFIG, points_raw)
        plan_id = points.get("plan_id")
        experiment = points.get("experiment", {}) or {}
        cohort_seed = experiment.get("cohort_seed") or "default-seed"
        allocation = experiment.get("allocation", []) or []
        fallback_variant = experiment.get("fallback_variant", "points")

        cohort = self._state.get("cohort", {})
        current_plan = cohort.get("plan_id")
        current_variant = cohort.get("variant")

        # 当 plan 变化或未分配时，重新分配变体
        if (not current_variant) or (plan_id and current_plan != plan_id):
            device_id = (self._backend.telemetry_context() or {}).get("device_id", "unknown")
            chosen = self.hash_variant(device_id, allocation, cohort_seed) or fallback_variant

            # 记录分配
            self._state["cohort"] = {
                "variant": chosen,
                "assigned_at": self.get_now_iso(),
                "plan_id": plan_id,
            }

            # 若 plan 变化，重置计数
            if plan_id and current_plan and current_plan != plan_id:
                self._state["counters"] = {
                    "total": 0,
                    "daily": {"date": None, "count": 0},
                    "since_last_paywall": 0,
                }
            self.save_state()

        # 同步 config.variant
        self._config = self.refresh_config(remote_config, override_variant=self._state.get("cohort", {}).get("variant"))

    # ----------------- 计数与决策 -----------------
    def reset_daily_counter(self) -> None:
        today = self.get_today()
        daily = self._state["counters"]["daily"]
        if daily.get("date") != today:
            daily["date"] = today
            daily["count"] = 0

    def increment_usage(self) -> None:
        self.reset_daily_counter()
        self._state["counters"]["total"] = int(self._state["counters"].get("total", 0)) + 1
        self._state["counters"]["daily"]["count"] = int(self._state["counters"]["daily"].get("count", 0)) + 1
        self._state["counters"]["since_last_paywall"] = int(self._state["counters"].get("since_last_paywall", 0)) + 1
        self.save_state()

    def _cooldown_blocked(self) -> Tuple[bool, Optional[int]]:
        """检查冷却，返回(是否阻断, 剩余秒数)"""
        shown_at = (self._state.get("last_trigger", {}) or {}).get("shown_at")
        if not shown_at:
            return False, None

        try:
            last = datetime.fromisoformat(shown_at)
        except Exception:
            return False, None

        gap = datetime.utcnow().replace(tzinfo=timezone.utc) - last.replace(tzinfo=timezone.utc)
        cooldown_seconds = max(int(self._config.cooldown_minutes) * 60, 0)
        if gap.total_seconds() < cooldown_seconds:
            return True, int(cooldown_seconds - gap.total_seconds())
        return False, None

    def should_show_paywall(self) -> QuotaDecision:
        self.reset_daily_counter()

        total = int(self._state["counters"].get("total", 0))
        daily = int(self._state["counters"]["daily"].get("count", 0))
        since_last = int(self._state["counters"].get("since_last_paywall", 0))

        # control 变体：直接放行
        if (self._state.get("cohort", {}) or {}).get("variant") == "control":
            return QuotaDecision(
                blocked=False,
                reason="control_variant",
                analytics_payload=self.build_analytics_payload({}),
                variant="control",
                config=self._config,
            )

        # 冷却检查
        is_cooldown, remaining = self._cooldown_blocked()
        if is_cooldown:
            return QuotaDecision(
                blocked=True,
                reason="cooldown",
                analytics_payload=self.build_analytics_payload({"cooldown": True}),
                variant=self._state.get("cohort", {}).get("variant"),
                config=self._config,
                cooldown_seconds=remaining,
            )

        # 阈值判断
        blocked = False
        reason = ""
        if self._config.total_limit is not None and total >= int(self._config.total_limit):
            blocked = True
            reason = "total_limit"
        if (not blocked) and (self._config.daily_limit is not None) and daily >= int(self._config.daily_limit):
            blocked = True
            reason = "daily_limit"
        if (not blocked) and self._config.grace_messages > 0 and since_last > self._config.grace_messages:
            # grace_messages 仅在已触发之后继续限制
            blocked = True
            reason = "grace_exceeded"

        return QuotaDecision(
            blocked=blocked,
            reason=reason or ("ok" if not blocked else "blocked"),
            analytics_payload=self.build_analytics_payload({
                "trigger_total": int(self._state.get("last_trigger", {}).get("trigger_count", 0)),
                "trigger_daily": daily,
                "total_usage": total,
            }),
            variant=self._state.get("cohort", {}).get("variant"),
            config=self._config,
        )

    def record_paywall_shown(self, trigger_count: Optional[int] = None) -> None:
        now = self.get_now_iso()
        if trigger_count is None:
            trigger_count = int(self._state.get("last_trigger", {}).get("trigger_count", 0)) + 1
        self._state["last_trigger"] = {"shown_at": now, "trigger_count": trigger_count}
        # 触发后清零 since_last_paywall
        self._state["counters"]["since_last_paywall"] = 0
        self.save_state()

    def build_analytics_payload(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        base = {
            "plan_id": self._config.plan_id,
            "variant": (self._state.get("cohort", {}) or {}).get("variant"),
            "trigger_total": int(self._state.get("last_trigger", {}).get("trigger_count", 0)),
        }
        base.update(extra or {})
        return base

    # ----------------- CTA 处理 -----------------
    def handle_cta(self, cta_item: Dict[str, Any]) -> Dict[str, Any]:
        """处理 CTA 点击，返回埋点载荷；UI 层据此跳转/上报。

        约定：
        - cta_item: 包含 label/action/payload/value
        - 返回: {"event": str, "properties": dict, "action": str, "payload": Any}
        """
        action = cta_item.get("action")
        value = cta_item.get("value")
        payload = cta_item.get("payload")

        variant = (self._state.get("cohort", {}) or {}).get("variant")

        event = "purchase_intent_points_clicked"
        props = self.build_analytics_payload({
            "cta_value": value,
            "cta_action": action,
        })

        if variant == "subscription":
            event = "purchase_intent_subscription_clicked"

        if action == "emit_event":
            event = "paywall_fake_door_triggered"
            props["cta_payload"] = payload

        return {"event": event, "properties": props, "action": action, "payload": payload}

    def get_debug_info(self) -> Dict[str, Any]:
        self.reset_daily_counter()
        total = int(self._state["counters"].get("total", 0))
        daily = int(self._state["counters"]["daily"].get("count", 0))
        since_last = int(self._state["counters"].get("since_last_paywall", 0))
        cooldown_active, remaining = self._cooldown_blocked()

        cohort = self._state.get("cohort", {}) or {}
        last_trigger = self._state.get("last_trigger", {}) or {}

        return {
            "plan_id": self._config.plan_id,
            "variant": cohort.get("variant"),
            "total_usage": total,
            "total_limit": self._config.total_limit,
            "daily_usage": daily,
            "daily_limit": self._config.daily_limit,
            "since_last_paywall": since_last,
            "grace_messages": self._config.grace_messages,
            "cooldown_minutes": self._config.cooldown_minutes,
            "cooldown_active": cooldown_active,
            "cooldown_remaining": remaining,
            "last_trigger_at": last_trigger.get("shown_at"),
            "trigger_count": last_trigger.get("trigger_count"),
            "assigned_at": cohort.get("assigned_at"),
            "available_variants": sorted([k for k, v in self._variant_configs.items() if v]),
        }

    # ----------------- 状态访问 -----------------
    def get_cohort_snapshot(self) -> Dict[str, Any]:
        cohort = self._state.get("cohort", {}) or {}
        return {
            "variant": cohort.get("variant"),
            "plan_id": cohort.get("plan_id"),
            "assigned_at": cohort.get("assigned_at"),
        }

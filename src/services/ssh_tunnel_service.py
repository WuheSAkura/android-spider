from __future__ import annotations

import logging
from typing import Any

from src.models.task_models import SSHTunnelConfig
from src.utils.exceptions import ConfigError, DependencyError

sshtunnel: Any | None

try:
    from sshtunnel import SSHTunnelForwarder  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - 依赖检查由 doctor 命令负责
    sshtunnel = None
else:
    sshtunnel = SSHTunnelForwarder


class SSHTunnelService:
    """为远端 MySQL 提供按需创建的 SSH 隧道。"""

    def __init__(self, config: SSHTunnelConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.forwarder: Any | None = None

    def start(self) -> None:
        if not self.config.enabled:
            return
        if sshtunnel is None:
            raise DependencyError("缺少 sshtunnel 依赖，请先安装 requirements.txt。")
        if not self.config.host or not self.config.user:
            raise ConfigError("SSH 隧道已启用，但缺少 SSH_HOST 或 SSH_USER 配置。")
        if self.forwarder is not None:
            return

        forwarder_class = sshtunnel
        self.forwarder = forwarder_class(
            ssh_address_or_host=(self.config.host, self.config.port),
            ssh_username=self.config.user,
            ssh_password=self.config.password or None,
            remote_bind_address=(self.config.remote_host, self.config.remote_port),
            local_bind_address=("127.0.0.1", self.config.local_port),
        )
        self.forwarder.start()
        self.logger.info(
            "SSH 隧道已建立：127.0.0.1:%s -> %s:%s",
            self.local_port,
            self.config.remote_host,
            self.config.remote_port,
        )

    @property
    def local_port(self) -> int:
        if self.forwarder is None:
            return self.config.local_port
        return int(self.forwarder.local_bind_port)

    def close(self) -> None:
        if self.forwarder is None:
            return
        try:
            self.forwarder.stop()
        finally:
            self.forwarder = None
            self.logger.info("SSH 隧道已关闭。")

class ProjectError(Exception):
    """项目基础异常。"""


class ConfigError(ProjectError):
    """配置错误。"""


class DependencyError(ProjectError):
    """依赖缺失或不可用。"""


class DeviceNotFoundError(ProjectError):
    """未找到可用设备。"""


class DriverError(ProjectError):
    """驱动层错误。"""


class StepExecutionError(ProjectError):
    """任务步骤执行失败。"""


class TaskCancelledError(ProjectError):
    """任务被用户取消。"""

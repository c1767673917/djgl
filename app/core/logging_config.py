"""
日志配置模块
提供统一的日志格式和敏感信息过滤
"""

import logging
import re
import json
from typing import Any, Dict, List
from datetime import datetime
from functools import wraps


class SensitiveDataFilter(logging.Filter):
    """敏感信息过滤器"""

    # 敏感信息模式
    SENSITIVE_PATTERNS = [
        # 密码相关
        (r'password["\s]*[:=]["\s]*([^"\s,}]+)', r'password":"***"'),
        (r'pwd["\s]*[:=]["\s]*([^"\s,}]+)', r'pwd":"***"'),
        (r'pass["\s]*[:=]["\s]*([^"\s,}]+)', r'pass":"***"'),

        # Token和密钥
        (r'token["\s]*[:=]["\s]*([^"\s,}]+)', r'token":"***"'),
        (r'key["\s]*[:=]["\s]*([^"\s,}]+)', r'key":"***"'),
        (r'secret["\s]*[:=]["\s]*([^"\s,}]+)', r'secret":"***"'),
        (r'authorization["\s]*[:=]["\s]*([^"\s,}]+)', r'authorization":"***"'),

        # 基础认证
        (r'basic\s+([a-zA-Z0-9+/=]+)', 'basic ***'),
        (r'Bearer\s+([a-zA-Z0-9\-._~+/]+=*)', 'Bearer ***'),

        # WebDAV相关
        (r'webdav_password["\s]*[:=]["\s]*([^"\s,}]+)', r'webdav_password":"***"'),
        (r'webdav_username["\s]*[:=]["\s]*([^"\s,}]+)', r'webdav_username":"***"'),

        # 用友云相关
        (r'app_secret["\s]*[:=]["\s]*([^"\s,}]+)', r'app_secret":"***"'),
        (r'app_key["\s]*[:=]["\s]*([^"\s,}]+)', r'app_key":"***"'),

        # URL中的敏感参数
        (r'([&?])password=([^&]*)', r'\1password=***'),
        (r'([&?])token=([^&]*)', r'\1token=***'),
        (r'([&?])key=([^&]*)', r'\1key=***'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录中的敏感信息"""
        if hasattr(record, 'msg'):
            record.msg = self._filter_sensitive_data(str(record.msg))

        if hasattr(record, 'args') and record.args:
            filtered_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    filtered_args.append(self._filter_sensitive_data(arg))
                else:
                    filtered_args.append(arg)
            record.args = tuple(filtered_args)

        return True

    def _filter_sensitive_data(self, text: str) -> str:
        """过滤文本中的敏感数据"""
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text


class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器"""

    def __init__(self, include_extra: bool = False):
        super().__init__()
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为JSON格式"""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # 添加额外字段
        if self.include_extra and hasattr(record, '__dict__'):
            extra_fields = {
                k: v for k, v in record.__dict__.items()
                if k not in [
                    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                    'filename', 'module', 'lineno', 'funcName', 'created',
                    'msecs', 'relativeCreated', 'thread', 'threadName',
                    'processName', 'process', 'getMessage', 'exc_info',
                    'exc_text', 'stack_info'
                ]
            }
            if extra_fields:
                log_data["extra"] = extra_fields

        return json.dumps(log_data, ensure_ascii=False, default=str)


class ColoredFormatter(logging.Formatter):
    """彩色控制台日志格式化器"""

    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
        'RESET': '\033[0m'      # 重置
    }

    def format(self, record: logging.LogRecord) -> str:
        """格式化带颜色的日志"""
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']

        # 基础格式
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')

        formatted = (
            f"{color}[{timestamp}] "
            f"{record.levelname:8} "
            f"{record.name}:{record.lineno} "
            f"- {record.getMessage()}{reset}"
        )

        # 添加异常信息
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted


def setup_logging(
    level: str = "INFO",
    enable_console: bool = True,
    enable_file: bool = True,
    log_file: str = "logs/app.log",
    structured: bool = False,
    filter_sensitive: bool = True
) -> None:
    """设置日志配置"""

    # 创建日志目录
    import os
    if enable_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # 清除现有处理器
    root_logger.handlers.clear()

    # 敏感信息过滤器
    sensitive_filter = SensitiveDataFilter() if filter_sensitive else None

    # 控制台处理器
    if enable_console:
        console_handler = logging.StreamHandler()
        if structured:
            console_formatter = StructuredFormatter()
        else:
            console_formatter = ColoredFormatter()

        console_handler.setFormatter(console_formatter)
        if sensitive_filter:
            console_handler.addFilter(sensitive_filter)
        root_logger.addHandler(console_handler)

    # 文件处理器
    if enable_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )

        if structured:
            file_formatter = StructuredFormatter(include_extra=True)
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

        file_handler.setFormatter(file_formatter)
        if sensitive_filter:
            file_handler.addFilter(sensitive_filter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器"""
    return logging.getLogger(name)


def log_function_call(logger: logging.Logger = None):
    """函数调用日志装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or logging.getLogger(func.__module__)
            func_logger.debug(f"调用函数 {func.__name__} with args={args}, kwargs={kwargs}")

            try:
                result = func(*args, **kwargs)
                func_logger.debug(f"函数 {func.__name__} 执行成功")
                return result
            except Exception as e:
                func_logger.error(f"函数 {func.__name__} 执行失败: {str(e)}")
                raise

        return wrapper
    return decorator


def log_async_function_call(logger: logging.Logger = None):
    """异步函数调用日志装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            func_logger = logger or logging.getLogger(func.__module__)
            func_logger.debug(f"调用异步函数 {func.__name__} with args={args}, kwargs={kwargs}")

            try:
                result = await func(*args, **kwargs)
                func_logger.debug(f"异步函数 {func.__name__} 执行成功")
                return result
            except Exception as e:
                func_logger.error(f"异步函数 {func.__name__} 执行失败: {str(e)}")
                raise

        return wrapper
    return decorator


# 需要导入rotating file handler
import logging.handlers
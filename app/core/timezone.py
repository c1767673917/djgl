"""
北京时区工具模块

提供统一的北京时间（UTC+8）生成函数。
"""
from datetime import datetime, timezone, timedelta


# 北京时区常量（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))


def get_beijing_now() -> datetime:
    """
    获取当前北京时间（带时区信息）

    Returns:
        datetime: 带有 UTC+8 时区信息的 datetime 对象

    Example:
        >>> dt = get_beijing_now()
        >>> print(dt.tzinfo)  # UTC+08:00
    """
    return datetime.now(BEIJING_TZ)


def get_beijing_now_naive() -> datetime:
    """
    获取当前北京时间（无时区信息，用于数据库存储）

    Returns:
        datetime: 不带时区信息的 naive datetime 对象（北京时间）

    Example:
        >>> dt = get_beijing_now_naive()
        >>> print(dt.tzinfo)  # None
        >>> print(dt.strftime('%Y-%m-%d %H:%M:%S'))  # 2025-10-15 14:30:45
    """
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def get_beijing_now_iso() -> str:
    """
    获取当前北京时间的ISO格式字符串（带时区信息）

    Returns:
        str: 格式如 '2025-10-15T14:30:45+08:00'
    """
    return get_beijing_now().isoformat()


def get_beijing_now_naive_iso() -> str:
    """
    获取当前北京时间的ISO格式字符串（无时区信息）

    Returns:
        str: 格式如 '2025-10-15T14:30:45'
    """
    return get_beijing_now_naive().isoformat()


def format_beijing_time(dt: datetime) -> str:
    """
    将 datetime 对象格式化为标准字符串（用于 API 响应）

    Args:
        dt: datetime 对象（可带时区或不带时区）

    Returns:
        str: ISO 8601 格式字符串（无时区标识），如 '2025-10-15T14:30:45'

    Example:
        >>> dt = get_beijing_now_naive()
        >>> format_beijing_time(dt)  # '2025-10-15T14:30:45'
    """
    if dt is None:
        return None

    # 如果是 aware datetime（带时区），先转换为北京时区
    if dt.tzinfo is not None:
        dt = dt.astimezone(BEIJING_TZ).replace(tzinfo=None)

    return dt.strftime('%Y-%m-%dT%H:%M:%S')

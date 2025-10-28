"""
自定义异常类
提供统一的异常处理机制
"""


class BaseAppException(Exception):
    """应用基础异常类"""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}

    def to_dict(self) -> dict:
        """将异常转换为字典格式"""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }


class WebDAVError(BaseAppException):
    """WebDAV相关错误"""

    def __init__(self, message: str, error_code: str = None, status_code: int = None, **details):
        super().__init__(message, error_code, details)
        self.status_code = status_code
        if status_code:
            self.details["status_code"] = status_code


class WebDAVAuthenticationError(WebDAVError):
    """WebDAV认证错误"""
    def __init__(self, message: str = "WebDAV认证失败，请检查用户名和密码"):
        super().__init__(message, "WEBDAV_AUTH_ERROR", status_code=401)


class WebDAVPermissionError(WebDAVError):
    """WebDAV权限错误"""
    def __init__(self, message: str = "WebDAV权限不足，请检查目录权限"):
        super().__init__(message, "WEBDAV_PERMISSION_ERROR", status_code=403)


class WebDAVNotFoundError(WebDAVError):
    """WebDAV资源未找到错误"""
    def __init__(self, message: str = "WebDAV路径不存在", path: str = None):
        details = {}
        if path:
            details["path"] = path
        super().__init__(message, "WEBDAV_NOT_FOUND_ERROR", status_code=404, **details)


class WebDAVTimeoutError(WebDAVError):
    """WebDAV超时错误"""
    def __init__(self, message: str = "WebDAV请求超时"):
        super().__init__(message, "WEBDAV_TIMEOUT_ERROR")


class WebDAVNetworkError(WebDAVError):
    """WebDAV网络错误"""
    def __init__(self, message: str, original_error: Exception = None):
        details = {}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(message, "WEBDAV_NETWORK_ERROR", **details)


class WebDAVServerError(WebDAVError):
    """WebDAV服务器错误"""
    def __init__(self, message: str = "WebDAV服务器错误", status_code: int = 500):
        super().__init__(message, "WEBDAV_SERVER_ERROR", status_code=status_code)


class BackupError(BaseAppException):
    """备份相关错误"""
    def __init__(self, message: str, error_code: str = None, **details):
        super().__init__(message, error_code or "BACKUP_ERROR", details)


class DatabaseError(BaseAppException):
    """数据库相关错误"""
    def __init__(self, message: str, error_code: str = None, **details):
        super().__init__(message, error_code or "DATABASE_ERROR", details)


class ConfigurationError(BaseAppException):
    """配置相关错误"""
    def __init__(self, message: str, config_key: str = None):
        details = {}
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, "CONFIG_ERROR", details)


class ValidationError(BaseAppException):
    """数据验证错误"""
    def __init__(self, message: str, field: str = None, value=None):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)
        super().__init__(message, "VALIDATION_ERROR", details)


class FileOperationError(BaseAppException):
    """文件操作错误"""
    def __init__(self, message: str, file_path: str = None, operation: str = None):
        details = {}
        if file_path:
            details["file_path"] = file_path
        if operation:
            details["operation"] = operation
        super().__init__(message, "FILE_OPERATION_ERROR", details)


class UploadError(BaseAppException):
    """上传相关错误"""
    def __init__(self, message: str, error_code: str = None, **details):
        super().__init__(message, error_code or "UPLOAD_ERROR", details)


class YonYouError(BaseAppException):
    """用友云相关错误"""
    def __init__(self, message: str, error_code: str = None, response_data: dict = None):
        details = {}
        if response_data:
            details["response_data"] = response_data
        super().__init__(message, error_code or "YONYOU_ERROR", details)
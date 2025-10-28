from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
import re
from urllib.parse import urlparse


class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "单据上传管理系统"
    APP_VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 10000
    DEBUG: bool = False

    # 用友云配置 - 必须通过环境变量配置
    YONYOU_APP_KEY: Optional[str] = None
    YONYOU_APP_SECRET: Optional[str] = None
    YONYOU_BUSINESS_TYPE: str = "yonbip-scm-scmsa"
    YONYOU_AUTH_URL: str = "https://c4.yonyoucloud.com/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken"
    YONYOU_UPLOAD_URL: str = "https://c4.yonyoucloud.com/iuap-api-gateway/yonbip/uspace/iuap-apcom-file/rest/v1/file"

    # 上传配置
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    MAX_FILES_PER_REQUEST: int = 10
    ALLOWED_EXTENSIONS: set = {".jpg", ".jpeg", ".png", ".gif"}

    # 重试配置
    MAX_RETRY_COUNT: int = 3
    RETRY_DELAY: int = 2  # 秒
    REQUEST_TIMEOUT: int = 30  # 秒

    # 并发控制
    MAX_CONCURRENT_UPLOADS: int = 3

    # 数据库配置
    DATABASE_URL: str = "sqlite:///data/uploads.db"

    # 本地文件存储配置
    LOCAL_STORAGE_PATH: str = "data/uploaded_files"  # 本地文件存储路径

    # WebDAV配置
    WEBDAV_URL: str = "http://localhost:10100/dav/"
    WEBDAV_USERNAME: str = "admin"
    WEBDAV_PASSWORD: str = "adminlcs"
    WEBDAV_BASE_PATH: str = "onedrive_lcs"
    WEBDAV_TIMEOUT: int = 30
    WEBDAV_RETRY_COUNT: int = 3
    WEBDAV_RETRY_DELAY: int = 5

    # 缓存配置
    CACHE_DIR: str = "./cache"
    CACHE_DAYS: int = 7
    TEMP_STORAGE_DIR: str = "./temp_storage"

    # 备份配置
    BACKUP_RETENTION_DAYS: int = 30
    BACKUP_COMPRESSION_LEVEL: int = 6
    BACKUP_ENABLED: bool = True

    # WebDAV健康检查配置
    HEALTH_CHECK_INTERVAL: int = 60  # 秒
    SYNC_RETRY_INTERVAL: int = 300   # 5分钟

    # Token缓存配置
    TOKEN_CACHE_DURATION: int = 3600  # 1小时

    # 调试配置
    WEBDAV_DEBUG: bool = False
    BACKUP_DEBUG: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # 忽略额外的环境变量

    def _validate_webdav_url(self, url: str) -> str:
        """验证WebDAV URL格式"""
        if not url:
            raise ValueError("WebDAV URL不能为空")

        try:
            parsed = urlparse(url)
            if not parsed.scheme in ['http', 'https']:
                raise ValueError("WebDAV URL必须使用http或https协议")
            if not parsed.netloc:
                raise ValueError("WebDAV URL格式无效，缺少主机名")
            return url.rstrip('/') + '/'
        except Exception as e:
            raise ValueError(f"WebDAV URL格式无效: {str(e)}")

    def _validate_webdav_credentials(self, username: str, password: str) -> tuple:
        """验证WebDAV凭据"""
        if not username:
            raise ValueError("WebDAV用户名不能为空")
        if not password:
            raise ValueError("WebDAV密码不能为空")
        if len(username) > 100:
            raise ValueError("WebDAV用户名长度不能超过100个字符")
        if len(password) > 200:
            raise ValueError("WebDAV密码长度不能超过200个字符")
        return username, password

    def _validate_webdav_base_path(self, base_path: str) -> str:
        """验证WebDAV基础路径"""
        if not base_path:
            return ""

        # 清理路径中的斜杠
        clean_path = base_path.strip('/')

        # 检查路径中的无效字符
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in invalid_chars:
            if char in clean_path:
                raise ValueError(f"WebDAV基础路径包含无效字符: {char}")

        return clean_path

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # 验证WebDAV配置
        self.WEBDAV_URL = self._validate_webdav_url(self.WEBDAV_URL)
        self.WEBDAV_USERNAME, self.WEBDAV_PASSWORD = self._validate_webdav_credentials(
            self.WEBDAV_USERNAME, self.WEBDAV_PASSWORD
        )
        self.WEBDAV_BASE_PATH = self._validate_webdav_base_path(self.WEBDAV_BASE_PATH)

        # 验证WebDAV超时配置
        if self.WEBDAV_TIMEOUT <= 0:
            raise ValueError("WebDAV超时时间必须大于0")
        if self.WEBDAV_TIMEOUT > 300:
            raise ValueError("WebDAV超时时间不能超过300秒")

        # 验证WebDAV重试配置
        if self.WEBDAV_RETRY_COUNT < 0:
            raise ValueError("WebDAV重试次数不能为负数")
        if self.WEBDAV_RETRY_COUNT > 10:
            raise ValueError("WebDAV重试次数不能超过10次")

        if self.WEBDAV_RETRY_DELAY < 0:
            raise ValueError("WebDAV重试延迟不能为负数")
        if self.WEBDAV_RETRY_DELAY > 60:
            raise ValueError("WebDAV重试延迟不能超过60秒")

        # 验证必需的用友云配置
        if not self.YONYOU_APP_KEY:
            raise ValueError(
                "缺少必需的环境变量: YONYOU_APP_KEY\n"
                "请在 .env 文件中设置: YONYOU_APP_KEY=your_app_key"
            )
        if not self.YONYOU_APP_SECRET:
            raise ValueError(
                "缺少必需的环境变量: YONYOU_APP_SECRET\n"
                "请在 .env 文件中设置: YONYOU_APP_SECRET=your_app_secret"
            )

    def validate_webdav_health(self) -> dict:
        """验证WebDAV配置的完整性"""
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        try:
            # 检查WebDAV URL
            if not self.WEBDAV_URL:
                validation_result["errors"].append("WebDAV URL未配置")
                validation_result["valid"] = False

            # 检查凭据
            if not self.WEBDAV_USERNAME:
                validation_result["errors"].append("WebDAV用户名未配置")
                validation_result["valid"] = False

            if not self.WEBDAV_PASSWORD:
                validation_result["errors"].append("WebDAV密码未配置")
                validation_result["valid"] = False

            # 检查路径配置
            if self.WEBDAV_BASE_PATH and len(self.WEBDAV_BASE_PATH) > 200:
                validation_result["warnings"].append("WebDAV基础路径较长，可能影响性能")

            # 检查调试配置
            if self.WEBDAV_DEBUG:
                validation_result["warnings"].append("WebDAV调试模式已启用，生产环境建议关闭")

            return validation_result

        except Exception as e:
            validation_result["valid"] = False
            validation_result["errors"].append(f"配置验证异常: {str(e)}")
            return validation_result


@lru_cache()
def get_settings():
    return Settings()

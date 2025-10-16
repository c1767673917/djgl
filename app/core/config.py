from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


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

    # Token缓存配置
    TOKEN_CACHE_DURATION: int = 3600  # 1小时

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # 忽略额外的环境变量

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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


@lru_cache()
def get_settings():
    return Settings()

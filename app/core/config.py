from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "单据上传管理系统"
    APP_VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 10000
    DEBUG: bool = False

    # 用友云配置
    YONYOU_APP_KEY: str = "2b2c5f61d8734cd49e76f8f918977c5d"
    YONYOU_APP_SECRET: str = "61bc68be07201201142a8bf751a59068df9833e1"
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

    # Token缓存配置
    TOKEN_CACHE_DURATION: int = 3600  # 1小时

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings():
    return Settings()

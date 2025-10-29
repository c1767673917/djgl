from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import init_database, verify_database_schema
from app.core.logging_config import setup_logging
from app.core.file_manager import FileManager
from app.api import upload, history, admin, migration, webdav

settings = get_settings()
file_manager = FileManager()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 挂载上传文件目录(用于图片预览)
from pathlib import Path
uploaded_files_path = Path(settings.LOCAL_STORAGE_PATH)
if uploaded_files_path.exists():
    app.mount("/uploaded_files", StaticFiles(directory=str(uploaded_files_path)), name="uploaded_files")

# 挂载缓存目录(用于WebDAV文件缓存访问)
cache_path = Path(settings.CACHE_DIR)
if cache_path.exists():
    app.mount("/cache", StaticFiles(directory=str(cache_path)), name="cache")

# 路由
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(history.router, prefix="/api", tags=["history"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(migration.router, prefix="/api/admin/migration", tags=["migration"])
app.include_router(webdav.router, prefix="/api/admin/webdav", tags=["webdav"])


# 启动事件
@app.on_event("startup")
async def startup_event():
    # 设置日志系统
    setup_logging(
        level="INFO" if not settings.DEBUG else "DEBUG",
        enable_console=True,
        enable_file=True,
        log_file="logs/app.log",
        structured=False,  # 生产环境可以设置为True
        filter_sensitive=True
    )

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"启动应用: {settings.APP_NAME} v{settings.APP_VERSION}")

    # 初始化数据库
    init_database()
    logger.info("数据库初始化完成")

    # 验证数据库Schema
    try:
        verify_database_schema()
    except RuntimeError as e:
        # Schema验证失败，阻止应用启动
        logger.critical("应用启动失败 - 数据库Schema不完整")
        raise

    # 验证WebDAV配置
    validation_result = settings.validate_webdav_health()
    if not validation_result["valid"]:
        error_msg = f"WebDAV配置验证失败: {', '.join(validation_result['errors'])}"
        logger.error(error_msg)
        # 在开发环境中抛出异常，生产环境中只记录警告
        if settings.DEBUG:
            raise ValueError(error_msg)
    elif validation_result["warnings"]:
        for warning in validation_result["warnings"]:
            logger.warning(f"WebDAV配置警告: {warning}")

    # 启动定时任务调度器
    try:
        from app.scheduler import start_scheduler
        await start_scheduler()
        logger.info("定时任务调度器启动成功")
    except Exception as e:
        logger.error(f"定时任务调度器启动失败: {str(e)}")

    logger.info("应用启动完成")


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    import logging
    logger = logging.getLogger(__name__)
    try:
        from app.scheduler import stop_scheduler
        await stop_scheduler()
        logger.info("定时任务调度器已关闭")
    except Exception as e:
        logger.error(f"定时任务调度器关闭失败: {str(e)}")

    logger.info("应用已关闭")


# 根路由 - 上传页面（新格式）
@app.get("/")
async def upload_page(
    business_id: str = Query(..., description="业务单据ID"),
    doc_number: str = Query(..., description="单据编号"),
    doc_type: str = Query(..., description="单据类型")
):
    """
    上传页面入口

    URL示例: /?business_id=2372677039643688969&doc_number=SO20250103001&doc_type=销售

    参数:
    - business_id: 用友云业务单据ID（纯数字）
    - doc_number: 业务单据编号（如SO20250103001）
    - doc_type: 单据类型（销售/转库/其他）
    """
    # 验证business_id格式
    if not business_id or not business_id.isdigit():
        raise HTTPException(status_code=400, detail="business_id必须为纯数字")

    # 验证doc_type枚举值
    valid_doc_types = ["销售", "转库", "其他"]
    if doc_type not in valid_doc_types:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type必须为以下值之一: {', '.join(valid_doc_types)}"
        )

    return FileResponse("app/static/index.html")


# 健康检查端点
@app.get("/api/health")
async def health_check():
    """健康检查端点，用于Docker健康检查"""
    return {"status": "healthy", "app": settings.APP_NAME, "version": settings.APP_VERSION}


# WebDAV文件访问接口（优先从缓存，WebDAV兜底）
@app.get("/uploaded_files/{file_path:path}")
async def get_uploaded_file(file_path: str):
    """
    智能文件访问接口

    1. 首先检查本地缓存是否存在且未过期
    2. 缓存命中则直接返回缓存文件
    3. 缓存未命中则从WebDAV下载
    4. 下载后如果文件在7天内则写入缓存
    """
    try:
        # 构造WebDAV路径
        webdav_path = f"files/{file_path}"

        # 检查缓存是否存在且有效
        cache_path = file_manager._get_cache_path(webdav_path)

        if file_manager._is_cache_valid(cache_path):
            # 缓存命中，直接返回
            from fastapi.responses import FileResponse
            return FileResponse(cache_path)

        # 缓存未命中，从WebDAV下载
        file_content = await file_manager.get_file(webdav_path)

        return Response(
            content=file_content,
            media_type="application/octet-stream",
            headers={
                "Cache-Control": "public, max-age=3600",  # 缓存1小时
                "Access-Control-Allow-Origin": "*"
            }
        )

    except Exception as e:
        # WebDAV访问失败，尝试从旧路径访问
        try:
            old_path = settings.LOCAL_STORAGE_PATH + "/" + file_path
            from pathlib import Path

            if Path(old_path).exists():
                return FileResponse(old_path)
        except:
            pass

        raise HTTPException(status_code=404, detail=f"文件不存在或访问失败: {file_path}")


# 管理页面路由
@app.get("/admin")
async def admin_page():
    """管理页面入口"""
    return FileResponse("app/static/admin.html")

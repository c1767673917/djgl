from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import init_database
from app.api import upload, history, admin

settings = get_settings()

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

# 路由
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(history.router, prefix="/api", tags=["history"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])


# 启动事件
@app.on_event("startup")
async def startup_event():
    init_database()


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


# 管理页面路由
@app.get("/admin")
async def admin_page():
    """管理页面入口"""
    return FileResponse("app/static/admin.html")

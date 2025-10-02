from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import init_database
from app.api import upload, history

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


# 启动事件
@app.on_event("startup")
async def startup_event():
    init_database()


# 根路由 - 重定向到上传页面
@app.get("/{business_id}")
async def upload_page(business_id: str):
    return FileResponse("app/static/index.html")

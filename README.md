# 单据上传管理系统

一个基于FastAPI和用友云API的轻量级单据图片上传系统，支持移动端扫码上传。

## 功能特性

- 扫描二维码快速访问上传页面
- 移动端友好的图片选择和拍照功能
- 批量上传最多10张图片
- 实时显示上传进度
- 自动重试机制（最多3次）
- 上传历史记录查询
- SQLite数据库存储历史

## 项目结构

```
单据上传管理/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI应用入口
│   ├── api/
│   │   ├── __init__.py
│   │   ├── upload.py           # 上传API
│   │   └── history.py          # 历史记录API
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # 配置管理
│   │   ├── database.py         # 数据库操作
│   │   └── yonyou_client.py    # 用友云API客户端
│   ├── models/
│   │   ├── __init__.py
│   │   └── upload_history.py   # 数据模型
│   └── static/
│       ├── index.html          # 上传页面
│       ├── css/
│       │   └── style.css       # 样式文件
│       └── js/
│           └── app.js          # 前端逻辑
├── data/                       # 数据库文件目录（自动创建）
├── logs/                       # 日志目录（自动创建）
├── .env                        # 环境变量配置
├── .gitignore                  # Git忽略文件
├── requirements.txt            # Python依赖
├── run.py                      # 启动脚本
└── README.md                   # 本文档
```

## 环境要求

- Python 3.8+
- pip

## 安装步骤

### 1. 安装Python依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv

# 激活虚拟环境
# macOS/Linux:
source venv/bin/activate
# Windows:
# venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

`.env` 文件已包含默认配置，如需修改可编辑以下参数：

```bash
# 服务端口（默认10000）
PORT=10000

# 用友云配置（已配置好，无需修改）
YONYOU_APP_KEY=2b2c5f61d8734cd49e76f8f918977c5d
YONYOU_APP_SECRET=61bc68be07201201142a8bf751a59068df9833e1
YONYOU_BUSINESS_TYPE=onbip-scm-scmsa

# 上传限制
MAX_FILE_SIZE=10485760          # 单文件最大10MB
MAX_FILES_PER_REQUEST=10        # 单次最多10个文件
```

### 3. 启动服务

```bash
# 使用run.py启动（推荐）
python run.py

# 或直接使用uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 10000
```

启动成功后会看到：

```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:10000
```

## 使用方法

### 1. 访问上传页面

在浏览器中打开：

```
http://{服务器IP}:10000/{6位业务单据号}
```

例如：
```
http://192.168.1.100:10000/123456
```

### 2. 生成二维码

为方便移动端访问，建议生成二维码：

**方法一：使用在线工具**
- 访问 https://www.qr-code-generator.com/
- 输入URL: `http://{你的IP}:10000/{业务单据号}`
- 生成并打印二维码

**方法二：使用命令行（需要安装qrencode）**
```bash
# macOS
brew install qrencode
qrencode -o qrcode.png "http://192.168.1.100:10000/123456"

# Linux
sudo apt-get install qrencode
qrencode -o qrcode.png "http://192.168.1.100:10000/123456"
```

### 3. 上传图片

1. 扫描二维码或输入URL打开页面
2. 点击上传区域选择图片或拍照
3. 预览选中的图片（可删除单张或清空）
4. 点击"开始上传"按钮
5. 查看上传进度和结果
6. 可点击"查看上传历史"查看历史记录

## API接口

### 上传文件

```
POST /api/upload
Content-Type: multipart/form-data

参数:
- business_id: 业务单据ID（6位数字）
- files: 文件列表（最多10个）

响应:
{
    "success": true,
    "total": 10,
    "succeeded": 9,
    "failed": 1,
    "results": [...]
}
```

### 查询历史

```
GET /api/history/{business_id}

响应:
{
    "business_id": "123456",
    "total_count": 15,
    "success_count": 14,
    "failed_count": 1,
    "records": [...]
}
```

### API文档

启动服务后访问：
- Swagger UI: http://localhost:10000/docs
- ReDoc: http://localhost:10000/redoc

## 技术架构

### 后端技术栈

- **FastAPI**: 现代化的Python Web框架
- **httpx**: 异步HTTP客户端
- **SQLite**: 轻量级数据库
- **Pydantic**: 数据验证和配置管理

### 前端技术栈

- 原生HTML/CSS/JavaScript
- 响应式设计，移动端优先
- 异步上传，并发控制（最多3个）

### 核心功能

1. **Token管理**: HMAC-SHA256签名算法，自动缓存和刷新
2. **文件上传**: multipart/form-data格式，支持重试
3. **并发控制**: 限制同时上传数为3个
4. **进度显示**: 实时更新每个文件的上传状态
5. **历史记录**: SQLite数据库存储，支持按业务单据查询

## 故障排查

### 1. 服务无法启动

**问题**: `ModuleNotFoundError: No module named 'xxx'`

**解决**: 确保已安装所有依赖
```bash
pip install -r requirements.txt
```

### 2. 无法访问服务

**问题**: 浏览器无法打开页面

**解决**:
- 检查服务是否启动成功
- 检查防火墙是否允许10000端口
- 确认IP地址正确（使用 `ifconfig` 或 `ipconfig` 查看）

### 3. 上传失败

**问题**: 文件上传时报错

**解决**:
- 检查文件大小是否超过10MB
- 检查文件格式是否为图片（jpg/png/gif）
- 查看浏览器控制台错误信息
- 检查用友云API凭证是否正确

### 4. Token获取失败

**问题**: 提示"获取Token失败"

**解决**:
- 检查网络连接
- 确认 `.env` 中的 `YONYOU_APP_KEY` 和 `YONYOU_APP_SECRET` 正确
- 查看服务日志获取详细错误信息

## 安全建议

1. **生产环境部署**:
   - 使用HTTPS协议
   - 配置CORS允许的域名
   - 设置合理的文件大小限制
   - 定期备份数据库

2. **凭证保护**:
   - 不要将 `.env` 文件提交到Git
   - 定期更换API密钥
   - 使用环境变量而非硬编码

3. **访问控制**:
   - 考虑添加用户认证
   - 限制IP访问范围
   - 监控异常上传行为

## 开发指南

### 本地开发

```bash
# 开启调试模式
# 修改 .env:
DEBUG=true

# 启动开发服务器（支持热重载）
python run.py
```

### 数据库管理

```bash
# 查看数据库
sqlite3 data/uploads.db

# 查询所有记录
SELECT * FROM upload_history;

# 按业务单据查询
SELECT * FROM upload_history WHERE business_id = '123456';

# 清空历史记录
DELETE FROM upload_history;
```

### 日志查看

日志输出到控制台，可重定向到文件：

```bash
python run.py > logs/app.log 2>&1
```

## 后台运行

### macOS/Linux

```bash
# 使用nohup后台运行
nohup python run.py > logs/app.log 2>&1 &

# 查看进程
ps aux | grep python

# 停止服务
kill <PID>
```

### 使用systemd（Linux）

创建服务文件 `/etc/systemd/system/document-upload.service`:

```ini
[Unit]
Description=Document Upload Management System
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/单据上传管理
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python run.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl enable document-upload
sudo systemctl start document-upload
sudo systemctl status document-upload
```

## 性能优化建议

1. **Token缓存**: 默认缓存1小时，减少API调用
2. **并发限制**: 默认最多3个并发上传，避免服务器压力过大
3. **数据库索引**: 已为 `business_id`、`upload_time`、`status` 创建索引
4. **文件大小限制**: 默认10MB，可根据需求调整

## 许可证

本项目仅供内部使用。

## 技术支持

如有问题，请联系开发团队。

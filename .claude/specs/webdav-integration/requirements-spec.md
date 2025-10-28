# WebDAV集成与数据库备份技术规范

## 问题陈述

**业务问题**: 服务器存储空间有限，图片文件压力巨大，需要使用WebDAV完全替代本地存储，并实现数据库定时备份。

**当前状���**:
- 所有文件存储在本地 `data/uploaded_files` 目录
- 无数据库备份机制
- 存储空间受限，无法扩展

**预期结果**:
- 所有新文件直接存储到WebDAV
- 7天内文件保留本地缓存，超过自动删除
- 每日0点自动备份数据库到WebDAV
- WebDAV故障时降级存储，恢复后自动同步

## 解决方案概述

**实现策略**: 基于现有FastAPI架构，集成WebDAV客户端实现混合存储模式，结合定时任务实现数据备份和缓存管理。

**核心变更**:
1. 扩展配置管理系统，添加WebDAV配置项
2. 创建WebDAV异步客户端模块
3. 修改文件上传API，实现WebDAV存储+本地缓存
4. 新增文件迁移API和备份定时任务
5. 实现WebDAV健康检���和故障降级机制

**成功标准**:
- 新文件成功存储到WebDAV，缓存访问延迟<1秒
- 文件迁移功能正常，进度显示准确
- 每日自动备份执行成功，保留30天历史
- WebDAV故障时服务不中断，恢复后自动同步

## 技术实现

### 数据库变更

**新增表**: file_metadata
```sql
CREATE TABLE file_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    webdav_path TEXT NOT NULL,
    local_cache_path TEXT,
    upload_time DATETIME NOT NULL,
    file_size INTEGER NOT NULL,
    is_cached BOOLEAN DEFAULT 1,
    last_access_time DATETIME,
    webdav_etag TEXT,
    is_synced BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_file_metadata_upload_time ON file_metadata(upload_time);
CREATE INDEX idx_file_metadata_is_cached ON file_metadata(is_cached);
CREATE INDEX idx_file_metadata_is_synced ON file_metadata(is_synced);
```

**扩展现有表**: upload_history
```sql
ALTER TABLE upload_history ADD COLUMN webdav_path TEXT;
ALTER TABLE upload_history ADD COLUMN is_cached BOOLEAN DEFAULT 1;
ALTER TABLE upload_history ADD COLUMN cache_expiry_time DATETIME;
ALTER TABLE upload_history ADD COLUMN backup_status TEXT DEFAULT 'pending';
```

**新增表**: backup_logs
```sql
CREATE TABLE backup_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_filename TEXT NOT NULL,
    backup_time DATETIME NOT NULL,
    file_size INTEGER NOT NULL,
    status TEXT NOT NULL, -- 'success', 'failed', 'partial'
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**迁移脚本**: migrations/add_webdav_support.sql
```sql
-- 2025-10-27: 添加WebDAV支持
-- 执行顺序很重要，请按顺序执行

-- 1. 创建文件元数据表
CREATE TABLE IF NOT EXISTS file_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    webdav_path TEXT NOT NULL,
    local_cache_path TEXT,
    upload_time DATETIME NOT NULL,
    file_size INTEGER NOT NULL,
    is_cached BOOLEAN DEFAULT 1,
    last_access_time DATETIME,
    webdav_etag TEXT,
    is_synced BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. 创建索引
CREATE INDEX IF NOT EXISTS idx_file_metadata_upload_time ON file_metadata(upload_time);
CREATE INDEX IF NOT EXISTS idx_file_metadata_is_cached ON file_metadata(is_cached);
CREATE INDEX IF NOT EXISTS idx_file_metadata_is_synced ON file_metadata(is_synced);

-- 3. 扩展upload_history表
ALTER TABLE upload_history ADD COLUMN webdav_path TEXT;
ALTER TABLE upload_history ADD COLUMN is_cached BOOLEAN DEFAULT 1;
ALTER TABLE upload_history ADD COLUMN cache_expiry_time DATETIME;
ALTER TABLE upload_history ADD COLUMN backup_status TEXT DEFAULT 'pending';

-- 4. 创建备份日志表
CREATE TABLE IF NOT EXISTS backup_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_filename TEXT NOT NULL,
    backup_time DATETIME NOT NULL,
    file_size INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 5. 插入现有文件到file_metadata表（迁移现有数据）
INSERT INTO file_metadata (filename, webdav_path, local_cache_path, upload_time, file_size, is_synced)
SELECT
    file_name,
    'files/' || strftime('%Y/%m/%d', upload_time) || '/' || file_name,
    local_file_path,
    upload_time,
    file_size,
    0 -- 标记为未同步到WebDAV
FROM upload_history
WHERE status = 'success' AND local_file_path IS NOT NULL;

-- 6. 更新upload_history表的webdav_path
UPDATE upload_history
SET webdav_path = 'files/' || strftime('%Y/%m/%d', upload_time) || '/' || file_name
WHERE status = 'success';
```

### 代码变更

**新增文件**:

1. **app/core/webdav_client.py** - WebDAV异步客户端
```python
# WebDAV客户端实现
# 支持PROPFIND, GET, PUT, DELETE, MKCOL方法
# 包含重试机制、错误处理、进度回调
```

2. **app/core/file_manager.py** - 文件管理服务
```python
# 混合存储策略实现
# 缓存管理、文件访问、清理策略
# WebDAV故障降级处理
```

3. **app/core/backup_service.py** - 备份服务
```python
# 数据库备份实现
# WebDAV上传、压缩、清理逻辑
# 备份状态管理
```

4. **app/scheduler.py** - 定时任务调度器
```python
# APScheduler配置
# 缓存清理任务
# 数据库备份任务
# WebDAV健康检查
```

5. **app/api/migration.py** - 文件迁移API
```python
# 迁移接口实现
# 进度查询、错误处理
# 批量操作支持
```

6. **app/api/webdav.py** - WebDAV状态API
```python
# WebDAV状态查询
# 健康检查、同步状态
# 管理接口
```

**修改文件**:

1. **app/core/config.py** - 配置扩展
```python
# 新增配置项:
WEBDAV_URL: str = "http://localhost:10100/dav/"
WEBDAV_USERNAME: str = "admin"
WEBDAV_PASSWORD: str = "adminlcs"
WEBDAV_BASE_PATH: str = "onedrive_lcs"
WEBDAV_TIMEOUT: int = 30
WEBDAV_RETRY_COUNT: int = 3
WEBDAV_RETRY_DELAY: int = 5

CACHE_DIR: str = "./cache"
CACHE_DAYS: int = 7
TEMP_STORAGE_DIR: str = "./temp_storage"
BACKUP_RETENTION_DAYS: int = 30
BACKUP_COMPRESSION_LEVEL: int = 6

# WebDAV健康检查配置
HEALTH_CHECK_INTERVAL: int = 60  # 秒
SYNC_RETRY_INTERVAL: int = 300   # 5分钟
```

2. **app/api/upload.py** - 上传API修改
```python
# 修改background_upload_to_yonyou函数
# 集成WebDAV上传+本地缓存
# 添加故障降级逻辑
# 更新数据库记录
```

3. **app/main.py** - 主应用配置
```python
# 添加调度器启动事件
# 注册新的API路由
# 挂载缓存静态文件目录
```

4. **app/static/admin.html** - 管理页面扩展
```javascript
// 添加迁移功能按钮
// WebDAV状态显示
// 进度条和错误信息展示
```

**核心函数签名**:

```python
# WebDAV客户端
class WebDAVClient:
    async def upload_file(self, local_path: str, webdav_path: str) -> Dict[str, Any]
    async def download_file(self, webdav_path: str, local_path: str) -> bytes
    async def delete_file(self, webdav_path: str) -> bool
    async def list_files(self, path: str) -> List[Dict[str, Any]]
    async def health_check(self) -> bool

# 文件管理器
class FileManager:
    async def save_file(self, file_content: bytes, filename: str) -> Dict[str, Any]
    async def get_file(self, webdav_path: str) -> bytes
    async def cleanup_cache(self) -> Dict[str, int]
    async def sync_pending_files(self) -> Dict[str, Any]

# 备份服务
class BackupService:
    async def create_backup(self) -> Dict[str, Any]
    async def upload_backup(self, backup_path: str) -> bool
    async def cleanup_old_backups(self) -> int
    async def schedule_backup(self) -> None
```

### API变更

**新增API端点**:

1. **POST /api/admin/migration/start** - 开始文件迁移
```json
Request: {}
Response: {
    "success": true,
    "migration_id": "uuid-string",
    "total_files": 150,
    "message": "迁移任务已启动"
}
```

2. **GET /api/admin/migration/status/{migration_id}** - 查询迁移状态
```json
Response: {
    "success": true,
    "migration_id": "uuid-string",
    "status": "running", // 'running', 'completed', 'failed'
    "progress": {
        "total": 150,
        "completed": 75,
        "failed": 2,
        "percentage": 50.0
    },
    "errors": [
        {
            "filename": "error_file.jpg",
            "error": "WebDAV connection timeout"
        }
    ]
}
```

3. **GET /api/admin/webdav/status** - WebDAV服务状态
```json
Response: {
    "success": true,
    "webdav_available": true,
    "last_check": "2025-10-27T10:30:00Z",
    "pending_sync_count": 5,
    "total_cached_files": 120,
    "cache_size_mb": 256.7
}
```

4. **POST /api/admin/webdav/sync** - 手动触发同步
```json
Request: {}
Response: {
    "success": true,
    "sync_started": true,
    "pending_files": 5,
    "message": "同步任务已启动"
}
```

5. **GET /api/admin/backup/status** - 备份状态查询
```json
Response: {
    "success": true,
    "last_backup": {
        "filename": "backup_20251027_000000.tar.gz",
        "time": "2025-10-27T00:00:00Z",
        "size": 15728640,
        "status": "success"
    },
    "next_backup": "2025-10-28T00:00:00Z",
    "backup_count": 15,
    "total_size_mb": 234.5
}
```

6. **POST /api/admin/backup/trigger** - 手动触发备份
```json
Request: {}
Response: {
    "success": true,
    "backup_started": true,
    "message": "备份任务已启动"
}
```

**修改现有API**:

1. **GET /api/admin/files** - 扩展文件列表功能
```json
// 新增响应字段
Response: {
    "files": [
        {
            // 现有字段...
            "webdav_path": "files/2025/10/27/filename.jpg",
            "is_cached": true,
            "cache_expiry": "2025-11-03T10:30:00Z",
            "is_synced": true,
            "file_location": "webdav" // 'local', 'webdav', 'both'
        }
    ]
}
```

2. **GET /uploaded_files/{file_path}** - 文件访问优化
```python
# 修改文件访问逻辑：
# 1. 检查本地缓存是否存在且未过期
# 2. 缓存命中则直接返回
# 3. 缓存未命中则从WebDAV下载
# 4. 如果是7天内文件则写入缓存
```

### 配置变更

**环境变量扩展 (.env)**:
```bash
# WebDAV配置
WEBDAV_URL=http://localhost:10100/dav/
WEBDAV_USERNAME=admin
WEBDAV_PASSWORD=adminlcs
WEBDAV_BASE_PATH=onedrive_lcs
WEBDAV_TIMEOUT=30
WEBDAV_RETRY_COUNT=3
WEBDAV_RETRY_DELAY=5

# 缓存配置
CACHE_DIR=./cache
CACHE_DAYS=7
TEMP_STORAGE_DIR=./temp_storage

# 备份配置
BACKUP_RETENTION_DAYS=30
BACKUP_COMPRESSION_LEVEL=6
BACKUP_ENABLED=true

# 健康检查配置
HEALTH_CHECK_INTERVAL=60
SYNC_RETRY_INTERVAL=300

# 调试配置
WEBDAV_DEBUG=false
BACKUP_DEBUG=false
```

**新增requirements.txt依赖**:
```
apscheduler==3.10.4          # 定时任务调度
aiofiles==23.2.1             # 异步文件操作
```

## 实现序列

### 阶段1: WebDAV核心功能实现 (P0 - 高优先级)

1. **配置和基础设施**
   - 修改 `app/core/config.py` 添加WebDAV配置项
   - 创建 `app/core/webdav_client.py` WebDAV客户端实现
   - 执行数据库迁移脚本 `migrations/add_webdav_support.sql`
   - 更新 `requirements.txt` 添加新依赖

2. **文件存储集成**
   - 创建 `app/core/file_manager.py` 文件管理服务
   - 修改 `app/api/upload.py` 集成WebDAV上传逻辑
   - 更新 `app/main.py` 挂载缓存目录和添加新路由
   - 实现文件访问的缓存策略

3. **故障处理机制**
   - 实现WebDAV健康检查功能
   - 添加降级存储逻辑
   - 创建待同步文件管理机制
   - 实现自动重试和恢复逻辑

### 阶段2: 缓存与备份功能 (P1 - 高优先级)

1. **定时任务系统**
   - 创建 `app/scheduler.py` 调度器实现
   - 实现缓存清理定时任务
   - 添加WebDAV健康检查定时任务
   - 集成到主应用启动流程

2. **数据库备份功能**
   - 创建 `app/core/backup_service.py` 备份服务
   - 实现数据库压缩和WebDAV上传
   - 添加备份文件清理逻辑
   - 创建备份日志记录系统

3. **状态监控API**
   - 创建 `app/api/webdav.py` WebDAV状态API
   - 实现备份状态查询接口
   - 添加手动触发同步功能
   - 集成到现有管理页面

### 阶段3: 迁移功能实现 (P2 - 中优先级)

1. **文件迁移API**
   - 创建 `app/api/migration.py` 迁移接口
   - 实现批量文件迁移逻辑
   - 添加进度跟踪和错误处理
   - 支持迁移任务的暂停和恢复

2. **管理界面扩展**
   - 修改 `app/static/admin.html` 添加迁移功能
   - 实现进度条和状态显示
   - 添加WebDAV状态监控面��
   - 集成备份管理功能

3. **系统优化**
   - 性能优化和并发控制
   - 添加详细的日志记录
   - 完善错误处理和用户提示
   - 系统监控和告警机制

### 阶段4: 测试和部署 (P3 - 低优先级)

1. **测试完善**
   - 添加WebDAV功能的单元测试
   - 创建集成测试用例
   - 性能测试和压力测试
   - 故障恢复测试

2. **文档和部署**
   - 更新部署文档
   - 添加配置说明
   - 创建运维手册
   - 生产环境部署验证

## 验证计划

### 单元测试

**WebDAV客户端测试** (`tests/test_webdav_client.py`):
```python
@pytest.mark.asyncio
async def test_webdav_upload_file():
    # 测试文件上传功能

@pytest.mark.asyncio
async def test_webdav_download_file():
    # 测试文件下载功能

@pytest.mark.asyncio
async def test_webdav_health_check():
    # 测试健康检查功能

@pytest.mark.asyncio
async def test_webdav_retry_mechanism():
    # 测试重试机制
```

**文件管理器测试** (`tests/test_file_manager.py`):
```python
@pytest.mark.asyncio
async def test_save_file_with_cache():
    # 测试文件保存和缓存

@pytest.mark.asyncio
async def test_get_file_cache_hit():
    # 测试缓存命中��景

@pytest.mark.asyncio
async def test_get_file_cache_miss():
    # 测试缓存未命中场景

@pytest.mark.asyncio
async def test_cleanup_cache():
    # 测试缓存清理功能
```

**备份服务测试** (`tests/test_backup_service.py`):
```python
@pytest.mark.asyncio
async def test_create_backup():
    # 测试备份创建

@pytest.mark.asyncio
async def test_upload_backup():
    # 测试备份上传

@pytest.mark.asyncio
async def test_cleanup_old_backups():
    # 测试备份清理
```

### 集成测试

**端到端上传流程测试** (`tests/test_integration_upload.py`):
```python
@pytest.mark.asyncio
async def test_complete_upload_workflow():
    # 1. 上传文件到API
    # 2. 验证WebDAV存储
    # 3. 验证本地缓存
    # 4. 验证数据库记录
    # 5. 测试文件访问
```

**故障恢复测试** (`tests/test_integration_failover.py`):
```python
@pytest.mark.asyncio
async def test_webdav_failover_workflow():
    # 1. 模拟WebDAV故障
    # 2. 上传文件（应该降级到本地）
    # 3. 恢复WebDAV服务
    # 4. 验证自动同步
    # 5. 验证文件完整性
```

**迁移功能测试** (`tests/test_integration_migration.py`):
```python
@pytest.mark.asyncio
async def test_bulk_migration_workflow():
    # 1. 创建测试文件
    # 2. 启动迁移任务
    # 3. 监控迁移进度
    # 4. 验证迁移结果
    # 5. 清理测试数据
```

### 业务逻辑验证

**存储策略验证**:
1. 新文件上传后存储在WebDAV，本地存在缓存
2. 缓存文件7天后自动清理
3. 超过7天的文件从WebDAV实时加载
4. WebDAV故障时文件临时存储本地
5. WebDAV恢复后自动同步临时文件

**备份策略验证**:
1. 每日0点自动执行备份
2. 备份文件包含数据库和.env文件
3. 备份文件命名格式正确
4. 自动清理30天前的备份
5. 备份失败时有���误记录和告警

**性能指标验证**:
1. 缓存文件访问延迟 <1秒
2. WebDAV文件首次访问延迟 <2秒
3. 文件上传成功率 >99%
4. 备份任务执行时间 <5分钟
5. 系统内存使用稳定

### 边界情况测试

**网络异常处理**:
1. WebDAV连接超时处理
2. 网络中断恢复后的重连
3. 大文件上传的稳定性
4. 并发上传的处理能力

**存储空间处理**:
1. 本地磁盘空间不足的处理
2. WebDAV空间不足的提示
3. 缓存目录的自动清理
4. 临时文件的管理

**数据一致性**:
1. 数据库记录与实际文件的一致性
2. 并发访问时的数据完整性
3. 异常情况下的数据恢复
4. 文件损坏的检测和处理

---

**技术规范版本**: 1.0
**创建时间**: 2025-10-27
**适用项目**: 单据上传管理系统 WebDAV集成
**实施复杂度**: 高（涉及核心架构变更）
**预估开发时间**: 2-3周
**风险等级**: 中等（需要充分的测试和备份策略）
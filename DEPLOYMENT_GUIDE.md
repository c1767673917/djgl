# WebDAV集成功能生产环境部署指南

## ⚠️ 重要提醒

**应用启动时不会自动迁移数据！** 所有数据库变更和文件迁移都需要手动执行，以确保生产环境安全。

---

## 📋 部署前检查清单

### 1. 环境准备
- [ ] WebDAV服务器已运行并可访问（http://localhost:10100/dav/）
- [ ] 数据库已备份（非常重要！）
- [ ] 有足够的磁盘空间用于缓存和临时存储
- [ ] Python 3.8+ 环境

### 2. WebDAV服务器测试
```bash
# 测试WebDAV连接
curl -u admin:adminlcs http://localhost:10100/dav/

# 测试上传权限
curl -u admin:adminlcs -T test.txt http://localhost:10100/dav/onedrive_lcs/test.txt
```

---

## 🔧 部署步骤

### 步骤1：备份当前数据库（必须！）

```bash
# 备份数据库文件
cp data/uploads.db data/uploads.db.backup_$(date +%Y%m%d_%H%M%S)

# 或使用SQLite dump
sqlite3 data/uploads.db .dump > backup_$(date +%Y%m%d_%H%M%S).sql
```

### 步骤2：安装新依赖

```bash
pip install -r requirements.txt
```

新增的依赖：
- APScheduler==3.10.4 - 定时任务
- aiofiles==23.2.1 - 异步文件操作

### 步骤3：配置环境变量

编辑 `.env` 文件，添加WebDAV配置：

```env
# WebDAV配置（必需）
WEBDAV_URL=http://localhost:10100/dav/
WEBDAV_USERNAME=admin
WEBDAV_PASSWORD=adminlcs
WEBDAV_BASE_PATH=onedrive_lcs

# 缓存配置
CACHE_DIR=./cache
CACHE_DAYS=7
TEMP_STORAGE_DIR=./temp_storage

# 备份配置
BACKUP_DIR=./backups
BACKUP_RETENTION_DAYS=30

# WebDAV超时和重试
WEBDAV_TIMEOUT=30.0
WEBDAV_RETRY_COUNT=3
WEBDAV_RETRY_DELAY=5

# 调试模式（生产环境设置为false）
WEBDAV_DEBUG=false
```

### 步骤4：创建必需目录

```bash
mkdir -p ./cache ./temp_storage ./backups ./logs
chmod 755 ./cache ./temp_storage ./backups ./logs
```

### 步骤5：执行数据库迁移（手动）

**⚠️ 这是最重要的步骤！**

```bash
# 查看迁移脚本内容（确认将要执行的操作）
cat migrations/add_webdav_support.sql

# 执行数据库迁移
sqlite3 data/uploads.db < migrations/add_webdav_support.sql
```

**迁移脚本会创建以下表：**
- `file_metadata` - 文件元数据管理
- `backup_logs` - 备份历史记录
- `migration_status` - 文件迁移状态
- `pending_sync` - 待同步文件队列

**以及扩展现有表：**
- `upload_history` 表添加以下字段：
  - `webdav_path` - WebDAV路径
  - `is_cached` - 是否缓存
  - `cache_expiry_time` - 缓存过期时间

### 步骤6：验证数据库迁移

```bash
# 检查新表是否创建成功
sqlite3 data/uploads.db "SELECT name FROM sqlite_master WHERE type='table';"

# 应该看到以下表：
# upload_history (现有)
# file_metadata (新增)
# backup_logs (新增)
# migration_status (新增)
# pending_sync (新增)

# 检查upload_history表的新字段
sqlite3 data/uploads.db "PRAGMA table_info(upload_history);"

# 应该看到新增的字段：webdav_path, is_cached, cache_expiry_time
```

### 步骤7：启动应用（测试模式）

```bash
# 先在测试模式下启动，检查是否有错误
python3 run.py
```

**检查启动日志：**
```
启动应用: 单据上传管理系统 v2.0
数据库初始化完成
WebDAV配置验证: 成功
定时任务调度器启动成功
应用启动完成
```

### 步骤8：验证WebDAV集成

访问管理后台：`http://localhost:10000/admin`

**检查WebDAV状态：**
- 应该显示"WebDAV状态: 在线"
- 待同步文件数：0

**测试连接按钮：**
- 点击"测试WebDAV连接"
- 应该显示"连接成功"

### 步骤9：测试文件上传

```bash
# 上传一个测试文件
curl -X POST http://localhost:10000/api/upload \
  -F "file=@test.jpg" \
  -F "businessId=123456" \
  -F "docType=contract"
```

**验证：**
1. 文件在WebDAV中存在：`http://localhost:10100/dav/onedrive_lcs/files/...`
2. 本地缓存目录有文件：`ls -la ./cache/`
3. 数据库有记录：
   ```bash
   sqlite3 data/uploads.db "SELECT * FROM upload_history ORDER BY id DESC LIMIT 1;"
   sqlite3 data/uploads.db "SELECT * FROM file_metadata ORDER BY id DESC LIMIT 1;"
   ```

### 步骤10：迁移现有文件（可选）

**⚠️ 这是一个可选步骤，如果有现有文件需要迁移到WebDAV**

#### 方式1：通过管理后台UI（推荐）

1. 访问 `http://localhost:10000/admin`
2. 找到"文件迁移到WebDAV"区域
3. **先执行演练模式：**
   - 勾选"演练模式"
   - 点击"开始迁移"
   - 查看会迁移哪些文件，不会实际修改
4. **确认无误后正式迁移：**
   - 取消勾选"演练模式"
   - 点击"开始迁移"
   - 观察实时进度
   - 等待完成

#### 方式2：通过API

```bash
# 演练模式（推荐先执行）
curl -X POST http://localhost:10000/api/admin/migration/start \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# 查看演练结果
curl http://localhost:10000/api/admin/migration/status

# 正式迁移（确认演练结果无误后）
curl -X POST http://localhost:10000/api/admin/migration/start \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'

# 查看迁移进度
curl http://localhost:10000/api/admin/migration/status
```

**迁移过程：**
1. 扫描本地 `data/uploaded_files/` 目录
2. 逐个上传文件到WebDAV
3. 验证上传成功
4. 删除本地原文件
5. 更新数据库记录

**迁移结果：**
```json
{
  "status": "completed",
  "total_files": 150,
  "migrated_files": 148,
  "failed_files": 2,
  "progress": 98.67,
  "start_time": "2025-10-27 10:00:00",
  "end_time": "2025-10-27 10:15:30",
  "errors": [
    "file1.jpg: 上传失败 - 网络超时",
    "file2.png: 文件不存在"
  ]
}
```

### 步骤11：测试故障降级

```bash
# 1. 停止WebDAV服务
docker stop webdav_container  # 或您的WebDAV服务

# 2. 尝试上传文件
curl -X POST http://localhost:10000/api/upload \
  -F "file=@test2.jpg" \
  -F "businessId=123457" \
  -F "docType=invoice"

# 3. 检查管理后台
# 应该显示：WebDAV状态: 离线
# 待同步文件数：1

# 4. 检查临时存储目录
ls -la ./temp_storage/

# 5. 重启WebDAV服务
docker start webdav_container

# 6. 等待自动同步（最多5分钟）
# 或手动触发同步
curl -X POST http://localhost:10000/api/admin/webdav/sync

# 7. 验证文件已同步到WebDAV
# 待同步文件数应该变为：0
```

### 步骤12：测试备份功能

```bash
# 手动触发一次备份（不需要等到0点）
curl -X POST http://localhost:10000/api/backup/create

# 检查备份文件
ls -la ./backups/
# 应该看到：backup_YYYYMMDD_HHMMSS.tar.gz

# 检查备份是否上传到WebDAV
curl -u admin:adminlcs http://localhost:10100/dav/onedrive_lcs/backups/

# 解压验证备份内容
tar -tzf backups/backup_*.tar.gz
# 应该包含：data/uploads.db 和 .env
```

---

## 🎯 验收标准

### 功能验收

- [ ] ✅ 新文件上传成功存储到WebDAV
- [ ] ✅ 本地缓存目录有7天内的文件
- [ ] ✅ 超过7天的缓存文件被自动清理
- [ ] ✅ 管理后台正确显示WebDAV状态
- [ ] ✅ 文件迁移功能正常（如果需要）
- [ ] ✅ WebDAV不可用时文件保存到临时存储
- [ ] ✅ WebDAV恢复后自动同步临时文件
- [ ] ✅ 备份功能正常执行
- [ ] ✅ 备份文件成功上传到WebDAV

### 性能验收

- [ ] ✅ 缓存文件访问延迟 < 1秒
- [ ] ✅ WebDAV首次加载延迟 < 2秒
- [ ] ✅ 文件上传成功率 > 99%
- [ ] ✅ 支持10个并发上传

### 数据完整性验收

- [ ] ✅ 数据库迁移后现有数据完整
- [ ] ✅ 文件迁移后可以正常访问
- [ ] ✅ 备份文件包含完整数据

---

## 🔄 回滚方案

如果部署后出现问题，可以按以下步骤回滚：

### 1. 停止应用

```bash
# 停止应用进程
pkill -f "python3 run.py"
```

### 2. 恢复数据库

```bash
# 恢复备份的数据库
cp data/uploads.db.backup_YYYYMMDD_HHMMSS data/uploads.db
```

### 3. 恢复代码（如果需要）

```bash
# 使用git回退到之前的版本
git checkout <previous_commit_hash>
```

### 4. 重启应用

```bash
python3 run.py
```

---

## 📊 监控建议

### 启动后监控指标

1. **WebDAV状态**
   - 每分钟检查一次健康状态
   - 告警：离线超过5分钟

2. **待同步文件数**
   - 实时监控
   - 告警：超过50个文件待同步

3. **缓存使用情况**
   - 每小时检查一次磁盘使用
   - 告警：缓存目录超过10GB

4. **备份执行状态**
   - 每日检查备份是否成功
   - 告警：连续2天备份失败

### 日志文件位置

```bash
# 应用主日志
tail -f logs/app.log

# 备份日志
tail -f logs/backup.log

# WebDAV操作日志
tail -f logs/webdav.log

# 错误日志
grep ERROR logs/app.log
```

---

## 🐛 常见问题排查

### 问题1：启动时提示"WebDAV配置验证失败"

**原因**：WebDAV服务不可用或配置错误

**解决方案**：
```bash
# 检查WebDAV服务是否运行
curl http://localhost:10100/dav/

# 检查.env配置是否正确
cat .env | grep WEBDAV

# 测试认证
curl -u admin:adminlcs http://localhost:10100/dav/
```

### 问题2：数据库迁移失败

**错误信息**：`Error: table file_metadata already exists`

**原因**：迁移脚本已经执行过

**解决方案**：检查表是否已存在
```bash
sqlite3 data/uploads.db "SELECT name FROM sqlite_master WHERE type='table';"
```

如果新表已存在，说明迁移已完成，可以跳过这一步。

### 问题3：文件上传后WebDAV中找不到

**可能原因**：
1. WebDAV服务离线
2. 认证失败
3. 磁盘空间不足

**排查步骤**：
```bash
# 1. 检查WebDAV状态
curl http://localhost:10000/api/admin/webdav/status

# 2. 检查待同步文件
curl http://localhost:10000/api/admin/webdav/sync-status

# 3. 检查临时存储目录
ls -la ./temp_storage/

# 4. 检查日志
grep "WebDAV upload" logs/app.log
```

### 问题4：缓存文件没有自动清理

**原因**：定时任务未启动

**解决方案**：
```bash
# 检查定时任务是否运行
curl http://localhost:10000/api/admin/scheduler/status

# 手动触发缓存清理
curl -X POST http://localhost:10000/api/admin/cache/cleanup
```

---

## 📞 技术支持

遇到问题时，请收集以下信息：

1. **错误日志**
   ```bash
   tail -n 100 logs/app.log > error_report.log
   ```

2. **环境信息**
   ```bash
   python3 --version
   sqlite3 --version
   cat .env | grep -v PASSWORD  # 不要包含密码
   ```

3. **数据库状态**
   ```bash
   sqlite3 data/uploads.db "SELECT name FROM sqlite_master WHERE type='table';"
   ```

4. **WebDAV测试结果**
   ```bash
   curl -v -u admin:adminlcs http://localhost:10100/dav/ 2>&1 | head -20
   ```

---

## ✅ 部署检查清单

完成以下所有步骤后，您的WebDAV集成功能就已经成功部署了！

- [ ] 1. 数据库已备份
- [ ] 2. WebDAV服务器可访问
- [ ] 3. 依赖已安装
- [ ] 4. 环境变量已配置
- [ ] 5. 必需目录已创建
- [ ] 6. 数据库迁移已执行
- [ ] 7. 数据库迁移已验证
- [ ] 8. 应用启动成功
- [ ] 9. WebDAV状态显示"在线"
- [ ] 10. 测试文件上传成功
- [ ] 11. 现有文件已迁移（如需要）
- [ ] 12. 故障降级测试通过
- [ ] 13. 备份功能测试通过
- [ ] 14. 所有验收标准通过
- [ ] 15. 监控和告警已配置

---

**部署完成！** 🎉

如果所有检查项都已完成，您的WebDAV集成功能已成功部署并可以在生产环境中使用。

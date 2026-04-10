# 单据上传管理系统 API 文档

来源: `http://localhost:8000/openapi.json` (Swagger UI: `http://localhost:8000/docs#/`)

## 基本信息
- Base URL: `http://localhost:8000`
- OpenAPI: 3.1.0
- Content-Type:
  - 上传: `multipart/form-data`
  - 其他请求: `application/json`
- 认证: 文档未标注鉴权方式

## 上传

### POST `/api/upload`
批量上传文件（异步处理）

流程:
1. 前端上传文件到后端
2. 后端保存记录到数据库（状态: `pending`）
3. 立即返回成功响应（<1秒）
4. 后台任务异步上传到用友云
5. 完成后更新状态（`success/failed`）

请求体（`multipart/form-data`）:
- `business_id` string，必填，业务单据ID（纯数字，用于用友云API）
- `doc_number` string，必填，单据编号（如 `SO20250103001`）
- `doc_type` string，必填，单据类型（销售/转库/其他）
- `product_type` string，可选，产品类型（如: 油脂/快消）
- `files[]` file[]，必填，文件列表（最多10个）

响应示例:
```json
{
  "success": true,
  "total": 10,
  "message": "已接收10个文件，正在后台上传中",
  "records": [
    {
      "id": 123,
      "file_name": "SO001_20251021_a3f2b1c4.jpg",
      "original_name": "photo.jpg",
      "status": "pending",
      "file_size": 102400
    }
  ]
}
```

## 上传历史

### GET `/api/history/{business_id}`
查询指定业务单据的上传历史

路径参数:
- `business_id` string，必填

响应示例:
```json
{
  "business_id": "000000",
  "total_count": 15,
  "success_count": 14,
  "failed_count": 1,
  "records": []
}
```

## 管理端

### GET `/api/admin/records`
获取上传记录列表（管理页面）

查询参数:
- `page` integer，默认 1，页码（从1开始）
- `page_size` integer，默认 20，最大 100
- `search` string，可选，模糊搜索单据编号或文件名
- `doc_type` string，可选，单据类型筛选（销售/转库/其他）
- `product_type` string，可选，产品类型筛选（油脂/快消）
- `status` string，可选，状态筛选（pending/uploading/success/failed）
- `start_date` string，可选，开始日期（YYYY-MM-DD）
- `end_date` string，可选，结束日期（YYYY-MM-DD）
- `logistics` string，可选，物流公司筛选（传入 `'全部物流'` 表示不过滤）

响应示例:
```json
{
  "total": 150,
  "page": 1,
  "page_size": 20,
  "total_pages": 8,
  "records": []
}
```

### DELETE `/api/admin/records`
软删除上传记录（批量）

请求体:
```json
{
  "ids": [1, 2, 3]
}
```

响应示例:
```json
{
  "success": true,
  "deleted_count": 3,
  "message": "成功删除3条记录"
}
```

说明:
- 软删除，仅标记 `deleted_at`
- 不删除本地文件
- 幂等: 重复删除已删除记录不报错
- 不调用用友云API

### GET `/api/admin/logistics-options`
获取物流公司列表（含默认“全部物流”）

### GET `/api/admin/export`
导出上传记录，支持导出 Excel 和/或 图片

查询参数:
- `search` string，可选，搜索关键词
- `doc_type` string，可选，单据类型筛选
- `product_type` string，可选，产品类型筛选
- `status` string，可选，状态筛选
- `start_date` string，可选，开始日期
- `end_date` string，可选，结束日期
- `logistics` string，可选，物流公司筛选
- `include_excel` boolean，默认 `true`，是否包含Excel
- `include_images` boolean，默认 `true`，是否包含图片

响应:
- Excel + images: ZIP 文件
- Excel only: 直接 `.xlsx`
- Images only: ZIP 文件（仅 images/）

### GET `/api/admin/statistics`
获取统计数据

响应示例:
```json
{
  "total_uploads": 1500,
  "pending_count": 10,
  "uploading_count": 5,
  "success_count": 1450,
  "failed_count": 35,
  "by_doc_type": {
    "销售": 800,
    "转库": 600,
    "其他": 100
  }
}
```

### PATCH `/api/admin/records/{record_id}/check`
更新记录的检查状态

路径参数:
- `record_id` integer，必填

请求体:
```json
{ "checked": true }
```

响应示例:
```json
{
  "success": true,
  "id": 123,
  "checked": true,
  "message": "检查状态已更新"
}
```

错误响应:
- 404: 记录不存在或已删除
- 422: 请求参数错误
- 500: 服务器内部错误

### PATCH `/api/admin/records/{record_id}/notes`
更新记录备注

路径参数:
- `record_id` integer，必填

请求体:
```json
{ "notes": "备注内容" }
```

响应示例:
```json
{
  "success": true,
  "id": 123,
  "notes": "备注内容",
  "message": "备注已更新"
}
```

错误响应:
- 400: 备注内容超过1000字符
- 404: 记录不存在或已删除
- 500: 服务器内部错误

### GET `/api/admin/files/{record_id}/preview`
预览文件（返回图片用于浏览器显示）

路径参数:
- `record_id` integer，必填

说明:
- 支持格式: jpg/jpeg/png/gif/bmp/webp
- 获取策略: 本地 -> WebDAV缓存 -> WebDAV下载并缓存

### GET `/api/admin/files/{record_id}/download`
下载单个文件（触发浏览器下载）

路径参数:
- `record_id` integer，必填

说明:
- 获取策略: 本地 -> WebDAV

## 迁移

### POST `/api/admin/migration/start`
开始文件迁移

请求体:
```json
{ "dry_run": false }
```

说明:
- `dry_run=true` 为演练模式，不实际迁移

### GET `/api/admin/migration/status/{migration_id}`
查询迁移状态

路径参数:
- `migration_id` string，必填

### GET `/api/admin/migration/list`
列出所有迁移任务

### DELETE `/api/admin/migration/cleanup`
清理迁移历史（保留最近10个）

### GET `/api/admin/migration/stats`
获取迁移统计信息

## WebDAV

### GET `/api/admin/webdav/status`
获取WebDAV服务状态

### POST `/api/admin/webdav/sync`
手动触发同步

请求体:
```json
{ "force": false }
```

### GET `/api/admin/webdav/files`
列出WebDAV文件

查询参数:
- `path` string，默认 `/`

### GET `/api/admin/webdav/health`
详细健康检查

### GET `/api/admin/webdav/cache/stats`
获取缓存统计信息

### POST `/api/admin/webdav/cache/cleanup`
触发缓存清理

### GET `/api/admin/webdav/backup/status`
获取备份状态

### POST `/api/admin/webdav/backup/trigger`
手动触发备份

### GET `/api/admin/webdav/config`
获取WebDAV配置信息（隐藏敏感信息）

### POST `/api/admin/webdav/test-connection`
测试WebDAV连接

## 页面与基础接口

### GET `/`
上传页面入口

查询参数:
- `business_id` string，必填，用友云业务单据ID
- `doc_number` string，必填，业务单据编号
- `doc_type` string，必填，单据类型（销售/转库/其他）

示例:
`/?business_id=2372677039643688969&doc_number=SO20250103001&doc_type=销售`

### GET `/admin`
管理页面入口

### GET `/api/health`
健康检查（Docker）

### GET `/uploaded_files/{file_path}`
智能文件访问接口

路径参数:
- `file_path` string，必填

说明:
1. 检查本地缓存是否存在且未过期
2. 命中直接返回
3. 未命中从WebDAV下载
4. 7天内文件写入缓存

## 数据模型（Schemas）

### DeleteRecordsRequest
```json
{ "ids": [1, 2, 3] }
```

### UpdateCheckStatusRequest
```json
{ "checked": true }
```

### UpdateNotesRequest
```json
{ "notes": "备注内容" }
```

### MigrationRequest
```json
{ "dry_run": false }
```

### MigrationStatus
```json
{
  "success": true,
  "migration_id": "string",
  "status": "string",
  "progress": {
    "total": 0,
    "completed": 0,
    "failed": 0,
    "percentage": 0
  },
  "errors": [],
  "message": "string"
}
```

### WebDAVStatusResponse
```json
{
  "success": true,
  "webdav_available": true,
  "last_check": "2024-01-01T00:00:00Z",
  "pending_sync_count": 0,
  "total_cached_files": 0,
  "cache_size_mb": 0,
  "message": "string"
}
```

### BackupStatusResponse
```json
{
  "success": true,
  "last_backup": {},
  "next_backup": "2024-01-01T00:00:00Z",
  "backup_count": 0,
  "total_size_mb": 0,
  "webdav_backup_count": 0
}
```

### SyncRequest
```json
{ "force": false }
```

### HTTPValidationError
```json
{
  "detail": [
    {
      "loc": ["string", 0],
      "msg": "string",
      "type": "string"
    }
  ]
}
```

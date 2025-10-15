# Docker 部署指南

本文档详细说明如何使用 Docker 部署单据上传管理系统。

## 前置要求

- Docker Engine 20.10+
- Docker Compose 2.0+
- 已配置好的用友云账号（AppKey 和 AppSecret）

## 快速开始

### 1. 配置环境变量

在项目根目录创建 `.env` 文件（或复制 `.env.example`）：

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置必需的用友云配置：

```env
# 用友云配置（必须设置）
YONYOU_APP_KEY=your_app_key_here
YONYOU_APP_SECRET=your_app_secret_here
```

### 2. 构建并启动容器

使用 Docker Compose 一键启动：

```bash
docker-compose up -d
```

首次启动会自动构建镜像，这可能需要几分钟时间。

### 3. 验证部署

检查容器状态：

```bash
docker-compose ps
```

查看日志：

```bash
docker-compose logs -f
```

访问健康检查端点：

```bash
curl http://localhost:10000/api/health
```

预期返回：

```json
{
  "status": "healthy",
  "app": "单据上传管理系统",
  "version": "1.0.0"
}
```

### 4. 访问应用

- 上传页面：http://localhost:10000/?business_id=xxx&doc_number=xxx&doc_type=销售
- 管理页面：http://localhost:10000/admin

## Docker 配置说明

### Dockerfile

基于 Python 3.9 的精简镜像构建，包含以下特性：

- **多阶段构建优化**：减小镜像体积
- **安全性**：使用非 root 用户运行（可选）
- **健康检查**：自动监控应用状态
- **数据持久化**：使用卷挂载保存数据和日志

### docker-compose.yml

主要配置项：

- **端口映射**：10000:10000
- **环境变量**：所有配置通过环境变量注入
- **卷挂载**：
  - `./data:/app/data` - 数据库和上传文件
  - `./logs:/app/logs` - 应用日志
- **健康检查**：每30秒检查一次应用状态
- **自动重启**：容器异常退出时自动重启

### .dockerignore

排除不必要的文件，加快构建速度并减小镜像体积：

- Python 缓存和虚拟环境
- 测试文件和覆盖率报告
- IDE 配置文件
- Git 仓库
- 本地数据和日志文件

## 常用命令

### 启动服务

```bash
# 前台启动（查看日志）
docker-compose up

# 后台启动
docker-compose up -d

# 重新构建并启动
docker-compose up -d --build
```

### 停止服务

```bash
# 停止容器
docker-compose stop

# 停止并删除容器
docker-compose down

# 停止并删除容器、网络、卷（谨慎使用，会删除数据）
docker-compose down -v
```

### 查看日志

```bash
# 查看所有日志
docker-compose logs

# 实时查看日志
docker-compose logs -f

# 查看最后100行日志
docker-compose logs --tail=100

# 查看特定服务的日志
docker-compose logs upload-manager
```

### 进入容器

```bash
# 进入容器 shell
docker-compose exec upload-manager bash

# 或使用 sh（精简镜像）
docker-compose exec upload-manager sh
```

### 重启服务

```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart upload-manager
```

### 查看容器状态

```bash
# 查看运行状态
docker-compose ps

# 查看资源使用情况
docker stats upload-manager
```

## 数据持久化

应用数据和日志通过卷挂载持久化到宿主机：

- **数据目录**：`./data`
  - `uploads.db` - SQLite 数据库
  - `uploaded_files/` - 上传的文件

- **日志目录**：`./logs`
  - 应用运行日志

### 备份数据

```bash
# 备份数据目录
tar -czf backup-$(date +%Y%m%d).tar.gz data/

# 备份数据库
cp data/uploads.db data/uploads.db.backup
```

### 恢复数据

```bash
# 停止服务
docker-compose down

# 恢复数据
tar -xzf backup-20250115.tar.gz

# 启动服务
docker-compose up -d
```

## 环境变量配置

所有配置项都可以通过环境变量覆盖，详见 `docker-compose.yml`：

### 应用配置

- `APP_NAME` - 应用名称
- `APP_VERSION` - 应用版本
- `HOST` - 监听地址（默认 0.0.0.0）
- `PORT` - 监听端口（默认 10000）
- `DEBUG` - 调试模式（默认 false）

### 用友云配置（必需）

- `YONYOU_APP_KEY` - 用友云 AppKey
- `YONYOU_APP_SECRET` - 用友云 AppSecret
- `YONYOU_BUSINESS_TYPE` - 业务类型
- `YONYOU_AUTH_URL` - 认证 URL
- `YONYOU_UPLOAD_URL` - 上传 URL

### 上传配置

- `MAX_FILE_SIZE` - 单文件最大大小（字节，默认 10MB）
- `MAX_FILES_PER_REQUEST` - 单次请求最大文件数（默认 10）

### 重试配置

- `MAX_RETRY_COUNT` - 最大重试次数（默认 3）
- `RETRY_DELAY` - 重试延迟（秒，默认 2）
- `REQUEST_TIMEOUT` - 请求超时（秒，默认 30）

### 并发控制

- `MAX_CONCURRENT_UPLOADS` - 最大并发上传数（默认 3）

## 故障排查

### 容器无法启动

1. 检查端口占用：

```bash
lsof -i :10000
```

2. 查看容器日志：

```bash
docker-compose logs upload-manager
```

3. 检查环境变量配置：

```bash
docker-compose config
```

### 健康检查失败

1. 查看健康检查状态：

```bash
docker inspect --format='{{json .State.Health}}' upload-manager | jq
```

2. 手动测试健康检查端点：

```bash
docker-compose exec upload-manager curl http://localhost:10000/api/health
```

### 数据库连接错误

1. 确认数据目录已创建且有写权限：

```bash
ls -la data/
```

2. 检查 SQLite 数据库文件：

```bash
docker-compose exec upload-manager ls -la /app/data/
```

### 文件上传失败

1. 检查用友云配置：

```bash
docker-compose exec upload-manager env | grep YONYOU
```

2. 查看上传日志：

```bash
docker-compose logs -f upload-manager | grep upload
```

## 生产环境建议

### 1. 使用环境变量文件

不要在 `docker-compose.yml` 中硬编码敏感信息：

```yaml
env_file:
  - .env
```

### 2. 限制资源使用

添加资源限制防止容器占用过多资源：

```yaml
deploy:
  resources:
    limits:
      cpus: '1'
      memory: 1G
    reservations:
      cpus: '0.5'
      memory: 512M
```

### 3. 使用外部卷

生产环境建议使用命名卷或外部存储：

```yaml
volumes:
  app_data:
    driver: local
```

### 4. 配置日志驱动

使用 JSON 日志驱动并限制日志大小：

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### 5. 设置时区

确保容器使用正确的时区：

```yaml
environment:
  - TZ=Asia/Shanghai
```

### 6. 使用 Nginx 反向代理

在生产环境中，建议在前面加一层 Nginx 反向代理：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 10M;

    location / {
        proxy_pass http://localhost:10000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 更新应用

### 1. 拉取最新代码

```bash
git pull
```

### 2. 重新构建镜像

```bash
docker-compose build
```

### 3. 重启服务

```bash
docker-compose up -d
```

### 4. 验证更新

```bash
curl http://localhost:10000/api/health
```

## 卸载

完全删除应用和数据：

```bash
# 停止并删除容器、网络
docker-compose down

# 删除镜像
docker rmi upload-manager

# 删除数据（可选，谨慎操作）
rm -rf data/ logs/
```

## 技术支持

如有问题，请查看：

1. 应用日志：`docker-compose logs -f`
2. 健康检查状态：`docker inspect upload-manager`
3. 系统资源：`docker stats upload-manager`

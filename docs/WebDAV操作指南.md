# WebDAV 操作指南

## 服务器信息
- **服务器地址**: `http://localhost:10100/dav/`
- **用户名**: `admin`
- **密码**: `adminlcs`

## 目录结构

```
/dav/
└── onedrive_lcs/
    ├── djgl_backup_full_20251026_103322.tar.gz (283MB)
    ├── test_file.txt (122字节)
    ├── 截屏2025-10-03 11.33.29.png (231KB)
    └── downloaded_test_file.txt (237字节)
```

## 常用操作命令

### 1. 列出目录文件

#### 列出根目录
```bash
curl -u admin:adminlcs -X PROPFIND http://localhost:10100/dav/ \
  -H "Depth: 1" \
  -H "Content-Type: application/xml" \
  -d '<?xml version="1.0" encoding="utf-8"?>
      <propfind xmlns="DAV:">
        <prop>
          <displayname/>
          <resourcetype/>
          <getcontentlength/>
          <getlastmodified/>
        </prop>
      </propfind>'
```

#### 列出特定目录（如 onedrive_lcs）
```bash
curl -u admin:adminlcs -X PROPFIND http://localhost:10100/dav/onedrive_lcs/ \
  -H "Depth: 1" \
  -H "Content-Type: application/xml" \
  -d '<?xml version="1.0" encoding="utf-8"?>
      <propfind xmlns="DAV:">
        <prop>
          <displayname/>
          <resourcetype/>
          <getcontentlength/>
          <getlastmodified/>
        </prop>
      </propfind>'
```

### 2. 下载文件

#### 下载普通文件
```bash
curl -u admin:adminlcs -o "本地文件名" "http://localhost:10100/dav/远程文件路径"
```

#### 示例：下载图片文件
```bash
curl -u admin:adminlcs -o "截图.png" "http://localhost:10100/dav/onedrive_lcs/截屏2025-10-03%2011.33.29.png"
```

#### 下载大文件（跟随重定向）
```bash
curl -u admin:adminlcs -L -o "备份文件.tar.gz" "http://localhost:10100/dav/onedrive_lcs/djgl_backup_full_20251026_103322.tar.gz"
```

### 3. 上传文件

#### 基本上传
```bash
curl -u admin:adminlcs -T "本地文件路径" "http://localhost:10100/dav/目标路径"
```

#### 示例：上传文本文件
```bash
curl -u admin:adminlcs -T "test.txt" "http://localhost:10100/dav/onedrive_lcs/test.txt"
```

#### 上传中文文件名文件
```bash
curl -u admin:adminlcs -T "图片.png" "http://localhost:10100/dav/onedrive_lcs/图片.png"
```

### 4. 直接访问链接（带认证）

#### 获取文件直接链接
```bash
# 获取响应头信息，查看重定向地址
curl -I -u admin:adminlcs "http://localhost:10100/dav/onedrive_lcs/文件名"
```

#### 直接访问文件（在浏览器中打开）
```
http://admin:adminlcs@localhost:10100/dav/onedrive_lcs/文件名
```

#### 示例：直接访问图片
```
http://admin:adminlcs@localhost:10100/dav/onedrive_lcs/截屏2025-10-03%2011.33.29.png
```

### 5. 创建目录

```bash
curl -u admin:adminlcs -X MKCOL "http://localhost:10100/dav/新目录名/"
```

### 6. 删除文件

```bash
curl -u admin:adminlcs -X DELETE "http://localhost:10100/dav/文件路径"
```

### 7. 删除目录

```bash
curl -u admin:adminlcs -X DELETE "http://localhost:10100/dav/目录名/"
```

## 文件URL编码说明

当文件名包含中文或特殊字符时，需要进行URL编码：

- `截屏2025-10-03 11.33.29.png` → `%E6%88%AA%E5%B1%8F2025-10-03%2011.33.29.png`
- 空格 → `%20`
- 中文字符自动编码

可以使用以下命令获取编码后的URL：
```bash
python3 -c "import urllib.parse; print(urllib.parse.quote('截屏2025-10-03 11.33.29.png'))"
```

## 注意事项

1. **认证信息**：所有操作都需要提供用户名和密码
2. **文件大小限制**：大文件上传可能需要更长时间
3. **网络稳定性**：上传下载过程中保持网络连接稳定
4. **重定向处理**：某些文件访问会重定向到Microsoft服务
5. **中文文件名**：确保正确的URL编码
6. **权限问题**：确保有足够的读写权限

## 工具推荐

### 命令行工具
- `curl` - 基础WebDAV操作
- `cadaver` - 交互式WebDAV客户端

### GUI工具
- Cyberduck - 跨平台WebDAV客户端
- FileZilla - 支持WebDAV协议
- Windows资源管理器 - 直接映射网络驱动器

### macOS挂载WebDAV
```bash
# 在Finder中：前往 -> 连接服务器
# 输入：http://localhost:10100/dav/
# 用户名：admin
# 密码：adminlcs
```

## 常见问题解决

### Q: 上传失败返回401错误
A: 检查用户名密码是否正确，确保使用正确的认证格式

### Q: 下载的文件大小不正确
A: 使用 `-L` 参数跟随重定向，或者分段下载大文件

### Q: 中文文件名无法访问
A: 确保文件名已正确进行URL编码

### Q: 连接超时
A: 检查网络连接，或者增加超时时间参数

---

*文档创建时间：2025-10-27*
*服务器：http://localhost:10100/dav/*
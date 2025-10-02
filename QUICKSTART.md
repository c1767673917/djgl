# 快速启动指南

## 一、安装依赖（首次运行）

```bash
# 进入项目目录
cd "/Users/lichuansong/Desktop/projects/单据上传管理"

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 二、启动服务

```bash
# 确保虚拟环境已激活
source venv/bin/activate

# 启动服务
python run.py
```

看到以下信息表示启动成功：
```
INFO:     Uvicorn running on http://0.0.0.0:10000
```

## 三、访问测试

### 1. 获取本机IP地址

```bash
# macOS
ifconfig | grep "inet " | grep -v 127.0.0.1

# 假设输出: inet 192.168.1.100 netmask ...
# 则本机IP为: 192.168.1.100
```

### 2. 在浏览器中访问

```
http://192.168.1.100:10000/123456
```

将 `192.168.1.100` 替换为你的实际IP地址，`123456` 为6位业务单据号。

### 3. API文档

```
http://localhost:10000/docs
```

## 四、生成二维码

访问在线二维码生成工具：
https://www.qr-code-generator.com/

输入URL：
```
http://你的IP:10000/123456
```

下载二维码图片，打印后扫描即可使用。

## 五、测试上传

1. 用手机扫描二维码
2. 点击上传区域，选择图片或拍照
3. 点击"开始上传"
4. 查看上传进度和结果

## 六、查看历史记录

在上传页面点击"查看上传历史"按钮，或直接访问：
```
http://192.168.1.100:10000/api/history/123456
```

## 七、停止服务

在终端按 `Ctrl + C` 停止服务。

## 八、常见问题

### Q1: 无法访问服务
- 检查防火墙是否允许10000端口
- 确认IP地址正确
- 确认服务已启动

### Q2: 上传失败
- 检查文件大小是否超过10MB
- 检查文件格式是否为图片
- 查看控制台错误信息

### Q3: 数据库文件在哪里
```
./data/uploads.db
```

查看数据库：
```bash
sqlite3 data/uploads.db
SELECT * FROM upload_history;
```

## 九、后台运行（可选）

```bash
# 后台运行
nohup python run.py > logs/app.log 2>&1 &

# 查看日志
tail -f logs/app.log

# 停止服务
ps aux | grep "python run.py"
kill <PID>
```

## 十、配置说明

所有配置在 `.env` 文件中：

```bash
# 修改端口
PORT=10000

# 修改最大文件大小（字节）
MAX_FILE_SIZE=10485760

# 修改最大文件数量
MAX_FILES_PER_REQUEST=10
```

修改后需要重启服务。

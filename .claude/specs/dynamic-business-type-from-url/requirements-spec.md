# 技术规范文档 - 动态businessType映射实现

生成日期: 2025-10-17
项目: 单据上传管理系统
功能: 根据URL参数doc_type动态映射businessType

---

## 问题陈述

### 业务问题
当前系统的用友云上传功能使用固定的 `businessType` 值（`yonbip-scm-scmsa`），无法根据不同的单据类型使用不同的业务类型。这导致转库单和其他类型单据无法使用正确的用友云业务类型进行上传。

### 当前状态
- **固定配置**: `YONYOU_BUSINESS_TYPE = "yonbip-scm-scmsa"` (app/core/config.py:17)
- **使用位置**: `YonYouClient.upload_file()` 方法中硬编码使用 `self.business_type` (app/core/yonyou_client.py:93)
- **URL参数**: 系统已支持 `doc_type` 参数传递,但未用于businessType映射
- **验证逻辑**: API层已有 `doc_type` 枚举验证（销售/转库/其他）

### 预期结果
- 销售单据上传时使用 `yonbip-scm-scmsa`
- 转库单据上传时使用 `yonbip-scm-stock`
- 其他单据上传时使用 `yonbip-scm-stock`
- 保持向后兼容性,不影响现有功能

---

## 解决方案概述

### 实现策略
采用**参数化设计**模式,将固定的 `businessType` 改造为可动态传递的参数,在API层实现映射逻辑,传递给底层客户端。

### 核心变更
1. **YonYouClient.upload_file()**: 添加可选的 `business_type` 参数
2. **API upload_files()**: 实现 doc_type → businessType 的映射逻辑
3. **默认值保留**: 配置中的 `YONYOU_BUSINESS_TYPE` 作为默认值和向后兼容

### 成功标准
1. ✅ 销售单据使用 `yonbip-scm-scmsa` 上传成功
2. ✅ 转库单据使用 `yonbip-scm-stock` 上传成功
3. ✅ 其他单据使用 `yonbip-scm-stock` 上传成功
4. ✅ 现有功能不受影响,向后兼容
5. ✅ 新增单据类型需显式添加映射

---

## 技术实现

### 数据库变更
**无需变更** - 此功能不涉及数据库schema修改

### 代码变更

#### 1. 修改 YonYouClient.upload_file() 方法

**文件路径**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/yonyou_client.py`

**修改位置**: 第77-131行

**变更内容**:

**修改前**:
```python
async def upload_file(
    self,
    file_content: bytes,
    file_name: str,
    business_id: str,
    retry_count: int = 0
) -> Dict[str, Any]:
    """上传文件到用友云"""
    try:
        # 获取access_token
        access_token = await self.get_access_token()

        # URL编码token
        encoded_token = urllib.parse.quote(access_token, safe='')

        # 构建请求URL
        url = f"{self.upload_url}?access_token={encoded_token}&businessType={self.business_type}&businessId={business_id}"

        # ... 后续代码
```

**修改后**:
```python
async def upload_file(
    self,
    file_content: bytes,
    file_name: str,
    business_id: str,
    retry_count: int = 0,
    business_type: Optional[str] = None  # 新增可选参数
) -> Dict[str, Any]:
    """上传文件到用友云

    Args:
        file_content: 文件二进制内容
        file_name: 文件名
        business_id: 业务单据ID
        retry_count: 重试次数（内部使用）
        business_type: 业务类型（可选,默认使用实例配置）

    Returns:
        上传结果字典
    """
    try:
        # 获取access_token
        access_token = await self.get_access_token()

        # URL编码token
        encoded_token = urllib.parse.quote(access_token, safe='')

        # 使用传入的business_type,如果未提供则使用实例默认值
        effective_business_type = business_type or self.business_type

        # 构建请求URL（使用动态businessType）
        url = f"{self.upload_url}?access_token={encoded_token}&businessType={effective_business_type}&businessId={business_id}"

        # ... 后续代码保持不变
```

**关键变更点**:
1. 函数签名添加 `business_type: Optional[str] = None` 参数
2. 使用 `effective_business_type = business_type or self.business_type` 选择有效值
3. URL构建时使用 `effective_business_type` 替代固定的 `self.business_type`
4. 递归调用时需要传递 `business_type` 参数

**完整修改后的函数**:
```python
async def upload_file(
    self,
    file_content: bytes,
    file_name: str,
    business_id: str,
    retry_count: int = 0,
    business_type: Optional[str] = None
) -> Dict[str, Any]:
    """上传文件到用友云

    Args:
        file_content: 文件二进制内容
        file_name: 文件名
        business_id: 业务单据ID
        retry_count: 重试次数（内部使用）
        business_type: 业务类型（可选,默认使用实例配置）

    Returns:
        上传结果字典
    """
    try:
        # 获取access_token
        access_token = await self.get_access_token()

        # URL编码token(token中包含特殊字符如/, +, =等需要编码)
        encoded_token = urllib.parse.quote(access_token, safe='')

        # 使用传入的business_type,如果未提供则使用实例默认值
        effective_business_type = business_type or self.business_type

        # 构建请求URL（使用动态businessType）
        url = f"{self.upload_url}?access_token={encoded_token}&businessType={effective_business_type}&businessId={business_id}"

        # 构建multipart/form-data请求
        files = {
            "files": (file_name, file_content, "application/octet-stream")
        }

        # 发送请求
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
            response = await client.post(url, files=files)
            result = response.json()

        # 检查响应
        if result.get("code") == "200":
            return {
                "success": True,
                "data": result["data"]["data"][0]
            }
        else:
            # 特殊处理: Token无效或过期时自动刷新重试
            # 错误码: 1090003500065 (token过期), 310036 (非法token)
            error_code = str(result.get("code"))
            if error_code in ["1090003500065", "310036"] and retry_count == 0:
                access_token = await self.get_access_token(force_refresh=True)
                # 递归调用时传递business_type参数
                return await self.upload_file(file_content, file_name, business_id, retry_count + 1, business_type)

            return {
                "success": False,
                "error_code": error_code,
                "error_message": result.get("message", "未知错误")
            }

    except Exception as e:
        return {
            "success": False,
            "error_code": "NETWORK_ERROR",
            "error_message": str(e)
        }
```

#### 2. 修改 API upload_files() 方法

**文件路径**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/upload.py`

**修改位置**: 第59-219行

**变更内容**:

在 `upload_files()` 函数开始处添加映射逻辑,在调用 `yonyou_client.upload_file()` 时传递映射后的值。

**步骤1: 在函数顶部添加映射逻辑**

在第95行（doc_type验证之后）添加:

```python
# doc_type到businessType的映射
DOC_TYPE_TO_BUSINESS_TYPE = {
    "销售": "yonbip-scm-scmsa",
    "转库": "yonbip-scm-stock",
    "其他": "yonbip-scm-stock"
}

# 获取映射后的businessType
business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(doc_type, settings.YONYOU_BUSINESS_TYPE)
```

**步骤2: 修改上传调用**

修改第155行的 `yonyou_client.upload_file()` 调用:

**修改前**:
```python
result = await yonyou_client.upload_file(
    file_content,
    new_filename,
    business_id
)
```

**修改后**:
```python
result = await yonyou_client.upload_file(
    file_content,
    new_filename,
    business_id,
    retry_count=0,  # 显式传递
    business_type=business_type  # 传递映射后的businessType
)
```

**完整的修改后upload_files函数片段**:

```python
@router.post("/upload")
async def upload_files(
    business_id: str = Form(..., description="业务单据ID"),
    doc_number: str = Form(..., description="单据编号"),
    doc_type: str = Form(..., description="单据类型"),
    files: List[UploadFile] = File(...)
):
    """
    批量上传文件到用友云

    请求参数:
    - business_id: 业务单据ID（纯数字，用于用友云API）
    - doc_number: 单据编号（业务标识，如SO20250103001）
    - doc_type: 单据类型（销售/转库/其他）
    - files: 文件列表 (最多10个)

    响应格式:
    {
        "success": true,
        "total": 10,
        "succeeded": 9,
        "failed": 1,
        "results": [...]
    }
    """
    # 验证businessId格式
    if not business_id or not business_id.isdigit():
        raise HTTPException(status_code=400, detail="businessId必须为纯数字")

    # 验证doc_type枚举值
    valid_doc_types = ["销售", "转库", "其他"]
    if doc_type not in valid_doc_types:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type必须为以下值之一: {', '.join(valid_doc_types)}"
        )

    # doc_type到businessType的映射
    DOC_TYPE_TO_BUSINESS_TYPE = {
        "销售": "yonbip-scm-scmsa",
        "转库": "yonbip-scm-stock",
        "其他": "yonbip-scm-stock"
    }

    # 获取映射后的businessType
    business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(doc_type, settings.YONYOU_BUSINESS_TYPE)

    # 验证doc_number格式
    if not doc_number or len(doc_number.strip()) == 0:
        raise HTTPException(status_code=400, detail="doc_number不能为空")

    # ... 文件验证代码保持不变 ...

    # 并发上传（限制并发数为3）
    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_UPLOADS)

    async def upload_single_file(upload_file: UploadFile):
        async with semaphore:
            # ... 文件读取和验证代码保持不变 ...

            # 上传到用友云（使用新文件名和映射后的businessType）
            for attempt in range(settings.MAX_RETRY_COUNT):
                result = await yonyou_client.upload_file(
                    file_content,
                    new_filename,
                    business_id,
                    retry_count=0,  # 显式传递
                    business_type=business_type  # 传递映射后的businessType
                )

                if result["success"]:
                    # ... 成功处理代码保持不变 ...
                else:
                    # ... 失败处理代码保持不变 ...

    # ... 其余代码保持不变 ...
```

#### 3. 配置文件保留

**文件路径**: `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/config.py`

**无需修改** - 保留现有的 `YONYOU_BUSINESS_TYPE = "yonbip-scm-scmsa"` 作为:
1. 销售单据的businessType值
2. 系统默认值（向后兼容）
3. 映射字典的fallback值

### API变更
**无API端点变更** - 使用现有的 `/api/upload` 端点,参数保持不变

### 配置变更
**无配置变更** - 保留现有的环境变量和配置项

---

## 实现序列

### Phase 1: 修改YonYouClient (核心层)
**目标**: 使 `upload_file()` 方法支持动态 `business_type` 参数

**任务**:
1. 打开文件 `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/yonyou_client.py`
2. 修改 `upload_file()` 方法签名,添加 `business_type: Optional[str] = None` 参数
3. 在方法内部添加逻辑: `effective_business_type = business_type or self.business_type`
4. 修改URL构建代码,使用 `effective_business_type`
5. 修改递归调用代码,传递 `business_type` 参数
6. 更新方法的docstring,说明新参数

**验证**:
- 代码语法检查通过
- 类型提示正确
- 向后兼容（不传参数时使用默认值）

### Phase 2: 实现映射逻辑 (API层)
**目标**: 在API层根据 `doc_type` 映射 `businessType` 并传递给客户端

**任务**:
1. 打开文件 `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/upload.py`
2. 在 `upload_files()` 函数中,在doc_type验证之后添加映射字典
3. 定义映射字典: `DOC_TYPE_TO_BUSINESS_TYPE = {...}`
4. 使用 `.get()` 方法获取映射值,提供默认值
5. 修改 `yonyou_client.upload_file()` 调用,传递 `business_type` 参数
6. 添加注释说明映射逻辑

**验证**:
- 映射逻辑正确
- 所有doc_type都有对应的映射
- 调用参数正确传递

### Phase 3: 测试验证
**目标**: 手动测试各种单据类型的上传功能

**任务**:
1. 启动应用: `python run.py`
2. 测试销售单据上传 (doc_type=销售)
3. 测试转库单据上传 (doc_type=转库)
4. 测试其他单据上传 (doc_type=其他)
5. 检查用友云API调用的businessType参数
6. 验证上传成功并记录到数据库

**验证标准**:
- ✅ 销售单据使用 `yonbip-scm-scmsa`
- ✅ 转库单据使用 `yonbip-scm-stock`
- ✅ 其他单据使用 `yonbip-scm-stock`
- ✅ 所有类型都能成功上传

---

## 映射逻辑实现

### 映射规则

使用Python字典实现 doc_type → businessType 的映射:

```python
DOC_TYPE_TO_BUSINESS_TYPE = {
    "销售": "yonbip-scm-scmsa",
    "转库": "yonbip-scm-stock",
    "其他": "yonbip-scm-stock"
}
```

### 默认值处理

使用字典的 `.get()` 方法提供fallback:

```python
business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(doc_type, settings.YONYOU_BUSINESS_TYPE)
```

**逻辑**:
- 如果 `doc_type` 在字典中,使用映射值
- 如果 `doc_type` 不在字典中,使用配置默认值 `yonbip-scm-scmsa`

### 扩展新单据类型

**步骤**:
1. 在 `app/api/upload.py` 中修改 `valid_doc_types` 列表,添加新类型
2. 在 `DOC_TYPE_TO_BUSINESS_TYPE` 字典中添加新映射
3. 重启应用即可生效

**示例**:
```python
# 1. 添加新的有效类型
valid_doc_types = ["销售", "转库", "其他", "采购"]  # 新增"采购"

# 2. 添加映射规则
DOC_TYPE_TO_BUSINESS_TYPE = {
    "销售": "yonbip-scm-scmsa",
    "转库": "yonbip-scm-stock",
    "其他": "yonbip-scm-stock",
    "采购": "yonbip-scm-purchase"  # 新增映射
}
```

---

## 数据流

### 完整流程

```
1. 前端/用户
   ↓ (发送请求)
   POST /api/upload?doc_type=转库&business_id=123&doc_number=SO001

2. upload.py::upload_files()
   ↓ (验证参数)
   doc_type验证 ✓

   ↓ (映射逻辑)
   DOC_TYPE_TO_BUSINESS_TYPE.get("转库")
   → "yonbip-scm-stock"

   ↓ (传递参数)
   yonyou_client.upload_file(
       file_content=...,
       file_name=...,
       business_id="123",
       business_type="yonbip-scm-stock"  # 映射后的值
   )

3. yonyou_client.py::upload_file()
   ↓ (参数处理)
   effective_business_type = "yonbip-scm-stock" or self.business_type
   → "yonbip-scm-stock"

   ↓ (构建URL)
   url = f"...?businessType=yonbip-scm-stock&businessId=123"

   ↓ (HTTP请求)
   POST https://c4.yonyoucloud.com/.../file

4. 用友云API
   ↓ (返回结果)
   {"code": "200", "data": {...}}

5. 保存到数据库
   upload_history表记录上传结果
```

### 关键节点

| 节点 | 位置 | 处理内容 |
|------|------|----------|
| 参数接收 | upload.py:60-64 | 接收 doc_type 表单参数 |
| 参数验证 | upload.py:89-94 | 验证 doc_type 枚举值 |
| **映射逻辑** | upload.py:96-102 | **doc_type → businessType 映射** |
| 参数传递 | upload.py:155-160 | 调用 upload_file() 传递 business_type |
| 参数应用 | yonyou_client.py:83-93 | 使用 business_type 构建URL |
| API调用 | yonyou_client.py:101-103 | 发送HTTP请求到用友云 |

---

## 错误处理

### 复用现有验证

**doc_type枚举验证** (upload.py:89-94):
```python
valid_doc_types = ["销售", "转库", "其他"]
if doc_type not in valid_doc_types:
    raise HTTPException(
        status_code=400,
        detail=f"doc_type必须为以下值之一: {', '.join(valid_doc_types)}"
    )
```

**说明**: 此验证确保只有合法的 doc_type 值能到达映射逻辑,无需额外验证。

### 边缘情况处理

#### 1. doc_type 未在映射字典中

**处理方式**:
```python
business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(doc_type, settings.YONYOU_BUSINESS_TYPE)
```

**结果**: 使用默认值 `yonbip-scm-scmsa` (向后兼容)

#### 2. business_type 参数未传递

**处理方式** (yonyou_client.py):
```python
effective_business_type = business_type or self.business_type
```

**结果**: 使用实例默认值 `self.business_type` (向后兼容)

#### 3. 用友云API返回错误

**现有处理逻辑** (yonyou_client.py:106-123):
- Token过期: 自动刷新并重试
- 其他错误: 返回错误信息
- 网络异常: 捕获并返回错误

**说明**: businessType错误会被用友云API返回,现有错误处理逻辑已覆盖。

### 错误码映射

| 场景 | HTTP状态码 | 错误信息 |
|------|-----------|---------|
| doc_type不合法 | 400 | "doc_type必须为以下值之一: 销售, 转库, 其他" |
| businessType错误 | 200 (API层) | 用友云返回的错误信息 |
| 网络异常 | 200 (API层) | "NETWORK_ERROR: ..." |

---

## 代码变更示例

### 完整代码对比

#### 文件1: app/core/yonyou_client.py

**修改前** (第77-93行):
```python
async def upload_file(
    self,
    file_content: bytes,
    file_name: str,
    business_id: str,
    retry_count: int = 0
) -> Dict[str, Any]:
    """上传文件到用友云"""
    try:
        # 获取access_token
        access_token = await self.get_access_token()

        # URL编码token(token中包含特殊字符如/, +, =等需要编码)
        encoded_token = urllib.parse.quote(access_token, safe='')

        # 构建请求URL
        url = f"{self.upload_url}?access_token={encoded_token}&businessType={self.business_type}&businessId={business_id}"
```

**修改后**:
```python
async def upload_file(
    self,
    file_content: bytes,
    file_name: str,
    business_id: str,
    retry_count: int = 0,
    business_type: Optional[str] = None  # 新增参数
) -> Dict[str, Any]:
    """上传文件到用友云

    Args:
        file_content: 文件二进制内容
        file_name: 文件名
        business_id: 业务单据ID
        retry_count: 重试次数（内部使用）
        business_type: 业务类型（可选,默认使用实例配置）

    Returns:
        上传结果字典
    """
    try:
        # 获取access_token
        access_token = await self.get_access_token()

        # URL编码token(token中包含特殊字符如/, +, =等需要编码)
        encoded_token = urllib.parse.quote(access_token, safe='')

        # 使用传入的business_type,如果未提供则使用实例默认值
        effective_business_type = business_type or self.business_type

        # 构建请求URL（使用动态businessType）
        url = f"{self.upload_url}?access_token={encoded_token}&businessType={effective_business_type}&businessId={business_id}"
```

**关键变更**:
1. ✅ 添加 `business_type: Optional[str] = None` 参数
2. ✅ 添加 `effective_business_type = business_type or self.business_type` 逻辑
3. ✅ URL使用 `effective_business_type` 替代 `self.business_type`
4. ✅ 更新docstring说明新参数

**递归调用修改** (第116行):

**修改前**:
```python
return await self.upload_file(file_content, file_name, business_id, retry_count + 1)
```

**修改后**:
```python
return await self.upload_file(file_content, file_name, business_id, retry_count + 1, business_type)
```

#### 文件2: app/api/upload.py

**修改位置1**: 添加映射逻辑 (第95行之后)

**插入代码**:
```python
    # doc_type到businessType的映射
    DOC_TYPE_TO_BUSINESS_TYPE = {
        "销售": "yonbip-scm-scmsa",
        "转库": "yonbip-scm-stock",
        "其他": "yonbip-scm-stock"
    }

    # 获取映射后的businessType
    business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(doc_type, settings.YONYOU_BUSINESS_TYPE)
```

**修改位置2**: 修改上传调用 (第155行)

**修改前**:
```python
result = await yonyou_client.upload_file(
    file_content,
    new_filename,  # 上传到用友云时使用新文件名
    business_id
)
```

**修改后**:
```python
result = await yonyou_client.upload_file(
    file_content,
    new_filename,  # 上传到用友云时使用新文件名
    business_id,
    retry_count=0,  # 显式传递retry_count
    business_type=business_type  # 传递映射后的businessType
)
```

**完整上下文**:
```python
@router.post("/upload")
async def upload_files(
    business_id: str = Form(..., description="业务单据ID"),
    doc_number: str = Form(..., description="单据编号"),
    doc_type: str = Form(..., description="单据类型"),
    files: List[UploadFile] = File(...)
):
    """批量上传文件到用友云"""

    # 验证businessId格式
    if not business_id or not business_id.isdigit():
        raise HTTPException(status_code=400, detail="businessId必须为纯数字")

    # 验证doc_type枚举值
    valid_doc_types = ["销售", "转库", "其他"]
    if doc_type not in valid_doc_types:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type必须为以下值之一: {', '.join(valid_doc_types)}"
        )

    # ============ 新增: 映射逻辑 ============
    # doc_type到businessType的映射
    DOC_TYPE_TO_BUSINESS_TYPE = {
        "销售": "yonbip-scm-scmsa",
        "转库": "yonbip-scm-stock",
        "其他": "yonbip-scm-stock"
    }

    # 获取映射后的businessType
    business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(doc_type, settings.YONYOU_BUSINESS_TYPE)
    # ======================================

    # 验证doc_number格式
    if not doc_number or len(doc_number.strip()) == 0:
        raise HTTPException(status_code=400, detail="doc_number不能为空")

    # ... 其余验证代码 ...

    async def upload_single_file(upload_file: UploadFile):
        async with semaphore:
            # ... 文件读取代码 ...

            # 上传到用友云（使用新文件名）
            for attempt in range(settings.MAX_RETRY_COUNT):
                # ============ 修改: 传递business_type ============
                result = await yonyou_client.upload_file(
                    file_content,
                    new_filename,
                    business_id,
                    retry_count=0,
                    business_type=business_type  # 传递映射后的值
                )
                # ===============================================

                if result["success"]:
                    # ... 成功处理 ...
```

---

## 验证计划

### 单元测试 (跳过)
**用户要求**: 跳过自动化测试,采用手动测试验证

### 手动测试场景

#### 测试场景1: 销售单据上传

**前置条件**:
- 应用已启动: `python run.py`
- 用友云API可访问

**测试步骤**:
1. 访问: `http://localhost:10000/?business_id=123456&doc_number=SO001&doc_type=销售`
2. 选择图片文件上传
3. 点击"上传文件"按钮

**预期结果**:
- ✅ 上传成功
- ✅ 用友云API调用参数: `businessType=yonbip-scm-scmsa`
- ✅ 数据库记录保存成功

**验证方法**:
```bash
# 检查数据库记录
sqlite3 data/uploads.db "SELECT doc_type, status FROM upload_history WHERE doc_number='SO001';"
```

#### 测试场景2: 转库单据上传

**前置条件**: 同上

**测试步骤**:
1. 访问: `http://localhost:10000/?business_id=123456&doc_number=ZK001&doc_type=转库`
2. 选择图片文件上传
3. 点击"上传文件"按钮

**预期结果**:
- ✅ 上传成功
- ✅ 用友云API调用参数: `businessType=yonbip-scm-stock`
- ✅ 数据库记录保存成功

**验证方法**:
```bash
sqlite3 data/uploads.db "SELECT doc_type, status FROM upload_history WHERE doc_number='ZK001';"
```

#### 测试场景3: 其他单据上传

**前置条件**: 同上

**测试步骤**:
1. 访问: `http://localhost:10000/?business_id=123456&doc_number=QT001&doc_type=其他`
2. 选择图片文件上传
3. 点击"上传文件"按钮

**预期结果**:
- ✅ 上传成功
- ✅ 用友云API调用参数: `businessType=yonbip-scm-stock`
- ✅ 数据库记录保存成功

**验证方法**:
```bash
sqlite3 data/uploads.db "SELECT doc_type, status FROM upload_history WHERE doc_number='QT001';"
```

### 业务逻辑验证

#### 验证项1: 映射正确性
- [ ] 销售单据使用 `yonbip-scm-scmsa`
- [ ] 转库单据使用 `yonbip-scm-stock`
- [ ] 其他单据使用 `yonbip-scm-stock`

#### 验证项2: 向后兼容性
- [ ] 现有代码不传 `business_type` 参数时使用默认值
- [ ] 配置文件的 `YONYOU_BUSINESS_TYPE` 仍然有效

#### 验证项3: 错误处理
- [ ] 非法 `doc_type` 返回400错误
- [ ] 用友云API错误正确返回并记录

### 调试方法

**查看API调用的URL参数**:

在 `yonyou_client.py` 的 `upload_file()` 方法中添加调试日志:
```python
# 构建请求URL（使用动态businessType）
url = f"{self.upload_url}?access_token={encoded_token}&businessType={effective_business_type}&businessId={business_id}"

# 调试日志
print(f"[DEBUG] 上传URL: businessType={effective_business_type}, businessId={business_id}")
```

**查看映射结果**:

在 `upload.py` 的 `upload_files()` 函数中添加:
```python
# 获取映射后的businessType
business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(doc_type, settings.YONYOU_BUSINESS_TYPE)

# 调试日志
print(f"[DEBUG] doc_type={doc_type} → businessType={business_type}")
```

---

## 实现清单总结

### 文件修改清单

| 文件路径 | 修改内容 | 修改行数 |
|---------|---------|---------|
| `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/yonyou_client.py` | 1. 添加 `business_type` 参数<br>2. 实现参数逻辑<br>3. 修改URL构建<br>4. 更新递归调用 | 77-117行 |
| `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/upload.py` | 1. 添加映射字典<br>2. 实现映射逻辑<br>3. 修改上传调用 | 95-160行 |
| `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/config.py` | **无修改** | - |

### 关键代码片段

#### 片段1: 参数化upload_file方法
```python
# app/core/yonyou_client.py
async def upload_file(
    self,
    file_content: bytes,
    file_name: str,
    business_id: str,
    retry_count: int = 0,
    business_type: Optional[str] = None  # 新增
) -> Dict[str, Any]:
    effective_business_type = business_type or self.business_type
    url = f"{self.upload_url}?...&businessType={effective_business_type}&..."
```

#### 片段2: 映射逻辑实现
```python
# app/api/upload.py
DOC_TYPE_TO_BUSINESS_TYPE = {
    "销售": "yonbip-scm-scmsa",
    "转库": "yonbip-scm-stock",
    "其他": "yonbip-scm-stock"
}
business_type = DOC_TYPE_TO_BUSINESS_TYPE.get(doc_type, settings.YONYOU_BUSINESS_TYPE)
```

#### 片段3: 参数传递
```python
# app/api/upload.py
result = await yonyou_client.upload_file(
    file_content,
    new_filename,
    business_id,
    retry_count=0,
    business_type=business_type  # 传递映射值
)
```

### 依赖关系

```
app/api/upload.py (API层)
    ↓ (调用)
app/core/yonyou_client.py (业务层)
    ↓ (使用)
app/core/config.py (配置层)
```

**数据流向**:
1. `doc_type` (用户输入) → API层验证
2. API层映射 → `business_type` (映射值)
3. `business_type` → YonYouClient方法参数
4. YonYouClient → 用友云API请求URL

---

## 技术约束

### 1. 向后兼容性
- ✅ `business_type` 参数为可选参数,默认值为 `None`
- ✅ 不传参数时使用 `self.business_type` (配置默认值)
- ✅ 现有调用代码无需修改

### 2. 扩展性
- ✅ 新增单据类型只需修改两处:
  1. `valid_doc_types` 列表
  2. `DOC_TYPE_TO_BUSINESS_TYPE` 字典
- ✅ 映射规则集中在API层,易于维护

### 3. 性能影响
- ✅ 字典查找: O(1) 时间复杂度
- ✅ 无额外网络请求
- ✅ 无数据库查询
- ✅ 对性能无影响

### 4. 安全性
- ✅ 复用现有的 `doc_type` 枚举验证
- ✅ 映射字典硬编码,无注入风险
- ✅ `businessType` 参数由映射生成,无用户直接输入

---

## 部署说明

### 部署步骤

#### 1. 代码更新
```bash
# 拉取代码（如果是Git管理）
git pull origin main

# 或直接修改文件
# - app/core/yonyou_client.py
# - app/api/upload.py
```

#### 2. 重启应用
```bash
# 本地运行
pkill -f "python run.py"
python run.py

# Docker部署
docker-compose restart
```

#### 3. 验证部署
```bash
# 健康检查
curl http://localhost:10000/api/health

# 测试上传
curl -X POST http://localhost:10000/api/upload \
  -F "business_id=123456" \
  -F "doc_number=TEST001" \
  -F "doc_type=转库" \
  -F "files=@test.jpg"
```

### 回滚方案

**如果出现问题,可快速回滚**:

1. 恢复 `yonyou_client.py`:
```python
# 移除 business_type 参数
async def upload_file(
    self,
    file_content: bytes,
    file_name: str,
    business_id: str,
    retry_count: int = 0
) -> Dict[str, Any]:
    # 使用固定的 self.business_type
    url = f"{self.upload_url}?...&businessType={self.business_type}&..."
```

2. 恢复 `upload.py`:
```python
# 移除映射逻辑和参数传递
result = await yonyou_client.upload_file(
    file_content,
    new_filename,
    business_id
)
```

3. 重启应用

---

## 附录

### A. 映射表

| doc_type | businessType | 说明 |
|----------|--------------|------|
| 销售 | yonbip-scm-scmsa | 原有默认值,保持不变 |
| 转库 | yonbip-scm-stock | 新增映射 |
| 其他 | yonbip-scm-stock | 新增映射 |

### B. 配置说明

**环境变量**: 无需新增环境变量

**配置项**:
- `YONYOU_BUSINESS_TYPE`: 保留作为默认值和"销售"类型的值

### C. API文档更新

**Swagger文档**: 无需更新（参数未变化）

**内部文档**: 更新说明 `doc_type` 会影响 `businessType` 的映射

### D. 相关文件索引

**核心文件**:
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/yonyou_client.py` - YonYouClient类
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/api/upload.py` - 上传API
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/config.py` - 配置管理

**相关文件**:
- `/Users/lichuansong/Desktop/projects/单据上传管理/.env` - 环境变量配置
- `/Users/lichuansong/Desktop/projects/单据上传管理/app/core/database.py` - 数据库操作

---

## 总结

### 实现要点
1. ✅ 参数化设计: `upload_file()` 支持动态 `business_type`
2. ✅ 映射逻辑: 字典映射 doc_type → businessType
3. ✅ 向后兼容: 可选参数,默认值保留
4. ✅ 扩展友好: 新增类型只需修改映射字典

### 技术亮点
- **最小化改动**: 仅修改2个文件,共约30行代码
- **零影响部署**: 无数据库变更,无配置变更
- **类型安全**: 保持Python类型提示
- **易于维护**: 映射逻辑集中,清晰明了

### 质量保证
- ✅ 代码遵循现有架构模式
- ✅ 保持异步处理能力
- ✅ 错误处理复用现有逻辑
- ✅ 向后兼容性完全保证

---

**文档版本**: 1.0.0
**生成时间**: 2025-10-17
**实现状态**: 待实施
**预计工时**: 30分钟（含测试）

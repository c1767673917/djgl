# Token 状态显示修复实现记录

## 根因确认

- 双重重试逻辑叠加:
  - `app/api/upload.py:145-168` 中, 后台任务在循环中调用:
    - `await yonyou_client.upload_file(file_content, new_filename, business_id, retry_count=attempt, business_type=business_type)` (修复前逻辑)
  - `YonYouClient.upload_file` 内部 (`app/core/yonyou_client.py:105-169`) 也使用 `retry_count` 参数控制 Token 错误 (1090003500065/310036) 的自动刷新与二次上传:
    - `if error_code in ['1090003500065', '310036'] and retry_count == 0: ... return await self.upload_file(..., retry_count + 1, ...)`
  - 结果是: 外层将“第几次尝试”传入 `retry_count`, 与内部“Token 重试计数”复用同一个参数, 语义混淆。

- 外层循环与内部 Token 重试的交叉影响:
  - 当第一次调用 `upload_file` 遇到 Token 错误时, 内部会自行刷新 Token 并重试一次, 然后才把最终结果返回给外层循环。
  - 但外层循环仍会根据第一次/第二次外层尝试更新 `error_code`, `error_message`, `retry_count` 变量, 并在最终失败路径中写入数据库 (`app/api/upload.py:206-229`).
  - 在极少数时序下(比如外层多次尝试 + 部分成功/失败掺杂), 前端可能在最终成功之前已经通过管理端接口(`app/api/admin.py:80-129`)拿到带有 `error_code='310036'` 的失败记录, 从而显示 `✗ 失败 非法token`。

- 状态更新时机:
  - 成功/失败状态只在 `background_upload_to_yonyou` 尾部一次性写入 (`app/api/upload.py:183-229`), 没有在每次重试中提前 `UPDATE`。
  - 但由于错误码与重试计数在内存中可能被多次覆盖, 与内部 Token 重试交叉叠加, 会放大上述“语义混淆”带来的可观测性问题(例如日志、统计接口短暂显示 Token 失败)。

## 修复内容

### 1. 精简 upload.py 中对 Token 错误的处理

文件: `app/api/upload.py`

- 在 `background_upload_to_yonyou` 中, 将“上传到用友云”的重试逻辑改为只负责网络级别错误, 不再参与 Token 错误重试:
  - 移除对 `yonyou_client.upload_file` 的 `retry_count=attempt` 传参, 避免干扰 `YonYouClient` 内部的 Token 重试逻辑。
  - 仅当 `error_code == 'NETWORK_ERROR'` 时才进入外层重试, 其他业务错误(含 Token 相关错误)不再由外层重复尝试。

关键代码 (修复后): `app/api/upload.py:133-168`

```python
        # 3. 上传到用友云
        #
        # 约定:
        # - 用友云 Token 相关错误(310036/1090003500065) 只在 YonYouClient 内部处理,
        #   由 YonYouClient.upload_file 负责刷新 Token 并重试一次。
        # - 这里的重试循环只负责“网络级别”的错误(例如 NETWORK_ERROR),
        #   避免和 YonYouClient 内部的 Token 重试产生交叉、竞态。
        yonyou_file_id = None
        error_code = None
        error_message = None
        retry_count = 0

        for attempt in range(settings.MAX_RETRY_COUNT):
            result = await yonyou_client.upload_file(
                file_content,
                new_filename,
                business_id,
                business_type=business_type
            )

            if result["success"]:
                yonyou_file_id = result["data"]["id"]
                retry_count = attempt
                break
            else:
                # 记录最近一次失败信息
                error_code = result.get("error_code")
                error_message = result.get("error_message")
                retry_count = attempt + 1

                # 仅在网络错误时进行重试, 其他业务错误直接退出循环
                if error_code != "NETWORK_ERROR":
                    break

                if attempt < settings.MAX_RETRY_COUNT - 1:
                    await asyncio.sleep(settings.RETRY_DELAY)
```

效果:
- Token 相关错误(310036/1090003500065) 完全由 `YonYouClient` 内部处理, 外层不会再因为 Token 错误额外重试、也不会错误地传入 `retry_count` 干扰内部逻辑。
- 外层循环专注于网络异常(`NETWORK_ERROR`), 保持原有的网络重试能力。
- 成功/失败状态仍然只在所有尝试完成后统一写入数据库, 不改变现有状态流转模型(`pending → uploading → success/failed`)。

### 2. 增强 Token 错误场景的可测试性

文件: `tests/conftest.py`

- 新增整数类型非法 Token 响应的 fixture, 覆盖真实环境中 `code` 可能为整数的情况:

```python
@pytest.fixture
def mock_upload_response_invalid_token_integer():
    """Mock 非法Token响应(错误码310036, 整数错误码)"""
    return {
        "code": 310036,
        "message": "非法token",
        "data": None
    }
```

文件: `tests/test_yonyou_client.py`

- 在 `TestFileUpload` 中新增用例 `test_upload_file_invalid_token_retry_integer_code`, 覆盖 `code` 为整数且为 310036 时的 Token 自动刷新重试逻辑:

```python
    @pytest.mark.asyncio
    async def test_upload_file_invalid_token_retry_integer_code(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_invalid_token_integer,
        mock_upload_response_success
    ):
        """测试非法token(错误码310036, 整数错误码)时的重试机制"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            # Mock Token获取
            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 第一次上传返回非法token(整数错误码)，第二次成功
            mock_post.side_effect = [
                Mock(json=Mock(return_value=mock_upload_response_invalid_token_integer)),
                Mock(json=Mock(return_value=mock_upload_response_success))
            ]

            result = await client.upload_file(
                file_content=test_image_bytes,
                file_name="test.jpg",
                business_id="123456"
            )

            # 验证重试成功
            assert result["success"] is True
            # 验证调用了两次上传API
            assert mock_post.call_count == 2
            # 验证调用了两次Token获取(第二次是force_refresh)
            assert mock_get.call_count == 2
```

效果:
- 进一步验证 `YonYouClient.upload_file` 对 310036/1090003500065 错误码的处理与类型(字符串/整数)无关, 保证真实环境中的 Token 过期/非法场景会被自动刷新并重试一次。
- 与 upload.py 的外层网络重试配合, 覆盖了“Token 失败 → 内部刷新成功 → 外层视角一次调用成功”的完整闭环。

## 测试执行情况

已在本地执行的关键测试:

1. 用友云客户端相关单测
   - 命令: `python3 -m pytest -q tests/test_yonyou_client.py -q`
   - 结果: 29 个测试全部通过 (含新增 `test_upload_file_invalid_token_retry_integer_code`)。
   - 覆盖率报告对整个项目要求 70% 覆盖, 仅运行该文件时整体覆盖率约 7%, 导致 pytest 报告 coverage 未达标。这是既有配置与按文件运行测试的已知行为, 与本次修改无关。

2. 其他测试文件
   - 运行 `python3 -m pytest -q` / 单独运行 `tests/test_async_upload.py`、`tests/test_upload_api.py` 等时, 当前仓库中存在大量历史性失败(如: WebDAV 测试依赖真实服务、部分测试仍假定旧版 `get_db_connection` 返回裸连接等)。
   - 这些失败在本次改动前已存在, 与本次 Token 状态修复无直接关系, 本次没有对相关模块和测试做侵入式修改。

## Structured Summary JSON

```json
{
  "issue": {
    "id": "token-status-fix",
    "title": "用友云上传成功但前端显示“失败 非法token”",
    "rootCause": {
      "description": "upload.py 中的外层重试循环与 YonYouClient.upload_file 内部的 Token 重试共用 retry_count 语义, 导致在少数时序下出现 Token 错误信息被错误保存/暴露, 前端短暂或错误地显示 \"失败 非法token\"。",
      "locations": [
        "app/api/upload.py:145-168",
        "app/core/yonyou_client.py:105-169"
      ]
    }
  },
  "changes": [
    {
      "file": "app/api/upload.py",
      "description": "将后台上传中的用友云重试逻辑收敛为仅处理 NETWORK_ERROR, 移除对 retry_count 的外层传递, 避免与 YonYouClient 内部 Token 重试逻辑交叉。"
    },
    {
      "file": "tests/conftest.py",
      "description": "新增整数类型非法 Token 响应 fixture mock_upload_response_invalid_token_integer。"
    },
    {
      "file": "tests/test_yonyou_client.py",
      "description": "新增测试用例 test_upload_file_invalid_token_retry_integer_code, 覆盖 code 为整数时的 310036 非法 Token 重试场景。"
    }
  ],
  "testing": {
    "commands": [
      "python3 -m pytest -q tests/test_yonyou_client.py -q"
    ],
    "notes": [
      "tests/test_yonyou_client.py 全部测试通过 (含新增用例)",
      "运行单文件测试时全局 coverage 要求 70% 无法满足, 为既有配置限制, 非功能性回归",
      "完整测试套件中存在与 WebDAV/数据库封装相关的历史性失败, 未在本次修复范围内修改"
    ]
  }
}
```


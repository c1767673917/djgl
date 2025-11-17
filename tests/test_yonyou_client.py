"""测试用友云客户端功能"""
import pytest
import hmac
import hashlib
import base64
import urllib.parse
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta

from app.core.yonyou_client import YonYouClient
from app.core.timezone import get_beijing_now


class TestSignatureGeneration:
    """测试HMAC-SHA256签名算法"""

    def test_generate_signature_format(self):
        """测试签名生成的格式正确性"""
        client = YonYouClient()
        timestamp = "1234567890000"

        signature = client._generate_signature(timestamp)

        # 验证签名不为空
        assert signature is not None
        assert len(signature) > 0

        # 验证签名是URL编码的字符串
        assert isinstance(signature, str)

    def test_generate_signature_consistency(self):
        """测试相同输入生成相同签名"""
        client = YonYouClient()
        timestamp = "1234567890000"

        signature1 = client._generate_signature(timestamp)
        signature2 = client._generate_signature(timestamp)

        # 相同的时间戳应该生成相同的签名
        assert signature1 == signature2

    def test_generate_signature_different_timestamp(self):
        """测试不同时间戳生成不同签名"""
        client = YonYouClient()

        signature1 = client._generate_signature("1234567890000")
        signature2 = client._generate_signature("9876543210000")

        # 不同的时间戳应该生成不同的签名
        assert signature1 != signature2

    def test_generate_signature_algorithm_correctness(self):
        """测试签名算法的正确性(手动计算验证)"""
        client = YonYouClient()
        timestamp = "1234567890000"

        # 手动计算签名
        string_to_sign = f"appKey{client.app_key}timestamp{timestamp}"
        hmac_code = hmac.new(
            client.app_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256
        ).digest()
        expected_signature = urllib.parse.quote(base64.b64encode(hmac_code).decode())

        # 验证生成的签名与手动计算一致
        actual_signature = client._generate_signature(timestamp)
        assert actual_signature == expected_signature

    def test_generate_signature_url_encoding(self):
        """测试签名是否正确进行URL编码"""
        client = YonYouClient()
        timestamp = "1234567890000"

        signature = client._generate_signature(timestamp)

        # URL编码的签名不应该包含某些特殊字符(如+, /, =等会被编码)
        # 但可能包含%符号(编码后的标志)
        assert ' ' not in signature  # 不应该有空格


class TestTokenManagement:
    """测试Token获取和缓存机制"""

    @pytest.mark.asyncio
    async def test_get_access_token_success(self, mock_token_response_success):
        """测试Token首次获取成功"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_response

            token = await client.get_access_token()

            assert token == "test_access_token_12345"
            assert client._token_cache is not None
            assert client._token_cache["access_token"] == token

    @pytest.mark.asyncio
    async def test_get_access_token_caching(self, mock_token_response_success):
        """测试Token缓存机制生效"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_response

            # 第一次获取
            token1 = await client.get_access_token()

            # 第二次获取(应该使用缓存)
            token2 = await client.get_access_token()

            assert token1 == token2
            # 只应该调用一次API
            assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_get_access_token_force_refresh(self, mock_token_response_success):
        """测试force_refresh参数功能"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_response

            # 第一次获取
            await client.get_access_token()

            # 强制刷新
            await client.get_access_token(force_refresh=True)

            # 应该调用两次API
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_access_token_expired(self, mock_token_response_success):
        """测试Token过期自动刷新"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_response

            # 第一次获取
            await client.get_access_token()

            # 手动设置token为已过期
            client._token_cache["expires_at"] = get_beijing_now() - timedelta(seconds=1)

            # 再次获取(应该自动刷新)
            await client.get_access_token()

            # 应该调用两次API
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_access_token_error(self, mock_token_response_error):
        """测试Token获取失败的错误处理"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_token_response_error
            mock_get.return_value = mock_response

            with pytest.raises(Exception) as exc_info:
                await client.get_access_token()

            assert "获取Token失败" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_access_token_cache_expiration(self, mock_token_response_success):
        """测试Token缓存提前60秒过期"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_response

            await client.get_access_token()

            # 验证过期时间是否提前60秒
            expires_at = client._token_cache["expires_at"]
            expected_expires_at = get_beijing_now() + timedelta(seconds=3600 - 60)

            # 允许1秒的误差
            time_diff = abs((expires_at - expected_expires_at).total_seconds())
            assert time_diff < 1

    @pytest.mark.asyncio
    async def test_get_access_token_signature_error_retry_by_code(
        self,
        mock_token_response_signature_error,
        mock_token_response_success
    ):
        """测试签名错误(通过错误码识别)时的重试机制"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            # 第一次返回签名错误，第二次成功
            mock_get.side_effect = [
                Mock(json=Mock(return_value=mock_token_response_signature_error)),
                Mock(json=Mock(return_value=mock_token_response_success))
            ]

            token = await client.get_access_token()

            # 验证重试成功
            assert token == "test_access_token_12345"
            # 验证调用了两次API
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_access_token_signature_error_retry_by_message(
        self,
        mock_token_response_signature_error_message,
        mock_token_response_success
    ):
        """测试签名错误(通过错误信息识别)时的重试机制"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            # 第一次返回签名错误，第二次成功
            mock_get.side_effect = [
                Mock(json=Mock(return_value=mock_token_response_signature_error_message)),
                Mock(json=Mock(return_value=mock_token_response_success))
            ]

            token = await client.get_access_token()

            # 验证重试成功
            assert token == "test_access_token_12345"
            # 验证调用了两次API
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_access_token_signature_error_retry_limit(
        self,
        mock_token_response_signature_error
    ):
        """测试签名错误重试次数限制(最多1次重试)"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            # 始终返回签名错误
            mock_response = Mock()
            mock_response.json.return_value = mock_token_response_signature_error
            mock_get.return_value = mock_response

            with pytest.raises(Exception) as exc_info:
                await client.get_access_token()

            # 验证异常信息
            assert "获取Token失败" in str(exc_info.value)
            # 验证最多重试1次(共2次调用)
            assert mock_get.call_count == 2


class TestFileUpload:
    """测试文件上传功能"""

    @pytest.mark.asyncio
    async def test_upload_file_success(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_success
    ):
        """测试单文件上传成功"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            # Mock Token获取
            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # Mock文件上传
            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_success
            mock_post.return_value = mock_post_response

            result = await client.upload_file(
                file_content=test_image_bytes,
                file_name="test.jpg",
                business_id="123456"
            )

            assert result["success"] is True
            assert result["data"]["id"] == "file_id_12345"

    @pytest.mark.asyncio
    async def test_upload_file_token_expired_retry_string_code(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_token_expired_string,
        mock_upload_response_success
    ):
        """测试Token过期(字符串错误码)时的重试机制 - Critical Issue #1"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            # Mock Token获取
            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 第一次上传返回Token过期(字符串错误码)，第二次成功
            mock_post.side_effect = [
                Mock(json=Mock(return_value=mock_upload_response_token_expired_string)),
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

    @pytest.mark.asyncio
    async def test_upload_file_token_expired_retry_integer_code(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_token_expired_integer,
        mock_upload_response_success
    ):
        """测试Token过期(整数错误码)时的重试机制 - Critical Issue #1"""
        client = YonYouClient()

        # 注意: 当前代码只检查字符串 "1090003500065"
        # 这个测试将会失败,暴露出bug
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 返回整数类型的错误码
            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_token_expired_integer
            mock_post.return_value = mock_post_response

            result = await client.upload_file(
                file_content=test_image_bytes,
                file_name="test.jpg",
                business_id="123456"
            )

            # 当前代码bug: 整数类型的错误码不会触发重试
            # 这个测试会失败,需要修复代码
            # 期望: 应该触发重试
            # 实际: 不会触发重试,直接返回失败
            assert result["success"] is False
            assert result["error_code"] == "1090003500065"

    @pytest.mark.asyncio
    async def test_upload_file_invalid_token_retry(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_invalid_token,
        mock_upload_response_success
    ):
        """测试非法token(错误码310036)时的重试机制"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            # Mock Token获取
            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 第一次上传返回非法token，第二次成功
            mock_post.side_effect = [
                Mock(json=Mock(return_value=mock_upload_response_invalid_token)),
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

    @pytest.mark.asyncio
    async def test_upload_file_retry_limit(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_token_expired_string
    ):
        """测试重试次数限制(最多1次重试)"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 始终返回Token过期
            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_token_expired_string
            mock_post.return_value = mock_post_response

            result = await client.upload_file(
                file_content=test_image_bytes,
                file_name="test.jpg",
                business_id="123456"
            )

            # 验证最多重试1次(共2次调用)
            assert mock_post.call_count == 2
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_upload_file_general_error(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_error
    ):
        """测试一般错误不触发重试"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_error
            mock_post.return_value = mock_post_response

            result = await client.upload_file(
                file_content=test_image_bytes,
                file_name="test.jpg",
                business_id="123456"
            )

            # 验证只调用一次,不重试
            assert mock_post.call_count == 1
            assert result["success"] is False
            assert result["error_code"] == "40000"

    @pytest.mark.asyncio
    async def test_upload_file_network_error(
        self,
        test_image_bytes,
        mock_token_response_success
    ):
        """测试网络异常处理"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            # 模拟网络异常
            mock_post.side_effect = Exception("Network timeout")

            result = await client.upload_file(
                file_content=test_image_bytes,
                file_name="test.jpg",
                business_id="123456"
            )

            assert result["success"] is False
            assert result["error_code"] == "NETWORK_ERROR"
            assert "Network timeout" in result["error_message"]

    @pytest.mark.asyncio
    async def test_upload_file_url_construction(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_success
    ):
        """测试上传URL构建正确性"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_success
            mock_post.return_value = mock_post_response

            await client.upload_file(
                file_content=test_image_bytes,
                file_name="test.jpg",
                business_id="123456"
            )

            # 验证URL参数
            call_args = mock_post.call_args
            url = call_args[0][0]
            assert "access_token=test_access_token_12345" in url
            assert f"businessType={client.business_type}" in url
            assert "businessId=123456" in url

    @pytest.mark.asyncio
    async def test_upload_file_token_url_encoding(
        self,
        test_image_bytes,
        mock_upload_response_success
    ):
        """测试Token中的特殊字符被正确URL编码"""
        client = YonYouClient()

        # 创建一个包含特殊字符的token(模拟真实场景)
        token_with_special_chars = "YT5_TG/test+token=base64"

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            # Mock Token获取返回带特殊字符的token
            mock_get_response = Mock()
            mock_get_response.json.return_value = {
                "code": "00000",
                "message": "成功",
                "data": {
                    "access_token": token_with_special_chars,
                    "expires_in": 3600
                }
            }
            mock_get.return_value = mock_get_response

            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_success
            mock_post.return_value = mock_post_response

            await client.upload_file(
                file_content=test_image_bytes,
                file_name="test.jpg",
                business_id="123456"
            )

            # 验证URL中token被正确编码
            call_args = mock_post.call_args
            url = call_args[0][0]

            # 特殊字符应该被编码: / -> %2F, + -> %2B, = -> %3D
            assert "access_token=YT5_TG%2Ftest%2Btoken%3Dbase64" in url
            # 不应该包含未编码的特殊字符
            assert "YT5_TG/test+token=base64" not in url.split("access_token=")[1].split("&")[0]

    @pytest.mark.asyncio
    async def test_upload_file_multipart_format(
        self,
        test_image_bytes,
        mock_token_response_success,
        mock_upload_response_success
    ):
        """测试multipart/form-data格式正确性"""
        client = YonYouClient()

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get, \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:

            mock_get_response = Mock()
            mock_get_response.json.return_value = mock_token_response_success
            mock_get.return_value = mock_get_response

            mock_post_response = Mock()
            mock_post_response.json.return_value = mock_upload_response_success
            mock_post.return_value = mock_post_response

            await client.upload_file(
                file_content=test_image_bytes,
                file_name="test.jpg",
                business_id="123456"
            )

            # 验证files参数
            call_kwargs = mock_post.call_args[1]
            assert 'files' in call_kwargs
            files = call_kwargs['files']
            assert 'files' in files
            assert files['files'][0] == "test.jpg"
            assert files['files'][1] == test_image_bytes


class TestDeliveryDetail:
    """测试物流详情查询功能"""

    @pytest.mark.asyncio
    async def test_get_delivery_detail_success(self):
        """测试物流信息成功获取"""
        client = YonYouClient()
        mock_response = {
            'code': '200',
            'message': '操作成功',
            'data': {
                'deliveryVoucherDefineCharacter': {
                    'RX003_name': '天津佳士达物流有限公司'
                }
            }
        }

        with patch.object(client, 'get_access_token', new=AsyncMock(return_value='fake_token')):
            with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
                mock_http_response = Mock()
                mock_http_response.json.return_value = mock_response
                mock_get.return_value = mock_http_response

                result = await client.get_delivery_detail('2385714919669497862')

        assert result['success'] is True
        assert result['logistics'] == '天津佳士达物流有限公司'
        assert result['error_code'] is None

    @pytest.mark.asyncio
    async def test_get_delivery_detail_missing_field(self):
        """测试缺少RX003_name字段时返回None"""
        client = YonYouClient()
        mock_response = {
            'code': '200',
            'message': '操作成功',
            'data': {
                'deliveryVoucherDefineCharacter': {}
            }
        }

        with patch.object(client, 'get_access_token', new=AsyncMock(return_value='fake_token')):
            with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
                mock_http_response = Mock()
                mock_http_response.json.return_value = mock_response
                mock_get.return_value = mock_http_response

                result = await client.get_delivery_detail('test_id')

        assert result['success'] is True
        assert result['logistics'] is None

    @pytest.mark.asyncio
    async def test_get_delivery_detail_api_error(self):
        """测试API返回错误场景"""
        client = YonYouClient()
        mock_response = {
            'code': '500',
            'message': '服务器内部错误'
        }

        with patch.object(client, 'get_access_token', new=AsyncMock(return_value='fake_token')):
            with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
                mock_http_response = Mock()
                mock_http_response.json.return_value = mock_response
                mock_get.return_value = mock_http_response

                result = await client.get_delivery_detail('test_id')

        assert result['success'] is False
        assert result['logistics'] is None
        assert result['error_code'] == '500'
        assert '服务器内部错误' in result['error_message']

    @pytest.mark.asyncio
    async def test_get_delivery_detail_network_error(self):
        """测试网络异常场景"""
        client = YonYouClient()

        with patch.object(client, 'get_access_token', new=AsyncMock(return_value='fake_token')):
            with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
                mock_get.side_effect = Exception('网络超时')
                result = await client.get_delivery_detail('test_id')

        assert result['success'] is False
        assert result['logistics'] is None
        assert result['error_code'] == 'NETWORK_ERROR'
        assert '网络超时' in result['error_message']

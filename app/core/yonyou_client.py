import hmac
import hashlib
import base64
import time
import urllib.parse
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import httpx
from app.core.config import get_settings
from app.core.timezone import get_beijing_now

settings = get_settings()


class YonYouClient:
    def __init__(self):
        self.app_key = settings.YONYOU_APP_KEY
        self.app_secret = settings.YONYOU_APP_SECRET
        self.auth_url = settings.YONYOU_AUTH_URL
        self.upload_url = settings.YONYOU_UPLOAD_URL
        self.business_type = settings.YONYOU_BUSINESS_TYPE
        self._token_cache: Optional[Dict[str, Any]] = None

    def _generate_signature(self, timestamp: str) -> str:
        """生成HMAC-SHA256签名"""
        # 构建待签名字符串: appKey{appKey}timestamp{timestamp}
        string_to_sign = f"appKey{self.app_key}timestamp{timestamp}"

        # 使用HMAC-SHA256计算签名
        hmac_code = hmac.new(
            self.app_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256
        ).digest()

        # Base64编码并URL编码
        signature = urllib.parse.quote(base64.b64encode(hmac_code).decode())

        return signature

    async def get_access_token(self, force_refresh: bool = False, retry_count: int = 0) -> str:
        """获取access_token，支持缓存和签名错误重试

        Args:
            force_refresh: 是否强制刷新token
            retry_count: 重试次数（内部使用）

        Returns:
            access_token字符串
        """
        # 检查缓存
        if not force_refresh and self._token_cache:
            if get_beijing_now() < self._token_cache["expires_at"]:
                return self._token_cache["access_token"]

        # 生成时间戳(毫秒)
        timestamp = str(int(time.time() * 1000))

        # 生成签名
        signature = self._generate_signature(timestamp)

        # 构建请求URL
        url = f"{self.auth_url}?appKey={self.app_key}&timestamp={timestamp}&signature={signature}"

        # 发送请求
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
            response = await client.get(url)
            result = response.json()

        # 检查响应
        if result.get("code") == "00000":
            access_token = result["data"]["access_token"]
            expires_in = result["data"].get("expires_in", 3600)  # 默认1小时

            # 缓存token
            self._token_cache = {
                "access_token": access_token,
                "expires_at": get_beijing_now() + timedelta(seconds=expires_in - 60)  # 提前60秒过期
            }

            return access_token
        else:
            # 处理签名相关错误，自动重试一次
            # 签名错误可能的错误码：50000(认证失败)、其他签名相关错误
            # 错误信息可能包含：签名不正确、signature invalid 等
            error_code = str(result.get("code", ""))
            error_message = str(result.get("message", "")).lower()

            # 判断是否为签名相关错误
            is_signature_error = (
                error_code == "50000" or
                "签名" in error_message or
                "signature" in error_message
            )

            # 如果是签名错误且未重试过，则重新生成时间戳和签名后重试
            if is_signature_error and retry_count == 0:
                # 等待一小段时间后重试（避免时间戳相同）
                await asyncio.sleep(0.1)
                return await self.get_access_token(force_refresh=True, retry_count=retry_count + 1)

            raise Exception(f"获取Token失败: {result.get('message', '未知错误')}")

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

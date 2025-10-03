import hmac
import hashlib
import base64
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import httpx
from app.core.config import get_settings

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

    async def get_access_token(self, force_refresh: bool = False) -> str:
        """获取access_token，支持缓存"""
        # 检查缓存
        if not force_refresh and self._token_cache:
            if datetime.now() < self._token_cache["expires_at"]:
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
                "expires_at": datetime.now() + timedelta(seconds=expires_in - 60)  # 提前60秒过期
            }

            return access_token
        else:
            raise Exception(f"获取Token失败: {result.get('message', '未知错误')}")

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
                    return await self.upload_file(file_content, file_name, business_id, retry_count + 1)

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

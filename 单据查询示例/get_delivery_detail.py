#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
销售发货详情查询脚本
用于从用友云API获取销售发货单的详细信息原始JSON数据
"""

import requests
import base64
import hmac
import hashlib
import time
import urllib.parse
import json
from typing import Dict, Optional


class YonYouAPIClient:
    """用友云API客户端"""

    def __init__(self, app_key: str, app_secret: str):
        """
        初始化API客户端

        Args:
            app_key: 应用密钥
            app_secret: 应用秘钥
        """
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = "https://c4.yonyoucloud.com"
        self.access_token = None

    def get_access_token(self) -> str:
        """
        获取访问令牌 - 使用HMAC-SHA256签名算法

        Returns:
            访问令牌字符串

        Raises:
            Exception: 当获取token失败时
        """
        # 获取当前时间戳（毫秒）
        timestamp = str(int(time.time() * 1000))

        # 构建待签名字符串
        string_to_sign = f'appKey{self.app_key}timestamp{timestamp}'

        # 使用HMAC-SHA256算法计算签名
        hmac_code = hmac.new(
            self.app_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256
        ).digest()

        # Base64编码并URL编码
        signature = urllib.parse.quote(base64.b64encode(hmac_code).decode())

        # 构建请求URL
        url = (f'{self.base_url}/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken'
               f'?appKey={self.app_key}&timestamp={timestamp}&signature={signature}')

        # 发送请求
        response = requests.get(url)
        result = response.json()

        # 检查响应
        if result.get('code') == '00000':
            self.access_token = result['data']['access_token']
            print(f"✓ 成功获取access_token: {self.access_token[:20]}...")
            return self.access_token
        else:
            raise Exception(f"获取token失败: {result.get('message', '未知错误')}")

    def get_delivery_detail(self, delivery_id: str) -> Dict:
        """
        查询销售发货单详细信息

        Args:
            delivery_id: 发货单业务数据ID

        Returns:
            包含详细信息的字典

        Raises:
            Exception: 当查询失败时
        """
        # 确保有访问令牌
        if not self.access_token:
            self.get_access_token()

        # 构建请求URL
        url = f'{self.base_url}/iuap-api-gateway/yonbip/sd/voucherdelivery/detail'

        # 请求参数
        params = {
            'access_token': self.access_token,
            'id': delivery_id
        }

        # 发送GET请求
        response = requests.get(url, params=params)
        result = response.json()

        # 检查响应
        if result.get('code') == '200':
            print(f"✓ 成功获取发货单 {delivery_id} 的详细信息")
            return result
        else:
            raise Exception(f"查询发货单失败: {result.get('message', '未知错误')}")


def save_json_to_file(data: Dict, filename: str = 'delivery_detail.json'):
    """
    将JSON数据保存到文件

    Args:
        data: 要保存的数据字典
        filename: 文件名
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✓ 数据已保存到文件: {filename}")


def main():
    """主函数"""
    # API配置 - 从api_doc.txt获取
    APP_KEY = "ab2bbb774d284bbca947e8c9938332bf"
    APP_SECRET = "d6ef04c33f3f6eaca7076439f6dc955474f3aa8f"

    # 要查询的发货单ID（示例ID，请根据实际情况修改）
    DELIVERY_ID = "2385714919669497862"  # 修改为实际的发货单ID

    print("=" * 60)
    print("销售发货详情查询脚本")
    print("=" * 60)

    try:
        # 创建API客户端
        client = YonYouAPIClient(APP_KEY, APP_SECRET)

        # 获取访问令牌
        print("\n[1/3] 正在获取访问令牌...")
        client.get_access_token()

        # 查询发货单详情
        print(f"\n[2/3] 正在查询发货单详情 (ID: {DELIVERY_ID})...")
        delivery_data = client.get_delivery_detail(DELIVERY_ID)

        # 保存原始JSON到文件
        print("\n[3/3] 正在保存数据...")
        save_json_to_file(delivery_data, f'delivery_detail_{DELIVERY_ID}.json')

        # 打印部分关键信息
        print("\n" + "=" * 60)
        print("查询结果摘要:")
        print("=" * 60)
        if delivery_data.get('data'):
            data = delivery_data['data']
            print(f"发货单编号: {data.get('code', 'N/A')}")
            print(f"单据日期: {data.get('vouchdate', 'N/A')}")
            print(f"客户名称: {data.get('agentId_name', 'N/A')}")
            print(f"库存组织: {data.get('stockOrgName', 'N/A')}")
            print(f"审批状态: {data.get('verifystate', 'N/A')}")
            print(f"发货状态: {data.get('statusCode', 'N/A')}")
            print(f"应收金额: {data.get('realMoney', 'N/A')}")
            print(f"含税金额: {data.get('payMoney', 'N/A')}")

            # 发货明细数量
            details = data.get('deliverydetails', [])
            print(f"\n发货明细行数: {len(details)}")

        print("\n✓ 所有操作完成!")

    except Exception as e:
        print(f"\n✗ 错误: {str(e)}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())

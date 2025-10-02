#!/bin/bash
# 测试运行脚本

echo "======================================"
echo "单据上传管理系统 - 测试套件"
echo "======================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Python版本
echo "检查Python环境..."
python3 --version

# 检查依赖
echo ""
echo "检查测试依赖..."
python3 -m pip list | grep -E "pytest|httpx|fastapi" > /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 测试依赖已安装${NC}"
else
    echo -e "${YELLOW}⚠ 安装测试依赖...${NC}"
    python3 -m pip install -r requirements.txt -q
fi

echo ""
echo "======================================"
echo "运行测试选项:"
echo "======================================"
echo "1. 运行所有测试"
echo "2. 运行核心测试(P0优先级)"
echo "3. 运行Critical Issue #1测试"
echo "4. 运行API测试"
echo "5. 生成覆盖率报告"
echo "6. 快速测试(仅核心功能)"
echo ""

# 如果有参数,直接运行
if [ ! -z "$1" ]; then
    CHOICE=$1
else
    read -p "请选择 (1-6): " CHOICE
fi

case $CHOICE in
    1)
        echo ""
        echo -e "${YELLOW}运行所有测试...${NC}"
        python3 -m pytest tests/ -v --tb=short --no-cov
        ;;
    2)
        echo ""
        echo -e "${YELLOW}运行核心测试(P0)...${NC}"
        python3 -m pytest tests/test_yonyou_client.py -v --no-cov
        ;;
    3)
        echo ""
        echo -e "${YELLOW}运行Critical Issue #1测试...${NC}"
        python3 -m pytest \
            tests/test_yonyou_client.py::TestFileUpload::test_upload_file_token_expired_retry_string_code \
            tests/test_yonyou_client.py::TestFileUpload::test_upload_file_token_expired_retry_integer_code \
            -v --no-cov
        ;;
    4)
        echo ""
        echo -e "${YELLOW}运行API测试...${NC}"
        python3 -m pytest tests/test_upload_api.py -v --tb=short --no-cov
        ;;
    5)
        echo ""
        echo -e "${YELLOW}生成覆盖率报告...${NC}"
        python3 -m pytest tests/test_yonyou_client.py \
            --cov=app/core/yonyou_client \
            --cov-report=html \
            --cov-report=term-missing

        if [ -d "htmlcov" ]; then
            echo ""
            echo -e "${GREEN}✓ 覆盖率报告已生成: htmlcov/index.html${NC}"
            echo -e "${YELLOW}提示: 运行 'open htmlcov/index.html' 查看报告${NC}"
        fi
        ;;
    6)
        echo ""
        echo -e "${YELLOW}快速测试(仅核心功能)...${NC}"
        python3 -m pytest \
            tests/test_yonyou_client.py::TestSignatureGeneration \
            tests/test_yonyou_client.py::TestTokenManagement \
            tests/test_yonyou_client.py::TestFileUpload::test_upload_file_success \
            tests/test_yonyou_client.py::TestFileUpload::test_upload_file_token_expired_retry_string_code \
            -v --no-cov
        ;;
    *)
        echo -e "${RED}无效选择${NC}"
        exit 1
        ;;
esac

# 检查测试结果
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}======================================"
    echo "✓ 测试完成"
    echo "======================================${NC}"
else
    echo ""
    echo -e "${RED}======================================"
    echo "✗ 测试失败"
    echo "======================================${NC}"
    exit 1
fi

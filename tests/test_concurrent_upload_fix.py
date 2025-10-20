"""测试并发上传场景下的文件名唯一性修复

此测试专门验证针对issue "对同一单据ID同时上传时图片名称相同" 的修复效果
"""
import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch, Mock
from fastapi.testclient import TestClient

from app.main import app
from app.api.upload import generate_unique_filename


class TestConcurrentUploadFix:
    """测试并发上传修复"""

    def test_concurrent_same_doc_id_different_filenames(self):
        """
        关键测试: 验证同一单据ID的并发上传会生成不同的文件名

        这是针对 bug "对同一单据id同时上传单据时，似乎会造成图片名称相同的问题" 的修复验证
        """
        temp_dir = tempfile.mkdtemp()
        try:
            # 模拟同一单据ID的并发上传场景
            doc_number = "SO20250103001"  # 同一单据号
            extension = ".jpg"
            concurrent_uploads = 10

            # 并发生成文件名
            filenames = []
            for _ in range(concurrent_uploads):
                filename, _ = generate_unique_filename(doc_number, extension, temp_dir)
                filenames.append(filename)

            # 关键断言: 所有文件名必须唯一
            unique_filenames = set(filenames)
            assert len(unique_filenames) == concurrent_uploads, (
                f"并发上传产生了重复文件名！\n"
                f"期望: {concurrent_uploads} 个唯一文件名\n"
                f"实际: {len(unique_filenames)} 个唯一文件名\n"
                f"重复的文件名: {[f for f in filenames if filenames.count(f) > 1]}"
            )

            # 验证文件名格式
            for filename in filenames:
                assert filename.startswith(doc_number), f"文件名应包含单据号: {filename}"
                assert '_' in filename, f"文件名应包含时间戳和UUID分隔符: {filename}"

            print(f"\n✓ 测试通过: 同一单据ID并发上传生成了 {len(unique_filenames)} 个唯一文件名")
            print("示例文件名:")
            for i, filename in enumerate(filenames[:3], 1):
                print(f"  {i}. {filename}")

        finally:
            shutil.rmtree(temp_dir)

    def test_filename_no_longer_depends_on_filesystem(self):
        """
        测试: 文件名生成不再依赖文件系统状态（修复前的缺陷）

        修复前: 使用 os.path.exists() 检查文件是否存在，存在竞争条件
        修复后: 使用 UUID，完全不依赖文件系统状态
        """
        temp_dir = tempfile.mkdtemp()
        try:
            doc_number = "SO20250103001"
            extension = ".jpg"

            # 生成第一个文件名
            filename1, path1 = generate_unique_filename(doc_number, extension, temp_dir)

            # 即使创建了文件，生成的第二个文件名也应该不同（因为使用UUID）
            Path(path1).touch()  # 创建文件

            filename2, path2 = generate_unique_filename(doc_number, extension, temp_dir)

            # 验证: 即使文件已存在，新文件名也不会冲突
            assert filename1 != filename2, (
                "文件名生成仍然依赖文件系统状态！\n"
                f"filename1: {filename1}\n"
                f"filename2: {filename2}"
            )

            print(f"\n✓ 测试通过: 文件名生成不再依赖文件系统状态")
            print(f"  第1次生成: {filename1}")
            print(f"  第2次生成: {filename2}")

        finally:
            shutil.rmtree(temp_dir)

    def test_filename_format_contains_uniqueness_guarantees(self):
        """
        测试: 验证新文件名格式包含唯一性保证

        格式: {doc_number}_{timestamp}_{uuid}.{extension}
        """
        temp_dir = tempfile.mkdtemp()
        try:
            doc_number = "SO20250103001"
            extension = ".jpg"

            filename, _ = generate_unique_filename(doc_number, extension, temp_dir)

            # 移除扩展名
            base_name = filename.replace(extension, '')
            parts = base_name.split('_')

            # 验证格式: 应该有3部分（单据号、时间戳、UUID）
            assert len(parts) == 3, (
                f"文件名格式错误，应为 doc_number_timestamp_uuid\n"
                f"实际格式: {filename}\n"
                f"拆分结果: {parts}"
            )

            doc_part, timestamp_part, uuid_part = parts

            # 验证各部分
            assert doc_part == doc_number, f"单据号部分不匹配: {doc_part} != {doc_number}"
            assert len(timestamp_part) == 14, f"时间戳应为14位: {timestamp_part}"
            assert timestamp_part.isdigit(), f"时间戳应为纯数字: {timestamp_part}"
            assert len(uuid_part) == 8, f"UUID部分应为8位: {uuid_part}"
            assert uuid_part.isalnum(), f"UUID应为字母数字组合: {uuid_part}"

            print(f"\n✓ 测试通过: 文件名格式正确")
            print(f"  完整文件名: {filename}")
            print(f"  单据号: {doc_part}")
            print(f"  时间戳: {timestamp_part}")
            print(f"  UUID: {uuid_part}")

        finally:
            shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_concurrent_upload_in_production_scenario(self):
        """
        集成测试: 模拟生产环境中的并发上传场景

        场景: 用户在短时间内对同一单据连续上传10张图片
        """
        temp_dir = tempfile.mkdtemp()
        try:
            doc_number = "SO20250103001"
            extension = ".jpg"

            # 模拟并发上传
            async def simulate_upload():
                """模拟一次上传"""
                await asyncio.sleep(0)  # 让出控制权
                filename, full_path = generate_unique_filename(doc_number, extension, temp_dir)
                return filename, full_path

            # 并发执行10次上传
            tasks = [simulate_upload() for _ in range(10)]
            results = await asyncio.gather(*tasks)

            filenames = [r[0] for r in results]
            paths = [r[1] for r in results]

            # 验证唯一性
            assert len(set(filenames)) == 10, f"文件名存在重复: {filenames}"
            assert len(set(paths)) == 10, f"路径存在重复: {paths}"

            print(f"\n✓ 测试通过: 生产场景模拟成功")
            print(f"  并发上传: 10 张图片")
            print(f"  单据ID: {doc_number}")
            print(f"  唯一文件名: {len(set(filenames))} 个")

        finally:
            shutil.rmtree(temp_dir)

    def test_high_concurrency_stress_test(self):
        """
        压力测试: 超高并发场景（100个并发请求）

        验证在极端并发情况下文件名仍然保持唯一
        """
        from concurrent.futures import ThreadPoolExecutor

        temp_dir = tempfile.mkdtemp()
        try:
            doc_number = "SO20250103001"
            extension = ".jpg"
            concurrent_count = 100

            def generate_one():
                return generate_unique_filename(doc_number, extension, temp_dir)[0]

            # 使用线程池模拟高并发
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(generate_one) for _ in range(concurrent_count)]
                filenames = [f.result() for f in futures]

            # 验证100个文件名全部唯一
            unique_count = len(set(filenames))
            assert unique_count == concurrent_count, (
                f"高并发场景下产生了重复文件名！\n"
                f"期望: {concurrent_count} 个唯一文件名\n"
                f"实际: {unique_count} 个唯一文件名"
            )

            print(f"\n✓ 压力测试通过: {concurrent_count} 个并发请求全部生成唯一文件名")

        finally:
            shutil.rmtree(temp_dir)


class TestRegressionPrevention:
    """防止回归测试"""

    def test_old_bug_no_longer_exists(self):
        """
        回归测试: 确保原有的 bug 不会再次出现

        原有bug: 使用 while os.path.exists() 检查文件，存在 TOCTOU 竞争条件
        """
        import inspect
        from app.api.upload import generate_unique_filename

        # 获取函数源代码
        source = inspect.getsource(generate_unique_filename)

        # 验证: 代码中不应该包含 os.path.exists 检查
        assert 'os.path.exists' not in source, (
            "警告: 代码中仍包含 os.path.exists，可能会导致竞争条件！"
        )

        # 验证: 代码中应该包含 uuid
        assert 'uuid' in source, (
            "警告: 代码中未使用 UUID，无法保证并发唯一性！"
        )

        print("\n✓ 回归测试通过: 原有的竞争条件已消除")
        print("  - 不再使用 os.path.exists() 检查")
        print("  - 使用 UUID 保证唯一性")


if __name__ == "__main__":
    print("=" * 70)
    print("运行并发上传修复验证测试")
    print("=" * 70)

    test_fix = TestConcurrentUploadFix()
    test_regression = TestRegressionPrevention()

    print("\n[测试1] 同一单据ID并发上传生成不同文件名")
    test_fix.test_concurrent_same_doc_id_different_filenames()

    print("\n[测试2] 文件名生成不依赖文件系统")
    test_fix.test_filename_no_longer_depends_on_filesystem()

    print("\n[测试3] 文件名格式包含唯一性保证")
    test_fix.test_filename_format_contains_uniqueness_guarantees()

    print("\n[测试4] 生产场景模拟")
    asyncio.run(test_fix.test_concurrent_upload_in_production_scenario())

    print("\n[测试5] 高并发压力测试")
    test_fix.test_high_concurrency_stress_test()

    print("\n[测试6] 回归防止测试")
    test_regression.test_old_bug_no_longer_exists()

    print("\n" + "=" * 70)
    print("✓ 所有测试通过！并发上传bug已修复")
    print("=" * 70)

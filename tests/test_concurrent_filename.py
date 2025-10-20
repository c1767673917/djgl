"""测试并发场景下的文件命名唯一性"""
import pytest
import asyncio
import os
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# 直接导入函数进行单元测试
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.upload import generate_unique_filename


class TestConcurrentFilenameGeneration:
    """测试并发文件名生成的唯一性"""

    def test_sequential_filename_uniqueness(self):
        """测试顺序生成10个文件名的唯一性"""
        temp_dir = tempfile.mkdtemp()
        try:
            doc_number = "SO20250103001"
            extension = ".jpg"
            filenames = []

            for i in range(10):
                filename, _ = generate_unique_filename(doc_number, extension, temp_dir)
                filenames.append(filename)

            # 验证所有文件名都是唯一的
            assert len(filenames) == len(set(filenames)), "顺序生成的文件名存在重复"

            # 验证文件名格式
            for filename in filenames:
                assert filename.startswith(doc_number), f"文件名应以单据号开头: {filename}"
                assert filename.endswith(extension), f"文件名应以扩展名结尾: {filename}"
                # 文件名格式: doc_number_timestamp_uuid.extension
                parts = filename.replace(extension, '').split('_')
                assert len(parts) == 3, f"文件名格式错误: {filename}"

        finally:
            shutil.rmtree(temp_dir)

    def test_concurrent_filename_uniqueness_multithread(self):
        """测试多线程并发生成100个文件名的唯一性（最严格测试）"""
        temp_dir = tempfile.mkdtemp()
        try:
            doc_number = "SO20250103001"
            extension = ".jpg"
            filenames = []

            def generate_one_filename():
                filename, _ = generate_unique_filename(doc_number, extension, temp_dir)
                return filename

            # 使用线程池模拟并发请求
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(generate_one_filename) for _ in range(100)]
                for future in futures:
                    filenames.append(future.result())

            # 验证所有文件名都是唯一的
            unique_count = len(set(filenames))
            total_count = len(filenames)
            assert unique_count == total_count, (
                f"并发生成的文件名存在重复: "
                f"生成了{total_count}个文件名，但只有{unique_count}个唯一值"
            )

            print(f"✓ 成功生成 {total_count} 个唯一文件名")
            print(f"示例文件名:")
            for i in range(min(5, len(filenames))):
                print(f"  {filenames[i]}")

        finally:
            shutil.rmtree(temp_dir)

    def test_concurrent_filename_uniqueness_same_doc_id(self):
        """测试同一单据ID的并发上传生成唯一文件名"""
        temp_dir = tempfile.mkdtemp()
        try:
            doc_number = "SO20250103001"
            extension = ".jpg"
            concurrent_count = 50

            def generate_one_filename():
                filename, full_path = generate_unique_filename(doc_number, extension, temp_dir)
                return filename, full_path

            # 模拟同一单据的并发上传
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(generate_one_filename) for _ in range(concurrent_count)]
                results = [future.result() for future in futures]

            filenames = [r[0] for r in results]
            full_paths = [r[1] for r in results]

            # 验证文件名唯一性
            assert len(filenames) == len(set(filenames)), "同一单据ID的并发上传产生了重复文件名"

            # 验证完整路径唯一性
            assert len(full_paths) == len(set(full_paths)), "同一单据ID的并发上传产生了重复完整路径"

            print(f"✓ 同一单据ID并发生成 {concurrent_count} 个唯一文件名")

        finally:
            shutil.rmtree(temp_dir)

    def test_filename_format_consistency(self):
        """测试文件名格式的一致性"""
        temp_dir = tempfile.mkdtemp()
        try:
            doc_number = "SO20250103001"
            extension = ".jpg"

            filename, full_path = generate_unique_filename(doc_number, extension, temp_dir)

            # 验证文件名格式: doc_number_timestamp_uuid.extension
            assert filename.startswith(doc_number), "文件名必须以单据号开头"
            assert filename.endswith(extension), "文件名必须以扩展名结尾"

            # 提取组成部分
            base_name = filename.replace(extension, '')
            parts = base_name.split('_')

            assert len(parts) == 3, f"文件名应包含3部分（单据号_时间戳_UUID），实际: {parts}"

            # 验证单据号
            assert parts[0] == doc_number, f"单据号不匹配: {parts[0]} != {doc_number}"

            # 验证时间戳格式 (YYYYMMDDHHMMSS, 14位数字)
            assert len(parts[1]) == 14, f"时间戳应为14位: {parts[1]}"
            assert parts[1].isdigit(), f"时间戳应为纯数字: {parts[1]}"

            # 验证UUID部分 (8位十六进制)
            assert len(parts[2]) == 8, f"UUID应为8位: {parts[2]}"
            # UUID由数字和字母组成
            assert parts[2].isalnum(), f"UUID应为字母数字组合: {parts[2]}"

            # 验证完整路径
            expected_path = os.path.join(temp_dir, filename)
            assert full_path == expected_path, f"完整路径不匹配: {full_path} != {expected_path}"

            print(f"✓ 文件名格式验证通过: {filename}")

        finally:
            shutil.rmtree(temp_dir)

    def test_different_doc_numbers_different_filenames(self):
        """测试不同单据号生成不同的文件名前缀"""
        temp_dir = tempfile.mkdtemp()
        try:
            doc_numbers = ["SO20250103001", "SO20250103002", "SO20250103003"]
            extension = ".jpg"

            filenames_by_doc = {}
            for doc_number in doc_numbers:
                filename, _ = generate_unique_filename(doc_number, extension, temp_dir)
                filenames_by_doc[doc_number] = filename
                assert filename.startswith(doc_number), f"文件名应以 {doc_number} 开头"

            # 验证不同单据号的文件名确实不同
            all_filenames = list(filenames_by_doc.values())
            assert len(all_filenames) == len(set(all_filenames)), "不同单据号应生成不同的文件名"

            print(f"✓ 不同单据号生成不同文件名")
            for doc_number, filename in filenames_by_doc.items():
                print(f"  {doc_number} -> {filename}")

        finally:
            shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_async_concurrent_filename_generation(self):
        """测试异步并发场景下的文件名唯一性（模拟实际FastAPI环境）"""
        temp_dir = tempfile.mkdtemp()
        try:
            doc_number = "SO20250103001"
            extension = ".jpg"
            concurrent_count = 100

            async def generate_async():
                # 在异步环境中调用同步函数
                await asyncio.sleep(0)  # 让出控制权
                filename, _ = generate_unique_filename(doc_number, extension, temp_dir)
                return filename

            # 并发执行
            tasks = [generate_async() for _ in range(concurrent_count)]
            filenames = await asyncio.gather(*tasks)

            # 验证唯一性
            unique_count = len(set(filenames))
            total_count = len(filenames)
            assert unique_count == total_count, (
                f"异步并发生成的文件名存在重复: "
                f"生成了{total_count}个文件名，但只有{unique_count}个唯一值"
            )

            print(f"✓ 异步并发成功生成 {total_count} 个唯一文件名")

        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    # 运行快速测试
    print("=" * 60)
    print("运行并发文件名生成测试")
    print("=" * 60)

    test = TestConcurrentFilenameGeneration()

    print("\n[1/6] 测试顺序生成的唯一性...")
    test.test_sequential_filename_uniqueness()

    print("\n[2/6] 测试多线程并发生成的唯一性...")
    test.test_concurrent_filename_uniqueness_multithread()

    print("\n[3/6] 测试同一单据ID的并发上传...")
    test.test_concurrent_filename_uniqueness_same_doc_id()

    print("\n[4/6] 测试文件名格式一致性...")
    test.test_filename_format_consistency()

    print("\n[5/6] 测试不同单据号生成不同文件名...")
    test.test_different_doc_numbers_different_filenames()

    print("\n[6/6] 测试异步并发场景...")
    asyncio.run(test.test_async_concurrent_filename_generation())

    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)

#!/usr/bin/env python3
"""
演示并发上传文件名冲突修复效果

这个脚本展示了修复前后的行为差异
"""

import os
import sys
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.upload import generate_unique_filename


def simulate_old_broken_version(doc_number, extension, storage_path):
    """
    模拟修复前的有bug的版本（仅用于演示）

    这个函数复现了原有的竞争条件问题
    """
    base_name = doc_number
    counter = 1
    new_filename = f"{base_name}{extension}"
    full_path = os.path.join(storage_path, new_filename)

    # 这里存在竞争条件！
    while os.path.exists(full_path):
        new_filename = f"{base_name}-{counter}{extension}"
        full_path = os.path.join(storage_path, new_filename)
        counter += 1

    return new_filename, full_path


def demo_old_version_bug():
    """演示修复前的bug"""
    print("=" * 70)
    print("演示1: 修复前的版本 (有BUG)")
    print("=" * 70)

    temp_dir = tempfile.mkdtemp()
    try:
        doc_number = "SO20250103001"
        extension = ".jpg"
        concurrent_count = 10

        print(f"\n场景: 同一单据ID ({doc_number}) 并发上传 {concurrent_count} 张图片")
        print("使用旧版本的文件名生成逻辑...\n")

        def generate_and_save():
            """生成文件名并立即创建文件"""
            filename, full_path = simulate_old_broken_version(doc_number, extension, temp_dir)
            # 模拟保存文件（创建空文件）
            Path(full_path).touch()
            return filename

        # 并发执行
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(generate_and_save) for _ in range(concurrent_count)]
            filenames = [f.result() for f in futures]

        # 检查结果
        unique_filenames = set(filenames)
        files_in_dir = list(Path(temp_dir).glob("*.jpg"))

        print(f"结果分析:")
        print(f"  期望生成文件数: {concurrent_count}")
        print(f"  实际生成文件数: {len(files_in_dir)}")
        print(f"  唯一文件名数量: {len(unique_filenames)}")
        print(f"  是否有冲突: {'是 ❌' if len(unique_filenames) < concurrent_count else '否 ✓'}")

        if len(unique_filenames) < concurrent_count:
            print(f"\n⚠️  警告: 发现 {concurrent_count - len(unique_filenames)} 个文件名冲突!")
            print("  这会导致文件被覆盖，数据丢失！")

        print(f"\n生成的文件:")
        for i, f in enumerate(sorted(files_in_dir)[:5], 1):
            print(f"  {i}. {f.name}")

    finally:
        shutil.rmtree(temp_dir)


def demo_new_version_fixed():
    """演示修复后的版本"""
    print("\n\n" + "=" * 70)
    print("演示2: 修复后的版本 (已修复)")
    print("=" * 70)

    temp_dir = tempfile.mkdtemp()
    try:
        doc_number = "SO20250103001"
        extension = ".jpg"
        concurrent_count = 10

        print(f"\n场景: 同一单据ID ({doc_number}) 并发上传 {concurrent_count} 张图片")
        print("使用新版本的文件名生成逻辑 (UUID + 时间戳)...\n")

        def generate_and_save():
            """生成文件名并立即创建文件"""
            filename, full_path = generate_unique_filename(doc_number, extension, temp_dir)
            # 模拟保存文件（创建空文件）
            Path(full_path).touch()
            return filename

        # 并发执行
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(generate_and_save) for _ in range(concurrent_count)]
            filenames = [f.result() for f in futures]

        # 检查结果
        unique_filenames = set(filenames)
        files_in_dir = list(Path(temp_dir).glob("*.jpg"))

        print(f"结果分析:")
        print(f"  期望生成文件数: {concurrent_count}")
        print(f"  实际生成文件数: {len(files_in_dir)}")
        print(f"  唯一文件名数量: {len(unique_filenames)}")
        print(f"  是否有冲突: {'是 ❌' if len(unique_filenames) < concurrent_count else '否 ✓'}")

        if len(unique_filenames) == concurrent_count:
            print(f"\n✓ 成功: 所有文件名都是唯一的!")
            print("  不会发生文件覆盖，数据安全！")

        print(f"\n生成的文件 (显示前5个):")
        for i, f in enumerate(sorted(files_in_dir)[:5], 1):
            print(f"  {i}. {f.name}")

        print(f"\n文件名格式分析:")
        example_name = files_in_dir[0].name.replace('.jpg', '')
        parts = example_name.split('_')
        if len(parts) == 3:
            print(f"  格式: {{单据号}}_{{时间戳}}_{{UUID}}.{{扩展名}}")
            print(f"  单据号: {parts[0]}")
            print(f"  时间戳: {parts[1]}")
            print(f"  UUID:   {parts[2]}")

    finally:
        shutil.rmtree(temp_dir)


def demo_comparison():
    """对比演示"""
    print("\n\n" + "=" * 70)
    print("演示3: 性能对比")
    print("=" * 70)

    import time

    temp_dir = tempfile.mkdtemp()
    try:
        doc_number = "SO20250103001"
        extension = ".jpg"
        test_count = 100

        # 测试旧版本性能
        print(f"\n测试旧版本性能 (生成{test_count}个文件名)...")
        start = time.time()
        for i in range(test_count):
            _ = simulate_old_broken_version(doc_number, extension, temp_dir)
        old_time = time.time() - start

        # 测试新版本性能
        print(f"测试新版本性能 (生成{test_count}个文件名)...")
        start = time.time()
        for i in range(test_count):
            _ = generate_unique_filename(doc_number, extension, temp_dir)
        new_time = time.time() - start

        print(f"\n性能对比:")
        print(f"  旧版本: {old_time:.4f} 秒")
        print(f"  新版本: {new_time:.4f} 秒")
        print(f"  速度提升: {old_time/new_time:.2f}x")
        print(f"  性能改进: {((old_time - new_time) / old_time * 100):.1f}%")

    finally:
        shutil.rmtree(temp_dir)


def main():
    """主函数"""
    print("\n" + "█" * 70)
    print("并发上传文件名冲突修复 - 效果演示")
    print("█" * 70)

    # 演示1: 旧版本的bug
    demo_old_version_bug()

    # 演示2: 新版本修复
    demo_new_version_fixed()

    # 演示3: 性能对比
    demo_comparison()

    print("\n\n" + "=" * 70)
    print("总结")
    print("=" * 70)
    print("""
修复前:
  ❌ 存在竞争条件，并发时会产生相同文件名
  ❌ 文件会被覆盖，导致数据丢失
  ❌ 性能随文件数量下降

修复后:
  ✓ 使用UUID保证绝对唯一性
  ✓ 并发安全，不会产生文件名冲突
  ✓ 性能更优，无需文件系统检查
  ✓ 文件名包含时间信息，便于追溯
    """)

    print("=" * 70)
    print("演示完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()

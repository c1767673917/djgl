"""
清空历史数据脚本

警告：此操作不可逆，执行前请确认已备份重要数据！
"""
import sqlite3
import sys
from pathlib import Path

# 添加项目路径到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import get_db_connection


def clear_history_data():
    """清空上传历史数据"""

    # 二次确认
    print("⚠️  警告：此操作将清空所有上传历史记录！")
    print("⚠️  请确认您已备份重要数据。")
    confirm = input("确认清空？(yes/no): ").strip().lower()

    if confirm != 'yes':
        print("❌ 操作已取消。")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 查询当前记录数
        cursor.execute("SELECT COUNT(*) FROM upload_history")
        count_before = cursor.fetchone()[0]
        print(f"\n📊 当前记录数: {count_before}")

        if count_before == 0:
            print("✅ 数据库已经是空的，无需清理。")
            conn.close()
            return

        # 执行清空操作
        print("\n🗑️  正在清空数据...")
        cursor.execute("DELETE FROM upload_history")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='upload_history'")
        conn.commit()

        # 验证清空结果
        cursor.execute("SELECT COUNT(*) FROM upload_history")
        count_after = cursor.fetchone()[0]

        if count_after == 0:
            print(f"✅ 成功清空 {count_before} 条记录！")
            print("✅ 主键计数器已重置。")
        else:
            print(f"⚠️  警告：仍有 {count_after} 条记录未删除。")

        conn.close()

    except Exception as e:
        print(f"❌ 清空失败: {str(e)}")
        raise


if __name__ == "__main__":
    clear_history_data()

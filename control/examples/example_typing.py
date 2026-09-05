"""
示例 2: 文本输入操作
====================
展示如何使用引擎进行拟人化的文本输入。

运行方式:
    python example_typing.py

注意:
    - 需要 Pico 硬件连接
    - 演示了不同速度的打字
    - 支持特殊字符和快捷键
"""

import time
import sys
from engine_v2 import HumanMotionEngine, HIDKey, Modifier


def main():
    print("=" * 60)
    print("示例 2: 文本输入操作")
    print("=" * 60)
    
    port = '/dev/tty.usbserial-110'  # 修改为你的实际端口
    engine = HumanMotionEngine(serial_port=port)
    
    # 1. 连接
    print("\n[1/5] 连接 Pico 设备...")
    if not engine.connect():
        print("❌ 连接失败")
        sys.exit(1)
    print("✓ 连接成功")
    
    # 2. 移动到文本框位置
    print("\n[2/5] 移动到文本框位置...")
    engine.move_to(500, 300)
    engine.click()  # 点击激活输入框
    time.sleep(0.5)
    
    # 3. 慢速打字 (模拟新手)
    print("\n[3/5] 慢速打字 (30 WPM, 模拟新手)...")
    engine.type_string(
        "Hello, this is a slow typing demo.",
        wpm=30.0,
        fatigue=0.0
    )
    print("✓ 打字完成")
    time.sleep(0.5)
    
    # 4. 换行
    print("\n[4/5] 按 Enter 换行...")
    engine.key_press(HIDKey.ENTER, Modifier.NONE)
    time.sleep(0.3)
    
    # 5. 快速打字 (模拟熟练用户)
    print("\n[5/5] 快速打字 (80 WPM, 模拟熟练用户)...")
    engine.type_string(
        "This is much faster! 12345 @#$%",
        wpm=80.0,
        fatigue=0.0
    )
    print("✓ 打字完成")
    time.sleep(0.5)
    
    # 6. 演示快捷键
    print("\n[6/7] 演示常用快捷键...")
    
    print("  - Ctrl+A (全选)")
    engine.key_combo(Modifier.LEFT_CTRL, HIDKey.A)
    time.sleep(0.3)
    
    print("  - Ctrl+C (复制)")
    engine.key_combo(Modifier.LEFT_CTRL, HIDKey.C)
    time.sleep(0.3)
    
    print("  - Ctrl+V (粘贴)")
    engine.key_combo(Modifier.LEFT_CTRL, HIDKey.V)
    time.sleep(0.3)
    
    print("  - Home 键")
    engine.key_press(HIDKey.HOME, Modifier.NONE)
    time.sleep(0.3)
    
    print("  - End 键")
    engine.key_press(HIDKey.END, Modifier.NONE)
    time.sleep(0.3)
    
    # 7. 演示疲劳对打字的影响
    print("\n[7/7] 模拟疲劳状态打字 (高疲劳, 可能出错)...")
    engine.key_press(HIDKey.ENTER, Modifier.NONE)
    engine.type_string(
        "Typing when tired... might make mistakes!",
        wpm=50.0,
        fatigue=0.8  # 高疲劳
    )
    
    # 8. 统计
    print("\n" + "=" * 60)
    print("操作完成！")
    print("=" * 60)
    stats = engine.get_stats()
    print(f"  总指令数: {stats['commands_sent']}")
    print(f"  当前位置: {stats['cursor']}")
    
    # 9. 断开
    engine.disconnect()
    print("\n✓ 完成")


if __name__ == '__main__':
    main()

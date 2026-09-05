"""
示例 1: 简单的鼠标移动和点击
==============================
这个示例展示如何使用微观引擎完成基础的鼠标操作。

运行方式:
    python example_simple_click.py

注意:
    - 需要 Pico 硬件连接
    - 会移动鼠标到屏幕中心并点击
    - 演示了相对移动、绝对移动、双击等操作
"""

import time
import sys
from engine_v2 import HumanMotionEngine


def main():
    print("=" * 60)
    print("示例 1: 简单的鼠标移动和点击")
    print("=" * 60)
    
    # 1. 初始化引擎 (根据你的实际端口修改)
    # macOS: /dev/tty.usbserial-XXX
    # Windows: COM3, COM4 等
    # Linux: /dev/ttyACM0, /dev/ttyUSB0 等
    port = '/dev/tty.usbserial-110'  # 修改为你的实际端口
    
    engine = HumanMotionEngine(serial_port=port)
    
    # 2. 连接 Pico
    print("\n[1/6] 连接 Pico 设备...")
    if not engine.connect():
        print("❌ 连接失败！请检查:")
        print(f"  - 串口设备: {port}")
        print("  - Pico 是否已连接")
        print("  - 波特率是否正确 (115200)")
        sys.exit(1)
    
    print("✓ 连接成功")
    
    # 3. 同步位置
    print("\n[2/6] 同步当前鼠标位置...")
    x, y = engine.sync_position()
    print(f"✓ 当前位置: ({x}, {y})")
    
    # 4. 相对移动
    print("\n[3/6] 相对移动 (+100, +50)...")
    engine.move_relative(100, 50)
    time.sleep(0.5)
    
    # 5. 绝对移动到屏幕中心
    print("\n[4/6] 移动到屏幕中心 (假设 1920x1080)...")
    engine.move_to(960, 540)
    print("✓ 已移动到 (960, 540)")
    time.sleep(0.5)
    
    # 6. 点击操作
    print("\n[5/6] 执行点击操作...")
    print("  - 单击左键")
    engine.click(button=1)
    time.sleep(0.3)
    
    print("  - 双击左键")
    engine.double_click(button=1)
    time.sleep(0.3)
    
    print("  - 右键点击")
    engine.click(button=2)
    time.sleep(0.3)
    
    # 7. 拖拽操作
    print("\n[6/6] 执行拖拽操作...")
    print("  - 从 (960, 540) 拖拽到 (1100, 600)")
    engine.drag_to(1100, 600, button=1)
    print("✓ 拖拽完成")
    
    # 8. 打印统计
    print("\n" + "=" * 60)
    print("操作完成！统计信息:")
    print("=" * 60)
    stats = engine.get_stats()
    print(f"  总指令数: {stats['commands_sent']}")
    print(f"  成功 ACK: {stats['ack_ok']}")
    print(f"  失败 ACK: {stats['ack_fail']}")
    print(f"  成功率: {stats['ack_success_rate']*100:.1f}%")
    
    # 9. 断开连接
    print("\n断开连接...")
    engine.disconnect()
    print("✓ 完成")


if __name__ == '__main__':
    main()

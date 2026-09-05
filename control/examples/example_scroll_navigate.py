"""
示例 3: 滚动和导航
==================
展示如何使用鼠标滚轮和键盘导航。

运行方式:
    python example_scroll_navigate.py

注意:
    - 需要 Pico 硬件连接
    - 演示了网页滚动、表格导航等场景
"""

import time
import sys
from engine_v2 import HumanMotionEngine, HIDKey, Modifier


def main():
    print("=" * 60)
    print("示例 3: 滚动和导航")
    print("=" * 60)
    
    port = '/dev/tty.usbserial-110'  # 修改为你的实际端口
    engine = HumanMotionEngine(serial_port=port)
    
    # 1. 连接
    print("\n[1/6] 连接 Pico 设备...")
    if not engine.connect():
        print("❌ 连接失败")
        sys.exit(1)
    print("✓ 连接成功")
    
    # 2. 模拟网页滚动
    print("\n[2/6] 模拟网页滚动...")
    
    # 慢速向下滚动 (像阅读文章)
    print("  - 向下滚动 10 格 (慢速)")
    for _ in range(10):
        engine.scroll(-1)
        time.sleep(0.3)  # 每格间隔 300ms (阅读速度)
    
    time.sleep(0.5)
    
    # 快速向上滚动 (回到顶部)
    print("  - 向上滚动 15 格 (快速)")
    engine.scroll(15)
    time.sleep(0.5)
    
    # 3. 键盘导航
    print("\n[3/6] 键盘导航 (Tab/方向键)...")
    
    # Tab 切换焦点
    print("  - Tab 切换焦点 3 次")
    for i in range(3):
        engine.key_press(HIDKey.TAB, Modifier.NONE)
        time.sleep(0.5)
    
    # 方向键导航
    print("  - 方向键导航")
    engine.key_press(HIDKey.DOWN, Modifier.NONE)
    time.sleep(0.3)
    engine.key_press(HIDKey.RIGHT, Modifier.NONE)
    time.sleep(0.3)
    engine.key_press(HIDKey.LEFT, Modifier.NONE)
    time.sleep(0.3)
    engine.key_press(HIDKey.UP, Modifier.NONE)
    time.sleep(0.3)
    
    # 4. 页面跳转
    print("\n[4/6] 页面跳转快捷键...")
    
    print("  - Ctrl+Home (到页面顶部)")
    engine.key_combo(Modifier.LEFT_CTRL, HIDKey.HOME)
    time.sleep(0.5)
    
    print("  - Ctrl+End (到页面底部)")
    engine.key_combo(Modifier.LEFT_CTRL, HIDKey.END)
    time.sleep(0.5)
    
    print("  - Page Down")
    engine.key_press(HIDKey.PAGE_DOWN, Modifier.NONE)
    time.sleep(0.5)
    
    print("  - Page Up")
    engine.key_press(HIDKey.PAGE_UP, Modifier.NONE)
    time.sleep(0.5)
    
    # 5. 浏览器快捷键
    print("\n[5/6] 浏览器常用快捷键...")
    
    print("  - Ctrl+T (新标签页)")
    engine.key_combo(Modifier.LEFT_CTRL, HIDKey.T)
    time.sleep(0.5)
    
    print("  - Ctrl+W (关闭标签页)")
    engine.key_combo(Modifier.LEFT_CTRL, HIDKey.W)
    time.sleep(0.5)
    
    print("  - Ctrl+R (刷新)")
    engine.key_combo(Modifier.LEFT_CTRL, HIDKey.R)
    time.sleep(0.5)
    
    print("  - F5 (刷新)")
    engine.key_press(HIDKey.F5, Modifier.NONE)
    time.sleep(0.5)
    
    # 6. 地址栏输入
    print("\n[6/6] 地址栏输入 URL...")
    
    print("  - Ctrl+L (聚焦地址栏)")
    engine.key_combo(Modifier.LEFT_CTRL, HIDKey.L)
    time.sleep(0.5)
    
    print("  - 输入 URL")
    engine.type_string("https://example.com", wpm=100.0)
    time.sleep(0.3)
    
    print("  - Enter 访问")
    engine.key_press(HIDKey.ENTER, Modifier.NONE)
    
    # 7. 统计
    print("\n" + "=" * 60)
    print("操作完成！")
    print("=" * 60)
    stats = engine.get_stats()
    print(f"  总指令数: {stats['commands_sent']}")
    
    # 8. 断开
    engine.disconnect()
    print("\n✓ 完成")


if __name__ == '__main__':
    main()

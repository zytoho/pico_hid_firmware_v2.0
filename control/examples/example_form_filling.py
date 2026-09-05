"""
示例 5: 完整的表单填写任务
===========================
演示一个完整的 RPA 任务：填写 Web 表单。

运行方式:
    python example_form_filling.py

注意:
    - 需要 Pico 硬件连接
    - 假设浏览器已打开并停留在表单页面
    - 需要根据实际表单位置调整坐标
"""

import time
import sys
from engine_v2 import HumanMotionEngine, HIDKey, Modifier
from agent_v2 import MacroAgent


def main():
    print("=" * 60)
    print("示例 5: 完整的表单填写任务")
    print("=" * 60)
    
    port = '/dev/tty.usbserial-110'  # 修改为你的实际端口
    engine = HumanMotionEngine(serial_port=port)
    agent = MacroAgent()
    
    # 1. 初始化
    print("\n[1/7] 初始化系统...")
    if not engine.connect():
        print("❌ 连接失败")
        sys.exit(1)
    agent.start()
    print("✓ 系统初始化完成")
    
    # 2. 点击第一个输入框
    print("\n[2/7] 填写姓名字段...")
    engine.move_to(500, 300)  # 假设姓名输入框在 (500, 300)
    engine.click()
    time.sleep(0.3)
    
    engine.type_string("张三", wpm=50.0)
    agent.log_action()
    print("✓ 姓名已填写")
    
    # 3. Tab 到下一个字段
    print("\n[3/7] 填写邮箱字段...")
    engine.key_press(HIDKey.TAB, Modifier.NONE)
    time.sleep(0.3)
    
    engine.type_string("zhangsan@example.com", wpm=60.0)
    agent.log_action()
    print("✓ 邮箱已填写")
    
    # 4. 填写手机号
    print("\n[4/7] 填写手机号字段...")
    engine.key_press(HIDKey.TAB, Modifier.NONE)
    time.sleep(0.3)
    
    engine.type_string("13800138000", wpm=70.0)
    agent.log_action()
    print("✓ 手机号已填写")
    
    # 5. 选择下拉菜单 (假设)
    print("\n[5/7] 选择城市下拉菜单...")
    engine.move_to(500, 500)  # 假设下拉菜单在 (500, 500)
    engine.click()
    time.sleep(0.5)
    
    # 向下选择选项
    engine.key_press(HIDKey.DOWN, Modifier.NONE)
    engine.key_press(HIDKey.DOWN, Modifier.NONE)
    engine.key_press(HIDKey.ENTER, Modifier.NONE)
    agent.log_action()
    print("✓ 城市已选择")
    
    # 6. 勾选复选框 (假设)
    print("\n[6/7] 勾选同意条款复选框...")
    engine.move_to(500, 700)  # 假设复选框在 (500, 700)
    engine.click()
    agent.log_action()
    print("✓ 复选框已勾选")
    
    # 7. 提交表单
    print("\n[7/7] 提交表单...")
    engine.move_to(600, 800)  # 假设提交按钮在 (600, 800)
    engine.click()
    agent.log_action()
    print("✓ 表单已提交")
    
    # 8. 统计
    print("\n" + "=" * 60)
    print("表单填写完成！")
    print("=" * 60)
    
    engine_stats = engine.get_stats()
    agent_status = agent.get_status()
    
    print("\n引擎统计:")
    print(f"  总指令数: {engine_stats['commands_sent']}")
    print(f"  ACK 成功率: {engine_stats['ack_success_rate']*100:.1f}%")
    
    print("\nAgent 统计:")
    print(f"  当前疲劳度: {agent_status['profile']['fatigue']:.3f}")
    print(f"  当前注意力: {agent_status['profile']['focus']:.3f}")
    print(f"  操作次数: {agent_status['stats']['total_actions']}")
    
    # 9. 清理
    engine.disconnect()
    agent.stop()
    print("\n✓ 任务完成")


if __name__ == '__main__':
    main()

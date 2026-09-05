"""
示例 4: 视觉检测 + 点击
========================
结合视觉流水线和微观引擎，实现目标检测和自动点击。

运行方式:
    python example_vision_click.py

注意:
    - 需要 Pico 硬件连接
    - 需要 YOLO 模型 (yolov8n.pt)
    - 需要 Moonlight 或其他目标窗口打开
    - 会自动检测"person"类别并点击

前置条件:
    1. 确保 YOLO 模型已下载:
       wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt
    
    2. 确保目标窗口已打开 (如 Moonlight)
"""

import time
import sys
from engine_v2 import HumanMotionEngine
from vision_pipeline import VisionPipeline


def main():
    print("=" * 60)
    print("示例 4: 视觉检测 + 点击")
    print("=" * 60)
    
    port = '/dev/tty.usbserial-110'  # 修改为你的实际端口
    engine = HumanMotionEngine(serial_port=port)
    
    # 1. 连接引擎
    print("\n[1/5] 连接 Pico 设备...")
    if not engine.connect():
        print("❌ 连接失败")
        sys.exit(1)
    print("✓ 连接成功")
    
    # 2. 初始化视觉流水线
    print("\n[2/5] 初始化视觉流水线...")
    try:
        vision = VisionPipeline(
            model_path='yolov8n.pt',
            window_title=None,  # 全屏截图，或指定窗口标题
            fps_limit=10
        )
        print("✓ 视觉流水线初始化成功")
    except Exception as e:
        print(f"❌ 视觉流水线初始化失败: {e}")
        engine.disconnect()
        sys.exit(1)
    
    # 3. 截图测试
    print("\n[3/5] 测试截图...")
    frame = vision.capture_frame()
    if frame is None:
        print("❌ 截图失败")
        engine.disconnect()
        sys.exit(1)
    print(f"✓ 截图成功: {frame.shape}")
    
    # 4. 检测目标
    print("\n[4/5] 检测目标 (person)...")
    
    max_attempts = 10
    target_found = False
    
    for attempt in range(max_attempts):
        print(f"  尝试 {attempt+1}/{max_attempts}...")
        
        # 检测
        detections = vision.detect(conf_threshold=0.5)
        print(f"  检测到 {len(detections)} 个目标")
        
        # 查找 person
        target = vision.find_target(class_name='person')
        
        if target:
            target_found = True
            print(f"  ✓ 找到 person: {target.class_name} ({target.confidence:.2f})")
            print(f"    中心位置: {target.center}")
            
            # 移动并点击
            print("  移动到目标位置...")
            engine.move_to(target.center[0], target.center[1])
            
            print("  点击目标...")
            engine.click(button=1)
            
            break
        
        time.sleep(0.5)
    
    if not target_found:
        print("⚠ 未找到 person 目标")
        print("  可能原因:")
        print("  - 画面中没有 person")
        print("  - 置信度阈值太高 (当前 0.5)")
        print("  - 需要调整目标类别")
    
    # 5. 统计
    print("\n" + "=" * 60)
    print("操作完成！")
    print("=" * 60)
    engine_stats = engine.get_stats()
    vision_stats = vision.get_stats()
    
    print("\n引擎统计:")
    print(f"  总指令数: {engine_stats['commands_sent']}")
    print(f"  ACK 成功率: {engine_stats['ack_success_rate']*100:.1f}%")
    
    print("\n视觉统计:")
    print(f"  帧数: {vision_stats['frames_captured']}")
    print(f"  检测次数: {vision_stats['detections_run']}")
    print(f"  FPS: {vision_stats['average_fps']:.1f}")
    
    # 6. 清理
    engine.disconnect()
    vision.cleanup()
    print("\n✓ 完成")


if __name__ == '__main__':
    main()

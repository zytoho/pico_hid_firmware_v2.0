"""
集成测试
========
测试完整系统集成 (需要硬件连接)
"""

import sys
import time
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('IntegrationTest')


def test_engine_connection():
    """测试引擎连接"""
    logger.info("=== 测试 1: 引擎连接 ===")
    
    try:
        from engine_v2 import HumanMotionEngine
        
        # 尝试连接 (使用默认端口, 可能需要修改)
        engine = HumanMotionEngine(serial_port='/dev/cu.usbserial-BG03FPHM')
        
        if engine.connect():
            logger.info("✓ 引擎连接成功")
            stats = engine.get_stats()
            logger.info(f"  状态: {stats}")
            engine.disconnect()
            return True
        else:
            logger.warning("✗ 引擎连接失败 (可能未连接硬件)")
            return False
    
    except Exception as e:
        logger.error(f"✗ 引擎测试异常: {e}")
        return False


def test_vision_pipeline():
    """测试视觉流水线"""
    logger.info("=== 测试 2: 视觉流水线 ===")
    
    try:
        from vision_pipeline import VisionPipeline
        
        # 初始化 (需要 YOLO 模型)
        vision = VisionPipeline(model_path='yolov8n.pt', fps_limit=10)
        
        # 单次截图
        frame = vision.capture_frame()
        if frame is not None:
            logger.info(f"✓ 截图成功: {frame.shape}")
        else:
            logger.warning("✗ 截图失败")
            return False
        
        # 单次检测
        detections = vision.detect(conf_threshold=0.5)
        logger.info(f"✓ 检测到 {len(detections)} 个目标")
        
        return True
    
    except ImportError as e:
        logger.warning(f"⚠ 视觉依赖缺失: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ 视觉测试异常: {e}")
        return False


def test_agent_lifecycle():
    """测试 Agent 生命周期"""
    logger.info("=== 测试 3: Agent 生命周期 ===")
    
    try:
        from agent_v2 import MacroAgent, AgentState
        
        agent = MacroAgent()
        
        # 启动
        agent.start()
        assert agent.state == AgentState.WORKING, "启动后状态应该是 WORKING"
        logger.info("✓ Agent 启动成功")
        
        # 运行一段时间
        time.sleep(0.5)
        
        # 获取状态
        status = agent.get_status()
        logger.info(f"✓ Agent 状态: {status['state']}")
        logger.info(f"  Profile: fatigue={status['profile']['fatigue']:.3f}, "
                   f"focus={status['profile']['focus']:.3f}")
        
        # 记录动作
        for _ in range(5):
            agent.log_action()
        logger.info("✓ 动作记录成功")
        
        # 停止
        agent.stop()
        assert agent.state == AgentState.IDLE, "停止后状态应该是 IDLE"
        logger.info("✓ Agent 停止成功")
        
        return True
    
    except Exception as e:
        logger.error(f"✗ Agent 测试异常: {e}")
        return False


def test_full_integration():
    """测试完整系统集成 (需要硬件)"""
    logger.info("=== 测试 4: 完整系统集成 ===")
    
    try:
        from main import ControlSystem, load_config
        from engine_v2 import HIDKey, Modifier
        
        # 加载配置
        config = load_config('config.yaml')
        
        # 创建系统
        system = ControlSystem(config)
        
        # 启动
        if not system.start():
            logger.warning("✗ 系统启动失败 (可能硬件未连接)")
            return False
        
        logger.info("✓ 系统启动成功")
        
        # 简单测试: 移动 + 点击
        logger.info("  执行: 移动到 (500, 300) 并点击")
        system.engine.move_to(500, 300)
        system.engine.click()
        system.agent.log_action()
        
        time.sleep(0.5)
        
        # 打字测试
        logger.info("  执行: 打字 'test'")
        system.engine.type_string("test")
        system.agent.log_action()
        
        time.sleep(0.5)
        
        # 快捷键测试
        logger.info("  执行: Ctrl+A (全选)")
        system.engine.key_combo(Modifier.LEFT_CTRL, HIDKey.A)
        system.agent.log_action()
        
        # 获取状态
        status = system.get_status()
        logger.info(f"✓ 系统状态: {status['engine']['commands_sent']} 条指令已发送")
        
        # 停止
        system.stop()
        logger.info("✓ 系统停止成功")
        
        return True
    
    except Exception as e:
        logger.error(f"✗ 集成测试异常: {e}")
        return False


def run_integration_tests():
    """运行所有集成测试"""
    results = []
    
    # 测试 1: 引擎连接 (可选, 可能没有硬件)
    results.append(("引擎连接", test_engine_connection()))
    
    # 测试 2: 视觉流水线 (需要 YOLO 模型)
    results.append(("视觉流水线", test_vision_pipeline()))
    
    # 测试 3: Agent 生命周期 (纯软件)
    results.append(("Agent 生命周期", test_agent_lifecycle()))
    
    # 测试 4: 完整集成 (需要硬件)
    results.append(("完整集成", test_full_integration()))
    
    # 打印结果
    logger.info("\n=== 测试结果汇总 ===")
    for name, success in results:
        status = "✓ 通过" if success else "✗ 失败/跳过"
        logger.info(f"  {name}: {status}")
    
    # 统计
    passed = sum(1 for _, success in results if success)
    total = len(results)
    logger.info(f"\n总计: {passed}/{total} 通过")
    
    return passed == total


if __name__ == '__main__':
    success = run_integration_tests()
    sys.exit(0 if success else 1)

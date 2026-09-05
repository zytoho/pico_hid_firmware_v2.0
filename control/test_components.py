"""
组件单元测试
============
测试各个组件的独立功能
"""

import sys
import time
import unittest
import numpy as np
from unittest.mock import Mock, MagicMock, patch

# 导入组件
from engine_v2 import FrameCodec, PathGenerator, HumanMotionEngine, HIDKey, Modifier
from agent_v2 import PhysicalFatigueModel, BehaviorProfile, AnomalyDetector, MacroAgent, AgentState


class TestFrameCodec(unittest.TestCase):
    """测试帧编解码器"""
    
    def test_encode_simple(self):
        """测试简单命令编码"""
        frame = FrameCodec.encode('C', 1)
        # 期望: #C:1|XX\n (XX 是校验和)
        self.assertTrue(frame.startswith(b'#C:1|'))
        self.assertTrue(frame.endswith(b'\n'))
    
    def test_encode_multiple_args(self):
        """测试多参数编码"""
        frame = FrameCodec.encode('M', 100, 200)
        self.assertIn(b'#M:100,200|', frame)
    
    def test_checksum_calculation(self):
        """测试校验和计算"""
        frame = FrameCodec.encode('P', 0)
        # 提取校验和部分
        frame_str = frame.decode('ascii')
        # 格式: #P:0|XX\n
        checksum_str = frame_str.split('|')[1][:2]
        checksum = int(checksum_str, 16)
        
        # 手动计算校验和
        body = 'P:0'
        expected = sum(ord(c) for c in body) & 0xFF
        
        self.assertEqual(checksum, expected)
    
    def test_decode_ack_success(self):
        """测试 ACK 解码 (成功)"""
        ok, msg = FrameCodec.decode_ack(b'+A\n')
        self.assertTrue(ok)
        self.assertEqual(msg, 'A')
    
    def test_decode_ack_failure(self):
        """测试 ACK 解码 (失败)"""
        ok, msg = FrameCodec.decode_ack(b'-TIMEOUT\n')
        self.assertFalse(ok)
        self.assertEqual(msg, 'TIMEOUT')


class TestPathGenerator(unittest.TestCase):
    """测试路径生成器"""
    
    def test_generate_straight_line(self):
        """测试直线移动 (低疲劳高注意力)"""
        start = np.array([0.0, 0.0])
        end = np.array([100.0, 0.0])
        
        path = PathGenerator.generate(start, end, fatigue=0.0, focus=1.0)
        
        # 路径应该有多个点
        self.assertGreater(len(path), 10)
        # 起点应该接近 start
        self.assertLess(abs(path[0, 0] - 0), 10)
        self.assertLess(abs(path[0, 1] - 0), 10)
    
    def test_generate_with_fatigue(self):
        """测试疲劳对路径的影响"""
        start = np.array([0.0, 0.0])
        end = np.array([100.0, 100.0])
        
        # 低疲劳
        path_low = PathGenerator.generate(start, end, fatigue=0.0, focus=1.0)
        # 高疲劳
        path_high = PathGenerator.generate(start, end, fatigue=0.8, focus=0.3)
        
        # 高疲劳应该有更多步数 (更慢)
        self.assertGreater(len(path_high), len(path_low))
    
    def test_generate_short_distance(self):
        """测试短距离移动"""
        start = np.array([0.0, 0.0])
        end = np.array([2.0, 2.0])
        
        path = PathGenerator.generate(start, end, fatigue=0.0, focus=1.0)
        # 短距离应该有很少的步数
        self.assertLessEqual(len(path), 15)
    
    def test_generate_zero_distance(self):
        """测试零距离移动"""
        point = np.array([50.0, 50.0])
        path = PathGenerator.generate(point, point, fatigue=0.0, focus=1.0)
        # 应该返回单个点
        self.assertEqual(len(path), 1)


class TestPhysicalFatigueModel(unittest.TestCase):
    """测试物理疲劳模型"""
    
    def test_initial_state(self):
        """测试初始状态"""
        model = PhysicalFatigueModel()
        profile = model.evaluate()
        
        # 初始疲劳应该很低
        self.assertLess(profile.fatigue, 0.1)
        # 初始注意力应该很高
        self.assertGreater(profile.focus, 0.7)
    
    def test_fatigue_increase(self):
        """测试疲劳随时间增加"""
        model = PhysicalFatigueModel(fatigue_time_constant=1.0)  # 加速测试
        
        # 模拟时间流逝
        model.start_time = time.time() - 120  # 2分钟前开始
        profile1 = model.evaluate()
        
        model.start_time = time.time() - 240  # 4分钟前开始
        profile2 = model.evaluate()
        
        # 4分钟后的疲劳应该更高
        self.assertGreater(profile2.fatigue, profile1.fatigue)
    
    def test_action_interval_increases(self):
        """测试操作间隔随疲劳增加"""
        # 使用极短的时间常数让疲劳快速累积
        model = PhysicalFatigueModel(fatigue_time_constant=1.0)
        
        # 初始状态 (几乎无疲劳)
        model.start_time = time.time()
        profile_initial = model.evaluate()
        
        # 模拟 10 分钟后 (时间常数 1 分钟, 所以疲劳 ≈ 1.0)
        model.start_time = time.time() - 600  # 10分钟前
        profile_fatigued = model.evaluate()
        
        # 疲劳时操作间隔应该更长 (允许微小随机抖动, 用宽松阈值)
        self.assertGreater(profile_fatigued.action_interval, profile_initial.action_interval + 0.3)
    
    def test_micro_break_trigger(self):
        """测试微休息触发"""
        model = PhysicalFatigueModel(micro_break_probability=1.0)  # 100% 触发
        
        # 应该触发微休息
        duration = model.should_micro_break()
        self.assertIsNotNone(duration)
        self.assertGreater(duration, 0)


class TestAnomalyDetector(unittest.TestCase):
    """测试异常检测器"""
    
    def test_record_success(self):
        """测试记录成功"""
        detector = AnomalyDetector()
        detector.record_failure("test")
        self.assertEqual(detector.consecutive_failures, 1)
        
        detector.record_success()
        self.assertEqual(detector.consecutive_failures, 0)
    
    def test_consecutive_failures_trigger(self):
        """测试连续失败触发异常"""
        detector = AnomalyDetector(max_consecutive_failures=2)
        
        detector.record_failure("fail 1")
        event = detector.record_failure("fail 2")
        
        # 应该触发异常
        self.assertIsNotNone(event)
        self.assertEqual(event.anomaly_type.value, "stuck")
    
    def test_stuck_detection(self):
        """测试卡住检测"""
        detector = AnomalyDetector(stuck_timeout=0.5)
        detector.last_progress_time = time.time() - 1.0  # 1秒前
        
        event = detector.check_stuck()
        
        # 应该检测到卡住
        self.assertIsNotNone(event)


class TestBehaviorProfile(unittest.TestCase):
    """测试行为 Profile"""
    
    def test_derived_properties(self):
        """测试派生属性"""
        profile = BehaviorProfile(fatigue=0.5, focus=0.7, action_interval=1.5)
        
        # 测试点击延迟范围
        click_range = profile.click_delay_range
        self.assertEqual(len(click_range), 2)
        self.assertLess(click_range[0], click_range[1])
        
        # 测试移动速度因子
        speed_factor = profile.move_speed_factor
        self.assertGreater(speed_factor, 1.0)  # 疲劳时应该 > 1
        
        # 测试错误率
        error_rate = profile.error_rate
        self.assertGreaterEqual(error_rate, 0.0)
        self.assertLessEqual(error_rate, 0.1)


class TestMacroAgent(unittest.TestCase):
    """测试宏观 Agent"""
    
    def test_initialization(self):
        """测试初始化"""
        agent = MacroAgent()
        self.assertEqual(agent.state, AgentState.IDLE)
    
    def test_start_stop(self):
        """测试启动和停止"""
        agent = MacroAgent()
        agent.start()
        self.assertEqual(agent.state, AgentState.WORKING)
        
        time.sleep(0.2)
        agent.stop()
        self.assertEqual(agent.state, AgentState.IDLE)
    
    def test_log_action(self):
        """测试记录动作"""
        agent = MacroAgent()
        agent.fatigue_model.log_action = Mock()
        
        agent.log_action()
        agent.fatigue_model.log_action.assert_called_once()
    
    def test_get_profile_thread_safe(self):
        """测试线程安全的 Profile 获取"""
        agent = MacroAgent()
        agent.start()
        time.sleep(0.2)
        
        # 多次获取应该不报错
        for _ in range(10):
            profile = agent.get_profile()
            self.assertIsInstance(profile, BehaviorProfile)
        
        agent.stop()
    
    def test_get_status(self):
        """测试状态查询"""
        agent = MacroAgent()
        agent.start()
        time.sleep(0.2)
        
        status = agent.get_status()
        
        self.assertIn('state', status)
        self.assertIn('profile', status)
        self.assertIn('stats', status)
        
        agent.stop()


def run_all_tests():
    """运行所有测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加所有测试类
    suite.addTests(loader.loadTestsFromTestCase(TestFrameCodec))
    suite.addTests(loader.loadTestsFromTestCase(TestPathGenerator))
    suite.addTests(loader.loadTestsFromTestCase(TestPhysicalFatigueModel))
    suite.addTests(loader.loadTestsFromTestCase(TestAnomalyDetector))
    suite.addTests(loader.loadTestsFromTestCase(TestBehaviorProfile))
    suite.addTests(loader.loadTestsFromTestCase(TestMacroAgent))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)

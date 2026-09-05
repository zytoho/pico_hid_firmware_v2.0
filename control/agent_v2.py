"""
宏观 Agent 决策引擎 (v2 - 物理模型 + 异常检测)
================================================
核心改进:
- 物理疲劳/注意力模型替代 LLM 推理 (更快、更稳定)
- LLM 仅在异常场景介入 (验证码、弹窗、未知 UI 等)
- 微休息/走神模拟
- 任务状态机管理
- 可配置的行为 Profile
"""

import time
import math
import random
import threading
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable, Dict, Any, List

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# 状态定义
# ============================================================================

class AgentState(Enum):
    """Agent 运行状态"""
    IDLE = auto()           # 空闲/待命
    WORKING = auto()        # 正常工作
    MICRO_BREAK = auto()    # 微休息 (短暂停顿)
    DISTRACTED = auto()     # 走神/注意力漂移
    ANOMALY = auto()        # 异常状态 (需要 LLM 介入)
    PAUSED = auto()         # 手动暂停
    ERROR = auto()          # 错误状态


class AnomalyType(Enum):
    """异常类型"""
    CAPTCHA = "captcha"                 # 验证码
    UNEXPECTED_POPUP = "unexpected_popup"  # 意外弹窗
    UI_CHANGE = "ui_change"             # UI 变化 (布局不同)
    STUCK = "stuck"                     # 卡住 (长时间无进展)
    UNKNOWN_ELEMENT = "unknown_element" # 未知元素
    RATE_LIMIT = "rate_limit"           # 频率限制提示


# ============================================================================
# 配置与数据类
# ============================================================================

@dataclass
class BehaviorProfile:
    """行为特征配置 (可在运行时动态调整)"""
    fatigue: float = 0.0           # 疲劳度 0.0 ~ 1.0
    focus: float = 1.0             # 集中度 0.0 ~ 1.0
    action_interval: float = 1.0   # 操作停顿基础间隔 (秒)
    
    #  derived 参数 (根据 fatigue/focus 自动计算)
    @property
    def click_delay_range(self) -> tuple:
        """点击保持时间范围"""
        base = 0.06 + self.fatigue * 0.03
        jitter = 0.015 + (1.0 - self.focus) * 0.02
        return (max(0.03, base - jitter), base + jitter)
    
    @property
    def move_speed_factor(self) -> float:
        """移动速度因子 (1.0 = 正常, >1 = 慢)"""
        return 1.0 + self.fatigue * 0.6 + (1.0 - self.focus) * 0.3
    
    @property
    def error_rate(self) -> float:
        """模拟出错概率"""
        return max(0.0, self.fatigue * 0.05 + (1.0 - self.focus) * 0.03)


@dataclass
class AnomalyEvent:
    """异常事件"""
    anomaly_type: AnomalyType
    description: str
    screenshot_context: Optional[Any] = None  # 截图数据 (传给 LLM)
    timestamp: float = 0.0
    retry_count: int = 0
    max_retries: int = 3
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ============================================================================
# 物理疲劳模型
# ============================================================================

class PhysicalFatigueModel:
    """
    基于物理的疲劳/注意力模型
    
    疲劳曲线: 指数增长, 4 小时达到 ~85%
    注意力: 正弦波动 + 疲劳衰减
    微休息: 随机触发, 模拟人类走神
    """
    
    def __init__(
        self,
        fatigue_time_constant: float = 120.0,  # 疲劳时间常数 (分钟)
        focus_base: float = 0.85,              # 基础注意力水平
        focus_oscillation_period: float = 200.0, # 注意力波动周期 (秒)
        focus_oscillation_amplitude: float = 0.15, # 注意力波动幅度
        micro_break_probability: float = 0.02, # 每个评估周期的微休息概率
        micro_break_duration_range: tuple = (5.0, 20.0), # 微休息时长范围 (秒)
    ):
        self.fatigue_tc = fatigue_time_constant
        self.focus_base = focus_base
        self.focus_period = focus_oscillation_period
        self.focus_amplitude = focus_oscillation_amplitude
        self.mb_prob = micro_break_probability
        self.mb_duration = micro_break_duration_range
        
        self.start_time = time.time()
        self.last_eval_time = time.time()
        self.action_count_window = 0
        self.total_actions = 0
    
    def evaluate(self) -> BehaviorProfile:
        """
        评估当前状态, 返回 BehaviorProfile
        
        每 ~15 秒调用一次 (由 Agent 主循环控制)
        """
        now = time.time()
        elapsed_min = (now - self.start_time) / 60.0
        elapsed_sec = now - self.start_time
        
        # ---- 疲劳度 (指数增长) ----
        # fatigue = 1 - e^(-t/tau), 120 分钟后 ~63%, 240 分钟后 ~86%
        fatigue = 1.0 - math.exp(-elapsed_min / self.fatigue_tc)
        # 加入随机扰动
        fatigue += random.uniform(-0.03, 0.03)
        fatigue = max(0.0, min(0.95, fatigue))
        
        # ---- 集中度 (正弦波动 + 疲劳衰减) ----
        oscillation = self.focus_amplitude * math.sin(
            2 * math.pi * elapsed_sec / self.focus_period
        )
        # 额外加入低频漂移 (注意力 wandering)
        low_freq = 0.08 * math.sin(2 * math.pi * elapsed_sec / 600.0)
        
        focus = (
            self.focus_base
            - fatigue * 0.5  # 疲劳导致注意力下降
            + oscillation
            + low_freq
            + random.uniform(-0.05, 0.05)
        )
        focus = max(0.15, min(1.0, focus))
        
        # ---- 操作间隔 (随疲劳增加) ----
        action_interval = 1.0 + fatigue * 1.5 + (1.0 - focus) * 0.8
        action_interval += random.uniform(-0.2, 0.2)
        action_interval = max(0.4, action_interval)
        
        # 重置窗口计数
        self.action_count_window = 0
        self.last_eval_time = now
        
        return BehaviorProfile(
            fatigue=fatigue,
            focus=focus,
            action_interval=action_interval,
        )
    
    def should_micro_break(self) -> Optional[float]:
        """
        判断是否应该触发微休息
        
        Returns:
            休息时长 (秒), None 表示不休息
        """
        if random.random() < self.mb_prob:
            duration = random.uniform(*self.mb_duration)
            logger.info(f"[FatigueModel] 微休息触发: {duration:.1f}s")
            return duration
        return None
    
    def log_action(self):
        """记录一次动作"""
        self.action_count_window += 1
        self.total_actions += 1
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        elapsed_min = (time.time() - self.start_time) / 60.0
        return {
            "elapsed_minutes": round(elapsed_min, 1),
            "total_actions": self.total_actions,
            "actions_per_minute": round(
                self.total_actions / max(0.1, elapsed_min), 1
            ),
        }


# ============================================================================
# 异常检测器
# ============================================================================

class AnomalyDetector:
    """
    异常检测器
    
    监控视觉/操作反馈, 识别异常状态:
    - 验证码出现
    - 意外弹窗
    - UI 布局变化
    - 操作卡住 (长时间无进展)
    - 频率限制提示
    
    检测到异常时调用 LLM 进行智能处理
    """
    
    def __init__(
        self,
        stuck_timeout: float = 30.0,  # 多少秒无进展视为卡住
        max_consecutive_failures: int = 3,  # 连续失败次数阈值
        llm_callback: Optional[Callable] = None,  # LLM 异常处理回调
    ):
        self.stuck_timeout = stuck_timeout
        self.max_failures = max_consecutive_failures
        self.llm_callback = llm_callback
        
        # 状态追踪
        self.consecutive_failures = 0
        self.last_progress_time = time.time()
        self.last_task_state: Optional[str] = None
        self.anomaly_history: List[AnomalyEvent] = []
    
    def record_success(self):
        """记录成功操作"""
        self.consecutive_failures = 0
        self.last_progress_time = time.time()
    
    def record_failure(self, description: str = "") -> Optional[AnomalyEvent]:
        """
        记录失败操作
        
        Returns:
            如果触发异常, 返回 AnomalyEvent; 否则 None
        """
        self.consecutive_failures += 1
        
        if self.consecutive_failures >= self.max_failures:
            event = AnomalyEvent(
                anomaly_type=AnomalyType.STUCK,
                description=f"连续失败 {self.consecutive_failures} 次: {description}",
            )
            self._record_anomaly(event)
            return event
        
        return None
    
    def check_stuck(self) -> Optional[AnomalyEvent]:
        """检查是否卡住"""
        elapsed = time.time() - self.last_progress_time
        if elapsed > self.stuck_timeout:
            event = AnomalyEvent(
                anomaly_type=AnomalyType.STUCK,
                description=f"超过 {self.stuck_timeout}s 无进展",
            )
            self._record_anomaly(event)
            return event
        return None
    
    def report_anomaly(
        self,
        anomaly_type: AnomalyType,
        description: str,
        context: Optional[Any] = None,
    ) -> AnomalyEvent:
        """手动报告异常"""
        event = AnomalyEvent(
            anomaly_type=anomaly_type,
            description=description,
            screenshot_context=context,
        )
        self._record_anomaly(event)
        return event
    
    def _record_anomaly(self, event: AnomalyEvent):
        """记录异常并尝试 LLM 处理"""
        self.anomaly_history.append(event)
        logger.warning(
            f"[AnomalyDetector] 异常: {event.anomaly_type.value} - {event.description}"
        )
        
        # 调用 LLM 处理
        if self.llm_callback:
            try:
                result = self.llm_callback(event)
                logger.info(f"[AnomalyDetector] LLM 处理结果: {result}")
                if result and result.get("resolved"):
                    self.reset()
            except Exception as e:
                logger.error(f"[AnomalyDetector] LLM 处理失败: {e}")
    
    def reset(self):
        """重置异常状态"""
        self.consecutive_failures = 0
        self.last_progress_time = time.time()
    
    def get_recent_anomalies(self, count: int = 5) -> List[AnomalyEvent]:
        """获取最近的异常记录"""
        return self.anomaly_history[-count:]


# ============================================================================
# LLM 异常处理器 (仅在异常时调用)
# ============================================================================

class LLMAnomalyHandler:
    """
    LLM 异常处理器
    
    仅在以下场景被调用:
    1. 检测到验证码
    2. 意外弹窗/对话框
    3. UI 布局发生重大变化
    4. 操作卡住无法自动恢复
    5. 需要理解屏幕内容做决策
    
    平时不调用 LLM, 节省计算资源
    """
    
    def __init__(
        self,
        model_name: str = "mlx-community/Qwen2.5-7B-Instruct-4bit",
        use_mlx: bool = True,
    ):
        self.model_name = model_name
        self.use_mlx = use_mlx
        self.model = None
        self.tokenizer = None
        self._loaded = False
    
    def _ensure_loaded(self):
        """延迟加载模型 (首次异常时才加载)"""
        if self._loaded:
            return
        
        try:
            if self.use_mlx:
                from mlx_lm import load
                self.model, self.tokenizer = load(self.model_name)
            else:
                # Fallback: 使用 transformers
                from transformers import AutoModelForCausalLM, AutoTokenizer
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self.model = AutoModelForCausalLM.from_pretrained(self.model_name)
            
            self._loaded = True
            logger.info(f"[LLMHandler] 模型加载完成: {self.model_name}")
        except Exception as e:
            logger.error(f"[LLMHandler] 模型加载失败: {e}")
            raise
    
    def handle_anomaly(self, event: AnomalyEvent) -> Dict[str, Any]:
        """
        处理异常事件
        
        Returns:
            {
                "resolved": bool,      # 是否已解决
                "action": str,         # 建议的操作
                "confidence": float,   # 置信度
                "reasoning": str,      # 推理过程
            }
        """
        self._ensure_loaded()
        
        # 构建 prompt
        prompt = self._build_prompt(event)
        
        # 推理
        response = self._generate(prompt)
        
        # 解析响应
        result = self._parse_response(response)
        return result
    
    def _build_prompt(self, event: AnomalyEvent) -> str:
        """构建异常处理 prompt"""
        type_descriptions = {
            AnomalyType.CAPTCHA: "遇到了验证码，需要判断验证码类型并决定如何处理",
            AnomalyType.UNEXPECTED_POPUP: "出现了意外的弹窗/对话框，需要判断是否关闭或处理",
            AnomalyType.UI_CHANGE: "界面布局发生了变化，需要重新定位目标元素",
            AnomalyType.STUCK: "操作卡住，长时间无法完成当前任务",
            AnomalyType.UNKNOWN_ELEMENT: "遇到未知的界面元素",
            AnomalyType.RATE_LIMIT: "检测到频率限制提示",
        }
        
        desc = type_descriptions.get(
            event.anomaly_type, "遇到未知异常"
        )
        
        prompt = (
            "<|im_start|>system\n"
            "你是一个桌面自动化异常处理助手。分析以下异常情况并给出处理建议。\n"
            "输出 JSON 格式: {\"resolved\": bool, \"action\": str, \"confidence\": float, \"reasoning\": str}\n"
            "<|im_end|>\n"
            f"<|im_start|>user\n"
            f"异常类型: {event.anomaly_type.value}\n"
            f"情况描述: {desc}\n"
            f"详细信息: {event.description}\n"
            f"已重试次数: {event.retry_count}\n"
            f"<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        
        return prompt
    
    def _generate(self, prompt: str) -> str:
        """生成 LLM 响应"""
        try:
            if self.use_mlx:
                from mlx_lm import generate
                return generate(
                    self.model, self.tokenizer,
                    prompt=prompt, max_tokens=200, verbose=False
                )
            else:
                import torch
                inputs = self.tokenizer(prompt, return_tensors="pt")
                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs, max_new_tokens=200
                    )
                return self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        except Exception as e:
            logger.error(f"[LLMHandler] 推理失败: {e}")
            return '{"resolved": false, "action": "error", "confidence": 0.0, "reasoning": "' + str(e) + '"}'
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 响应"""
        import json
        
        default = {
            "resolved": False,
            "action": "skip",
            "confidence": 0.0,
            "reasoning": "parse_error",
        }
        
        try:
            # 尝试提取 JSON
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                parsed = json.loads(json_str)
                return {
                    "resolved": parsed.get("resolved", False),
                    "action": parsed.get("action", "skip"),
                    "confidence": parsed.get("confidence", 0.0),
                    "reasoning": parsed.get("reasoning", ""),
                }
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"[LLMHandler] 响应解析失败: {e}")
        
        return default


# ============================================================================
# 宏观 Agent 主类
# ============================================================================

class MacroAgent:
    """
    宏观 Agent 控制器
    
    职责:
    1. 维护行为 Profile (疲劳/注意力/间隔)
    2. 异常检测与处理
    3. 任务状态管理
    4. 微休息/走神调度
    """
    
    def __init__(
        self,
        fatigue_model: Optional[PhysicalFatigueModel] = None,
        anomaly_detector: Optional[AnomalyDetector] = None,
        llm_handler: Optional[LLMAnomalyHandler] = None,
        on_state_change: Optional[Callable[[AgentState], None]] = None,
    ):
        self.fatigue_model = fatigue_model or PhysicalFatigueModel()
        self.llm_handler = llm_handler or LLMAnomalyHandler()
        
        # 异常检测器: LLM 回调指向我们的处理器
        self.anomaly_detector = anomaly_detector or AnomalyDetector(
            llm_callback=self._on_anomaly_detected
        )
        
        self.on_state_change = on_state_change
        
        # 当前状态
        self.state = AgentState.IDLE
        self.profile = BehaviorProfile()
        
        # 线程控制
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # 统计
        self._eval_count = 0
        self._micro_break_count = 0
    
    def start(self):
        """启动 Agent 后台评估循环"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._evaluation_loop, daemon=True)
        self._thread.start()
        self._set_state(AgentState.WORKING)
        logger.info("[MacroAgent] 已启动")
    
    def stop(self):
        """停止 Agent"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self._set_state(AgentState.IDLE)
        logger.info("[MacroAgent] 已停止")
    
    def _evaluation_loop(self):
        """后台评估循环 (每 15 秒评估一次)"""
        while self._running:
            try:
                self._evaluate_cycle()
            except Exception as e:
                logger.error(f"[MacroAgent] 评估循环异常: {e}")
            
            # 等待 15 秒 (分段 sleep 以便快速响应 stop)
            for _ in range(150):
                if not self._running:
                    break
                time.sleep(0.1)
    
    def _evaluate_cycle(self):
        """单次评估周期"""
        self._eval_count += 1
        
        # 1. 物理模型评估
        with self._lock:
            self.profile = self.fatigue_model.evaluate()
        
        # 2. 检查是否需要微休息
        if self.state == AgentState.WORKING:
            break_duration = self.fatigue_model.should_micro_break()
            if break_duration:
                self._enter_micro_break(break_duration)
                return
        
        # 3. 检查是否卡住
        stuck_event = self.anomaly_detector.check_stuck()
        if stuck_event:
            self._set_state(AgentState.ANOMALY)
        
        # 4. 日志
        if self._eval_count % 4 == 0:  # 每分钟打印一次
            stats = self.fatigue_model.get_stats()
            logger.info(
                f"[MacroAgent] 状态: fatigue={self.profile.fatigue:.2f}, "
                f"focus={self.profile.focus:.2f}, "
                f"interval={self.profile.action_interval:.2f}s, "
                f"state={self.state.name}, "
                f"total_actions={stats['total_actions']}"
            )
    
    def _enter_micro_break(self, duration: float):
        """进入微休息状态"""
        self._micro_break_count += 1
        self._set_state(AgentState.MICRO_BREAK)
        logger.info(f"[MacroAgent] 微休息开始: {duration:.1f}s")
        
        time.sleep(duration)
        
        if self._running:
            self._set_state(AgentState.WORKING)
            logger.info("[MacroAgent] 微休息结束, 恢复工作")
    
    def _set_state(self, new_state: AgentState):
        """切换状态"""
        old_state = self.state
        self.state = new_state
        if old_state != new_state:
            logger.debug(f"[MacroAgent] 状态切换: {old_state.name} -> {new_state.name}")
            if self.on_state_change:
                try:
                    self.on_state_change(new_state)
                except Exception as e:
                    logger.error(f"[MacroAgent] 状态回调异常: {e}")
    
    def _on_anomaly_detected(self, event: AnomalyEvent) -> Dict[str, Any]:
        """异常检测回调 → 调用 LLM 处理"""
        self._set_state(AgentState.ANOMALY)
        
        try:
            result = self.llm_handler.handle_anomaly(event)
            if result.get("resolved"):
                self.anomaly_detector.reset()
                self._set_state(AgentState.WORKING)
            return result
        except Exception as e:
            logger.error(f"[MacroAgent] 异常处理失败: {e}")
            return {"resolved": False, "action": "skip", "confidence": 0.0}
    
    # ---- 对外接口 ----
    
    def get_profile(self) -> BehaviorProfile:
        """获取当前行为 Profile (线程安全)"""
        with self._lock:
            return BehaviorProfile(
                fatigue=self.profile.fatigue,
                focus=self.profile.focus,
                action_interval=self.profile.action_interval,
            )
    
    def log_action(self):
        """记录一次动作 (调用方在每次操作后调用)"""
        self.fatigue_model.log_action()
        self.anomaly_detector.record_success()
    
    def log_failure(self, description: str = ""):
        """记录失败操作"""
        event = self.anomaly_detector.record_failure(description)
        if event:
            self._set_state(AgentState.ANOMALY)
    
    def report_anomaly(
        self,
        anomaly_type: AnomalyType,
        description: str,
        context: Optional[Any] = None,
    ):
        """报告异常 (由视觉/操作模块调用)"""
        self.anomaly_detector.report_anomaly(anomaly_type, description, context)
    
    def pause(self):
        """手动暂停"""
        self._set_state(AgentState.PAUSED)
    
    def resume(self):
        """手动恢复"""
        if self.state == AgentState.PAUSED:
            self._set_state(AgentState.WORKING)
    
    def get_status(self) -> Dict[str, Any]:
        """获取完整状态信息"""
        with self._lock:
            return {
                "state": self.state.name,
                "profile": {
                    "fatigue": round(self.profile.fatigue, 3),
                    "focus": round(self.profile.focus, 3),
                    "action_interval": round(self.profile.action_interval, 3),
                },
                "stats": self.fatigue_model.get_stats(),
                "micro_breaks": self._micro_break_count,
                "evaluations": self._eval_count,
                "recent_anomalies": [
                    {
                        "type": e.anomaly_type.value,
                        "desc": e.description,
                        "time": time.strftime(
                            "%H:%M:%S", time.localtime(e.timestamp)
                        ),
                    }
                    for e in self.anomaly_detector.get_recent_anomalies(3)
                ],
            }


# ============================================================================
# 测试
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )
    
    print("=== 宏观 Agent 测试 (物理模型) ===\n")
    
    # 测试 1: 物理疲劳模型
    print("[测试 1] 物理疲劳模型模拟")
    model = PhysicalFatigueModel(fatigue_time_constant=2.0)  # 加速: 2分钟=63%
    
    for i in range(10):
        profile = model.evaluate()
        print(
            f"  周期 {i+1}: fatigue={profile.fatigue:.3f}, "
            f"focus={profile.focus:.3f}, "
            f"interval={profile.action_interval:.3f}s"
        )
        model.log_action()
        time.sleep(0.5)  # 加速模拟
    
    # 测试 2: 异常检测
    print("\n[测试 2] 异常检测")
    detector = AnomalyDetector(stuck_timeout=2.0, max_consecutive_failures=2)
    
    detector.record_success()
    print("  记录成功 ✓")
    
    detector.record_failure("第一次失败")
    print("  记录失败 1")
    
    event = detector.record_failure("第二次失败")
    if event:
        print(f"  触发异常: {event.anomaly_type.value} - {event.description}")
    
    # 测试 3: Agent 状态
    print("\n[测试 3] Agent 状态管理")
    agent = MacroAgent()
    agent.start()
    time.sleep(1)
    
    status = agent.get_status()
    print(f"  Agent 状态: {status['state']}")
    print(f"  Profile: {status['profile']}")
    
    agent.log_action()
    agent.log_action()
    agent.log_action()
    
    status = agent.get_status()
    print(f"  操作后 stats: {status['stats']}")
    
    agent.stop()
    print("\n=== 测试完成 ===")

"""
视觉闭环 Pipeline
- MSS 高速截图 (捕获 Moonlight 窗口)
- YOLOv8 目标检测/定位
- 坐标系统转换 (屏幕坐标 → Pico 绝对坐标)
"""

import time
import threading
import numpy as np
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
import mss
import mss.tools
import cv2
from ultralytics import YOLO


@dataclass
class Detection:
    """目标检测结果"""
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    center: Tuple[int, int]          # 中心点坐标


class VisionPipeline:
    """视觉处理流水线"""
    
    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        window_title: str = "Moonlight",
        target_region: Optional[Tuple[int, int, int, int]] = None,
        fps_limit: int = 30
    ):
        """
        初始化视觉流水线
        
        Args:
            model_path: YOLO 模型路径
            window_title: Moonlight 窗口标题 (用于定位截图区域)
            target_region: 自定义截图区域 (x, y, width, height)，None 则自动检测窗口
            fps_limit: 帧率上限
        """
        self.model = YOLO(model_path)
        self.window_title = window_title
        self.target_region = target_region
        self.fps_limit = fps_limit
        
        # 屏幕坐标系统 (Pico 维护的虚拟坐标系)
        self.screen_width = 0
        self.screen_height = 0
        self.capture_region = None  # 实际截图区域
        
        # 检测结果缓存
        self._detections: List[Detection] = []
        self._last_frame: Optional[np.ndarray] = None
        self._last_inference_time = 0.0
        
        # 性能统计
        self.fps_counter = 0
        self.fps_time = time.time()
        self.current_fps = 0.0
        
        # 初始化截图区域
        self._init_capture_region()
        
    def _init_capture_region(self):
        """初始化截图区域"""
        if self.target_region:
            # 使用用户指定的区域
            self.capture_region = {
                "left": self.target_region[0],
                "top": self.target_region[1],
                "width": self.target_region[2],
                "height": self.target_region[3]
            }
        else:
            # 自动检测 Moonlight 窗口 (简化版: 使用全屏)
            # TODO: 实际场景应该用 pygetwindow 或类似库定位窗口
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # 主显示器
                self.capture_region = {
                    "left": monitor["left"],
                    "top": monitor["top"],
                    "width": monitor["width"],
                    "height": monitor["height"]
                }
        
        self.screen_width = self.capture_region["width"]
        self.screen_height = self.capture_region["height"]
        print(f"[Vision] 截图区域: {self.capture_region}")
        print(f"[Vision] 屏幕分辨率: {self.screen_width}x{self.screen_height}")
    
    def capture_frame(self) -> Optional[np.ndarray]:
        """截取一帧"""
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(self.capture_region)
                # 转换为 numpy array (BGRA → BGR)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                self._last_frame = frame
                return frame
        except Exception as e:
            print(f"[Vision] 截图失败: {e}")
            return None
    
    def detect(
        self,
        frame: Optional[np.ndarray] = None,
        conf_threshold: float = 0.5
    ) -> List[Detection]:
        """
        执行目标检测
        
        Args:
            frame: 输入帧，None 则自动截取
            conf_threshold: 置信度阈值
        
        Returns:
            检测结果列表
        """
        if frame is None:
            frame = self.capture_frame()
        
        if frame is None:
            return []
        
        # FPS 限制
        now = time.time()
        elapsed = now - self._last_inference_time
        if elapsed < (1.0 / self.fps_limit):
            # 未到帧率上限，返回上次结果
            return self._detections
        
        self._last_inference_time = now
        
        # YOLO 推理
        results = self.model(frame, conf=conf_threshold, verbose=False)
        
        # 解析结果
        detections = []
        for result in results:
            boxes = result.boxes
            for i in range(len(boxes)):
                # 边界框 (xyxy 格式)
                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
                # 中心点
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                # 类别和置信度
                cls_id = int(boxes.cls[i].cpu().numpy())
                cls_name = self.model.names[cls_id]
                conf = float(boxes.conf[i].cpu().numpy())
                
                detections.append(Detection(
                    class_id=cls_id,
                    class_name=cls_name,
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                    center=(cx, cy)
                ))
        
        self._detections = detections
        
        # FPS 统计
        self.fps_counter += 1
        if now - self.fps_time >= 1.0:
            self.current_fps = self.fps_counter / (now - self.fps_time)
            self.fps_counter = 0
            self.fps_time = now
        
        return detections
    
    def find_target(
        self,
        class_name: Optional[str] = None,
        class_id: Optional[int] = None,
        conf_threshold: float = 0.5
    ) -> Optional[Detection]:
        """
        查找特定目标 (返回置信度最高的)
        
        Args:
            class_name: 类别名称 (如 "person", "car")
            class_id: 类别 ID
            conf_threshold: 置信度阈值
        
        Returns:
            匹配的目标，None 表示未找到
        """
        detections = self.detect(conf_threshold=conf_threshold)
        
        if not detections:
            return None
        
        # 筛选匹配的类别
        candidates = []
        for det in detections:
            if class_name and det.class_name != class_name:
                continue
            if class_id is not None and det.class_id != class_id:
                continue
            candidates.append(det)
        
        if not candidates:
            return None
        
        # 返回置信度最高的
        return max(candidates, key=lambda d: d.confidence)
    
    def get_target_center(
        self,
        class_name: Optional[str] = None,
        class_id: Optional[int] = None
    ) -> Optional[Tuple[int, int]]:
        """
        获取目标中心点坐标 (屏幕坐标系)
        
        Returns:
            (x, y) 中心点坐标，None 表示未找到
        """
        target = self.find_target(class_name=class_name, class_id=class_id)
        if target:
            return target.center
        return None
    
    def screen_to_pico_coords(
        self,
        screen_x: int,
        screen_y: int
    ) -> Tuple[int, int]:
        """
        屏幕坐标 → Pico 绝对坐标
        
        注意: 当前假设 Pico 坐标系与屏幕坐标系一致
        如果有偏移/缩放，需要在这里做变换
        
        Args:
            screen_x: 屏幕 X 坐标
            screen_y: 屏幕 Y 坐标
        
        Returns:
            (pico_x, pico_y) Pico 坐标系
        """
        # TODO: 如果 Pico 坐标系与屏幕不一致，在这里做变换
        # 例如: 缩放、平移、旋转等
        
        # 当前实现: 1:1 映射
        return (screen_x, screen_y)
    
    def get_last_frame(self) -> Optional[np.ndarray]:
        """获取最后一帧 (用于可视化/调试)"""
        return self._last_frame
    
    def draw_detections(
        self,
        frame: Optional[np.ndarray] = None,
        detections: Optional[List[Detection]] = None
    ) -> np.ndarray:
        """
        在帧上绘制检测结果 (用于调试/可视化)
        
        Args:
            frame: 输入帧，None 则使用最后一帧
            detections: 检测结果，None 则使用缓存
        
        Returns:
            标注后的帧
        """
        if frame is None:
            frame = self._last_frame
        
        if frame is None:
            return None
        
        if detections is None:
            detections = self._detections
        
        # 复制帧避免修改原图
        annotated = frame.copy()
        
        # 绘制每个检测
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            cx, cy = det.center
            
            # 边界框
            color = (0, 255, 0)  # 绿色
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            
            # 标签
            label = f"{det.class_name} {det.confidence:.2f}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(
                annotated,
                (x1, y1 - label_size[1] - 10),
                (x1 + label_size[0], y1),
                color,
                -1
            )
            cv2.putText(
                annotated,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),
                2
            )
            
            # 中心点
            cv2.circle(annotated, (cx, cy), 5, (0, 0, 255), -1)
        
        # FPS 显示
        fps_text = f"FPS: {self.current_fps:.1f}"
        cv2.putText(
            annotated,
            fps_text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            2
        )
        
        return annotated


class ContinuousVisionThread(threading.Thread):
    """
    连续视觉处理线程 (后台运行)
    适合需要持续追踪目标的场景
    """
    
    def __init__(
        self,
        vision: VisionPipeline,
        target_class: Optional[str] = None,
        callback=None
    ):
        """
        Args:
            vision: VisionPipeline 实例
            target_class: 追踪的目标类别
            callback: 每次检测到目标时的回调函数 callback(Detection)
        """
        super().__init__(daemon=True)
        self.vision = vision
        self.target_class = target_class
        self.callback = callback
        
        self.running = False
        self.latest_target: Optional[Detection] = None
        self.lock = threading.Lock()
    
    def run(self):
        """主循环"""
        self.running = True
        print(f"[VisionThread] 开始追踪目标: {self.target_class or 'ALL'}")
        
        while self.running:
            target = self.vision.find_target(class_name=self.target_class)
            
            with self.lock:
                self.latest_target = target
            
            if target and self.callback:
                try:
                    self.callback(target)
                except Exception as e:
                    print(f"[VisionThread] 回调异常: {e}")
            
            # 帧率控制
            time.sleep(1.0 / self.vision.fps_limit)
    
    def stop(self):
        """停止线程"""
        self.running = False
        self.join(timeout=1.0)
    
    def get_latest_target(self) -> Optional[Detection]:
        """获取最新检测到的目标"""
        with self.lock:
            return self.latest_target


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    print("=== 视觉流水线测试 ===")
    
    # 初始化 (使用默认 YOLOv8n 模型)
    vision = VisionPipeline(
        model_path="yolov8n.pt",
        fps_limit=30
    )
    
    # 单次检测测试
    print("\n[测试 1] 单次检测")
    detections = vision.detect()
    print(f"检测到 {len(detections)} 个目标:")
    for det in detections[:5]:  # 只显示前 5 个
        print(f"  - {det.class_name} (conf={det.confidence:.2f}) at {det.center}")
    
    # 连续追踪测试
    print("\n[测试 2] 连续追踪 (按 Ctrl+C 停止)")
    
    def on_target_detected(det: Detection):
        print(f"  追踪到: {det.class_name} at {det.center}")
    
    tracker = ContinuousVisionThread(
        vision=vision,
        target_class="person",  # 追踪人
        callback=on_target_detected
    )
    tracker.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止追踪...")
        tracker.stop()
    
    print("测试完成")

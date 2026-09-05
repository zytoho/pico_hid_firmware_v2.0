"""
游戏视觉模块
============
集成 MSS 截图 + YOLO 推理，实现：
- 怪物识别（普通怪、精英怪、BOSS）
- 掉落物识别
- 人物与怪物距离计算
- 血量/蓝量检测
- 自动决策（攻击 vs 拾取）

使用方法:
    from game_vision import GameVision
    
    gv = GameVision(model_path='game_yolo.pt')
    gv.analyze_frame()
    
    # 获取最近怪物
    monster = gv.get_nearest_monster()
    if monster:
        print(f"距离: {monster.distance}像素")
        # 移动到怪物并攻击
        engine.move_to(monster.attack_point[0], monster.attack_point[1])
        engine.click()
    
    # 检查血量
    hp = gv.get_hp_percent()
    if hp < 30:
        # 按补血快捷键
        engine.press_key(KEY_1)
"""

import time
import math
import cv2
import numpy as np
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass, field
from enum import Enum
import mss
import mss.tools


class EntityType(Enum):
    """实体类型"""
    NORMAL_MONSTER = "normal_monster"      # 普通怪
    ELITE_MONSTER = "elite_monster"        # 精英怪
    BOSS = "boss"                          # BOSS
    LOOT = "loot"                          # 掉落物
    PLAYER = "player"                      # 玩家角色
    NPC = "npc"                            # NPC


@dataclass
class GameEntity:
    """游戏实体"""
    entity_type: EntityType
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]        # (x1, y1, x2, y2)
    center: Tuple[int, int]                # 中心点
    distance: float = 0.0                  # 与玩家的距离（像素）
    attack_point: Tuple[int, int] = None   # 攻击点（边界框底部中心）
    
    def __post_init__(self):
        if self.attack_point is None:
            # 攻击点默认为边界框底部中心
            x1, y1, x2, y2 = self.bbox
            self.attack_point = ((x1 + x2) // 2, y2)


@dataclass
class HealthInfo:
    """血量/蓝量信息"""
    hp_percent: float = 100.0              # 血量百分比
    mp_percent: float = 100.0              # 蓝量百分比
    hp_low: bool = False                   # 是否低血量
    mp_low: bool = False                   # 是否低蓝量
    
    # 阈值配置
    hp_threshold: float = 30.0             # 低血量阈值
    mp_threshold: float = 20.0             # 低蓝量阈值


class GameVision:
    """游戏视觉系统"""
    
    def __init__(
        self,
        model_path: str = 'game_yolo.pt',
        capture_region: Optional[Tuple[int, int, int, int]] = None,
        fps_limit: int = 30,
        hp_region: Optional[Tuple[int, int, int, int]] = None,
        mp_region: Optional[Tuple[int, int, int, int]] = None,
        player_position: Optional[Tuple[int, int]] = None
    ):
        """
        初始化游戏视觉系统
        
        Args:
            model_path: YOLO 模型路径（需要训练好的游戏专用模型）
            capture_region: 截图区域 (x, y, width, height)，None 则全屏
            fps_limit: 帧率限制
            hp_region: 血条区域 (x, y, width, height)
            mp_region: 蓝条区域 (x, y, width, height)
            player_position: 玩家角色在屏幕上的固定位置 (x, y)
        """
        # 延迟加载 YOLO 模型
        self.model_path = model_path
        self.model = None
        
        self.capture_region = capture_region
        self.fps_limit = fps_limit
        
        # UI 区域配置
        self.hp_region = hp_region
        self.mp_region = mp_region
        
        # 玩家位置（如果游戏角色固定在屏幕某个位置）
        self.player_position = player_position
        
        # 检测结果
        self.entities: List[GameEntity] = []
        self.health_info = HealthInfo()
        self.last_frame: Optional[np.ndarray] = None
        
        # 性能统计
        self.fps_counter = 0
        self.fps_time = time.time()
        self.current_fps = 0.0
        
        # 类别映射（需要根据实际训练的模型调整）
        self.class_mapping = {
            'normal_monster': EntityType.NORMAL_MONSTER,
            'elite_monster': EntityType.ELITE_MONSTER,
            'boss': EntityType.BOSS,
            'loot': EntityType.LOOT,
            'player': EntityType.PLAYER,
            'npc': EntityType.NPC,
        }
        
        print(f"[GameVision] 初始化完成")
        print(f"[GameVision] 模型: {model_path}")
    
    def _load_model(self):
        """延迟加载 YOLO 模型"""
        if self.model is None:
            try:
                from ultralytics import YOLO
                self.model = YOLO(self.model_path)
                print(f"[GameVision] 模型加载成功: {self.model_path}")
            except Exception as e:
                print(f"[GameVision] 模型加载失败: {e}")
                print(f"[GameVision] 请确保已训练游戏专用 YOLO 模型")
                raise
    
    def capture_frame(self) -> Optional[np.ndarray]:
        """截取游戏画面"""
        try:
            with mss.mss() as sct:
                if self.capture_region:
                    monitor = {
                        "left": self.capture_region[0],
                        "top": self.capture_region[1],
                        "width": self.capture_region[2],
                        "height": self.capture_region[3]
                    }
                else:
                    monitor = sct.monitors[1]  # 主显示器
                
                screenshot = sct.grab(monitor)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                self.last_frame = frame
                return frame
        except Exception as e:
            print(f"[GameVision] 截图失败: {e}")
            return None
    
    def detect_entities(
        self,
        frame: Optional[np.ndarray] = None,
        conf_threshold: float = 0.5
    ) -> List[GameEntity]:
        """
        检测游戏实体
        
        Args:
            frame: 输入帧，None 则自动截取
            conf_threshold: 置信度阈值
        
        Returns:
            检测到的实体列表
        """
        self._load_model()
        
        if frame is None:
            frame = self.capture_frame()
        
        if frame is None:
            return []
        
        # YOLO 推理
        results = self.model(frame, conf=conf_threshold, verbose=False)
        
        entities = []
        for result in results:
            boxes = result.boxes
            for i in range(len(boxes)):
                # 边界框
                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                
                # 类别
                cls_id = int(boxes.cls[i].cpu().numpy())
                cls_name = self.model.names[cls_id]
                conf = float(boxes.conf[i].cpu().numpy())
                
                # 映射到实体类型
                entity_type = self.class_mapping.get(cls_name, EntityType.NORMAL_MONSTER)
                
                # 计算距离
                distance = self._calculate_distance(cx, cy)
                
                entity = GameEntity(
                    entity_type=entity_type,
                    class_name=cls_name,
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                    center=(cx, cy),
                    distance=distance
                )
                entities.append(entity)
        
        self.entities = entities
        
        # FPS 统计
        self.fps_counter += 1
        now = time.time()
        if now - self.fps_time >= 1.0:
            self.current_fps = self.fps_counter / (now - self.fps_time)
            self.fps_counter = 0
            self.fps_time = now
        
        return entities
    
    def _calculate_distance(self, entity_x: int, entity_y: int) -> float:
        """
        计算实体与玩家的距离（像素）
        
        Args:
            entity_x: 实体 X 坐标
            entity_y: 实体 Y 坐标
        
        Returns:
            距离（像素）
        """
        if self.player_position:
            px, py = self.player_position
        else:
            # 默认玩家位置为屏幕中心
            if self.last_frame is not None:
                h, w = self.last_frame.shape[:2]
                px, py = w // 2, h // 2
            else:
                px, py = 960, 540  # 假设 1920x1080
        
        return math.sqrt((entity_x - px) ** 2 + (entity_y - py) ** 2)
    
    def detect_health(self, frame: Optional[np.ndarray] = None) -> HealthInfo:
        """
        检测血量和蓝量
        
        通过识别 UI 上的血条和蓝条区域，计算百分比
        
        Args:
            frame: 输入帧，None 则自动截取
        
        Returns:
            血量蓝量信息
        """
        if frame is None:
            frame = self.capture_frame()
        
        if frame is None:
            return self.health_info
        
        # 检测血量
        if self.hp_region:
            self.health_info.hp_percent = self._calculate_bar_percent(
                frame, self.hp_region, color_range='red'
            )
            self.health_info.hp_low = self.health_info.hp_percent < self.health_info.hp_threshold
        
        # 检测蓝量
        if self.mp_region:
            self.health_info.mp_percent = self._calculate_bar_percent(
                frame, self.mp_region, color_range='blue'
            )
            self.health_info.mp_low = self.health_info.mp_percent < self.health_info.mp_threshold
        
        return self.health_info
    
    def _calculate_bar_percent(
        self,
        frame: np.ndarray,
        region: Tuple[int, int, int, int],
        color_range: str = 'red'
    ) -> float:
        """
        计算血条/蓝条的百分比
        
        Args:
            frame: 图像帧
            region: 区域 (x, y, width, height)
            color_range: 颜色范围 ('red' 或 'blue')
        
        Returns:
            百分比 (0-100)
        """
        x, y, w, h = region
        
        # 裁剪区域
        roi = frame[y:y+h, x:x+w]
        
        # 转换到 HSV 颜色空间
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        # 根据颜色范围创建掩码
        if color_range == 'red':
            # 红色范围（血条）
            lower = np.array([0, 70, 50])
            upper = np.array([10, 255, 255])
            mask1 = cv2.inRange(hsv, lower, upper)
            
            lower = np.array([170, 70, 50])
            upper = np.array([180, 255, 255])
            mask2 = cv2.inRange(hsv, lower, upper)
            
            mask = cv2.bitwise_or(mask1, mask2)
        
        elif color_range == 'blue':
            # 蓝色范围（蓝条）
            lower = np.array([100, 70, 50])
            upper = np.array([130, 255, 255])
            mask = cv2.inRange(hsv, lower, upper)
        
        else:
            return 0.0
        
        # 计算填充比例
        total_pixels = w * h
        filled_pixels = cv2.countNonZero(mask)
        
        # 从左到右扫描，找到填充的边界
        # 假设血条是从左到右填充的
        col_sums = np.sum(mask, axis=0)
        
        # 找到最后一个非零列
        non_zero_cols = np.where(col_sums > 0)[0]
        if len(non_zero_cols) == 0:
            return 0.0
        
        last_filled_col = non_zero_cols[-1]
        percent = (last_filled_col + 1) / w * 100
        
        return min(100.0, max(0.0, percent))
    
    def analyze_frame(
        self,
        frame: Optional[np.ndarray] = None,
        conf_threshold: float = 0.5
    ) -> Dict:
        """
        分析一帧，返回完整的战斗信息
        
        Args:
            frame: 输入帧
            conf_threshold: 置信度阈值
        
        Returns:
            分析结果字典
        """
        if frame is None:
            frame = self.capture_frame()
        
        if frame is None:
            return {'error': '截图失败'}
        
        # 检测实体
        entities = self.detect_entities(frame, conf_threshold)
        
        # 检测血量蓝量
        health = self.detect_health(frame)
        
        # 分类实体
        monsters = [e for e in entities if e.entity_type in 
                   [EntityType.NORMAL_MONSTER, EntityType.ELITE_MONSTER, EntityType.BOSS]]
        loots = [e for e in entities if e.entity_type == EntityType.LOOT]
        
        # 按距离排序怪物
        monsters.sort(key=lambda e: e.distance)
        
        # 按距离排序掉落物
        loots.sort(key=lambda e: e.distance)
        
        # 决策：攻击还是拾取
        decision = self.make_decision(monsters, loots, health)
        
        return {
            'monsters': monsters,
            'loots': loots,
            'health': health,
            'decision': decision,
            'fps': self.current_fps
        }
    
    def make_decision(
        self,
        monsters: List[GameEntity],
        loots: List[GameEntity],
        health: HealthInfo
    ) -> Dict:
        """
        决策逻辑：攻击怪物还是拾取掉落物
        
        优先级：
        1. 血量低 → 补血
        2. 蓝量低 → 补蓝
        3. 有掉落物且近 → 拾取
        4. 有怪物 → 攻击（优先 BOSS > 精英 > 普通）
        
        Args:
            monsters: 怪物列表
            loots: 掉落物列表
            health: 血量蓝量信息
        
        Returns:
            决策结果
        """
        decision = {
            'action': 'idle',
            'target': None,
            'reason': ''
        }
        
        # 1. 检查是否需要补血
        if health.hp_low:
            decision['action'] = 'heal_hp'
            decision['reason'] = f'血量低 ({health.hp_percent:.1f}%)'
            return decision
        
        # 2. 检查是否需要补蓝
        if health.mp_low:
            decision['action'] = 'heal_mp'
            decision['reason'] = f'蓝量低 ({health.mp_percent:.1f}%)'
            return decision
        
        # 3. 检查是否有近处掉落物
        if loots:
            nearest_loot = loots[0]
            if nearest_loot.distance < 200:  # 200 像素内
                decision['action'] = 'pickup'
                decision['target'] = nearest_loot
                decision['reason'] = f'拾取掉落物 (距离 {nearest_loot.distance:.0f}px)'
                return decision
        
        # 4. 检查是否有怪物可攻击
        if monsters:
            # 优先攻击 BOSS > 精英 > 普通
            boss = next((m for m in monsters if m.entity_type == EntityType.BOSS), None)
            elite = next((m for m in monsters if m.entity_type == EntityType.ELITE_MONSTER), None)
            normal = next((m for m in monsters if m.entity_type == EntityType.NORMAL_MONSTER), None)
            
            target = boss or elite or normal
            
            if target:
                decision['action'] = 'attack'
                decision['target'] = target
                decision['reason'] = f'攻击 {target.class_name} (距离 {target.distance:.0f}px)'
                return decision
        
        # 5. 无事可做
        decision['action'] = 'idle'
        decision['reason'] = '无目标'
        
        return decision
    
    def get_nearest_monster(self) -> Optional[GameEntity]:
        """获取最近的怪物"""
        monsters = [e for e in self.entities if e.entity_type in 
                   [EntityType.NORMAL_MONSTER, EntityType.ELITE_MONSTER, EntityType.BOSS]]
        
        if not monsters:
            return None
        
        return min(monsters, key=lambda e: e.distance)
    
    def get_nearest_loot(self) -> Optional[GameEntity]:
        """获取最近的掉落物"""
        loots = [e for e in self.entities if e.entity_type == EntityType.LOOT]
        
        if not loots:
            return None
        
        return min(loots, key=lambda e: e.distance)
    
    def get_hp_percent(self) -> float:
        """获取当前血量百分比"""
        return self.health_info.hp_percent
    
    def get_mp_percent(self) -> float:
        """获取当前蓝量百分比"""
        return self.health_info.mp_percent
    
    def draw_debug_info(self, frame: Optional[np.ndarray] = None) -> np.ndarray:
        """
        在帧上绘制调试信息
        
        Args:
            frame: 输入帧，None 则使用最后一帧
        
        Returns:
            标注后的帧
        """
        if frame is None:
            frame = self.last_frame
        
        if frame is None:
            return None
        
        annotated = frame.copy()
        
        # 绘制实体
        for entity in self.entities:
            x1, y1, x2, y2 = entity.bbox
            cx, cy = entity.center
            
            # 根据类型选择颜色
            if entity.entity_type == EntityType.BOSS:
                color = (0, 0, 255)  # 红色
            elif entity.entity_type == EntityType.ELITE_MONSTER:
                color = (0, 165, 255)  # 橙色
            elif entity.entity_type == EntityType.NORMAL_MONSTER:
                color = (0, 255, 255)  # 黄色
            elif entity.entity_type == EntityType.LOOT:
                color = (0, 255, 0)  # 绿色
            else:
                color = (255, 255, 255)  # 白色
            
            # 边界框
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            
            # 标签
            label = f"{entity.class_name} {entity.confidence:.2f}"
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
            
            # 距离标注
            dist_text = f"{entity.distance:.0f}px"
            cv2.putText(
                annotated,
                dist_text,
                (x1, y2 + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2
            )
        
        # 绘制玩家位置
        if self.player_position:
            px, py = self.player_position
            cv2.circle(annotated, (px, py), 10, (255, 0, 255), -1)
            cv2.putText(
                annotated,
                "Player",
                (px + 15, py),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 255),
                2
            )
        
        # 绘制血量蓝量
        hp_text = f"HP: {self.health_info.hp_percent:.1f}%"
        mp_text = f"MP: {self.health_info.mp_percent:.1f}%"
        
        cv2.putText(
            annotated,
            hp_text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255) if self.health_info.hp_low else (0, 255, 0),
            2
        )
        cv2.putText(
            annotated,
            mp_text,
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 0, 0) if self.health_info.mp_low else (0, 255, 255),
            2
        )
        
        # FPS
        fps_text = f"FPS: {self.current_fps:.1f}"
        cv2.putText(
            annotated,
            fps_text,
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 0),
            2
        )
        
        return annotated


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    print("=== 游戏视觉系统测试 ===")
    print("\n注意: 需要先训练游戏专用的 YOLO 模型")
    print("模型需要识别以下类别:")
    print("  - normal_monster: 普通怪")
    print("  - elite_monster: 精英怪")
    print("  - boss: BOSS")
    print("  - loot: 掉落物")
    print("  - player: 玩家角色")
    
    # 配置示例
    config = {
        'model_path': 'game_yolo.pt',
        'capture_region': (0, 0, 1920, 1080),
        'player_position': (960, 540),  # 玩家固定在屏幕中心
        'hp_region': (50, 50, 200, 20),  # 血条区域
        'mp_region': (50, 80, 200, 20),  # 蓝条区域
    }
    
    print(f"\n配置:")
    for k, v in config.items():
        print(f"  {k}: {v}")
    
    # 初始化（会尝试加载模型）
    try:
        gv = GameVision(**config)
        
        # 测试截图
        print("\n[测试] 截图...")
        frame = gv.capture_frame()
        if frame is not None:
            print(f"  截图成功: {frame.shape}")
            
            # 测试血量检测
            print("\n[测试] 血量蓝量检测...")
            health = gv.detect_health(frame)
            print(f"  HP: {health.hp_percent:.1f}%")
            print(f"  MP: {health.mp_percent:.1f}%")
            
            # 测试实体检测（需要模型）
            print("\n[测试] 实体检测...")
            try:
                analysis = gv.analyze_frame(frame)
                print(f"  怪物数量: {len(analysis['monsters'])}")
                print(f"  掉落物数量: {len(analysis['loots'])}")
                print(f"  决策: {analysis['decision']['action']}")
                print(f"  原因: {analysis['decision']['reason']}")
                
                # 绘制调试信息
                debug_frame = gv.draw_debug_info(frame)
                if debug_frame is not None:
                    cv2.imwrite('debug_output.jpg', debug_frame)
                    print(f"  调试图已保存: debug_output.jpg")
            
            except Exception as e:
                print(f"  实体检测失败 (需要模型): {e}")
        
        print("\n✓ 基础功能测试完成")
        print("\n下一步:")
        print("  1. 收集游戏截图数据")
        print("  2. 标注怪物、掉落物等目标")
        print("  3. 训练 YOLO 模型")
        print("  4. 使用训练好的模型运行本模块")
    
    except Exception as e:
        print(f"\n✗ 初始化失败: {e}")

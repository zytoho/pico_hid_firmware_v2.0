# 游戏自动化战斗系统使用指南

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                  MacBook Pro (控制端)                     │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │           game_agent.py (战斗决策层)               │  │
│  │  - 优先攻击 BOSS > 精英 > 普通怪                   │  │
│  │  - 自动拾取掉落物                                  │  │
│  │  - 自动补血补蓝                                    │  │
│  └─────────────┬────────────────────────────────────┘  │
│                │                                         │
│  ┌─────────────▼────────────────────────────────────┐  │
│  │         game_vision.py (视觉识别层)                │  │
│  │  - MSS 高速截图 (30+ FPS)                          │  │
│  │  - YOLO 目标检测 (怪物/掉落物/NPC)                 │  │
│  │  - 血量蓝量识别 (颜色特征)                         │  │
│  │  - 距离计算 (玩家 → 目标)                          │  │
│  └─────────────┬────────────────────────────────────┘  │
│                │                                         │
│  ┌─────────────▼────────────────────────────────────┐  │
│  │         engine_v2.py (硬件控制层)                  │  │
│  │  - 贝塞尔曲线拟人轨迹                              │  │
│  │  - 帧协议封装 (#CMD:ARGS|XX\n)                     │  │
│  │  - 串口通信 (115200 baud)                          │  │
│  └─────────────┬────────────────────────────────────┘  │
│                │ USB-to-TTL                              │
└────────────────┼─────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│           Raspberry Pi Pico (执行端)                      │
│  - UART 中断接收                                         │
│  - HID 报告生成                                          │
│  - TinyUSB 驱动                                          │
└─────────────┬───────────────────────────────────────────┘
              │ USB HID
              ▼
┌─────────────────────────────────────────────────────────┐
│              Windows Host (游戏端)                        │
│  - 识别为物理鼠标键盘                                     │
│  - 无法被软件检测                                         │
│  - 运行游戏客户端                                         │
└─────────────────────────────────────────────────────────┘
```

## 核心功能

### 1. 怪物识别与优先级

系统会自动识别以下实体类型：

| 类型 | 类名 | 优先级 | 说明 |
|------|------|--------|------|
| BOSS | `boss` | 最高 | 优先攻击 |
| 精英怪 | `elite_monster` | 高 | 次优先 |
| 普通怪 | `normal_monster` | 中 | 最后攻击 |
| 掉落物 | `loot` | - | 近距离自动拾取 |
| NPC | `npc` | - | 不攻击 |

**决策逻辑**:
```python
if HP < 30%:
    执行补血
elif MP < 20%:
    执行补蓝
elif 掉落物距离 < 200px:
    移动到掉落物并拾取
elif 有怪物:
    按优先级选择目标 (BOSS > 精英 > 普通)
    移动到攻击点并攻击
else:
    继续搜索
```

### 2. 距离计算

系统会计算玩家角色与目标的像素距离：

```python
distance = sqrt((target_x - player_x)^2 + (target_y - player_y)^2)
```

- **玩家位置**: 可通过 `--player-pos x,y` 配置（默认屏幕中心）
- **攻击距离**: 通过 `--attack-range` 配置（默认 150px）
- **拾取距离**: 通过 `--pickup-range` 配置（默认 200px）

### 3. 血量蓝量检测

通过颜色特征识别 UI 血条和蓝条：

- **血条**: 红色区域 (HSV: H=0-10, 170-180)
- **蓝条**: 蓝色区域 (HSV: H=100-130)

**配置方法**:
```bash
--hp-region x,y,w,h   # 血条区域坐标
--mp-region x,y,w,h   # 蓝条区域坐标
```

### 4. 自动补血补蓝

当血量/蓝量低于阈值时，自动按快捷键使用药品：

```bash
--hp-key 1            # 补血快捷键 (默认 '1')
--mp-key 2            # 补蓝快捷键 (默认 '2')
--hp-threshold 30     # 血量低于 30% 时补血
--mp-threshold 20     # 蓝量低于 20% 时补蓝
```

---

## 训练 YOLO 模型

系统需要游戏专用的 YOLO 模型来识别怪物、掉落物等目标。

### 步骤 1: 收集训练数据

1. **截图工具**:
   ```bash
   # 使用游戏截图功能（按 F12 或其他快捷键）
   # 或使用 OBS 录制游戏画面
   ```

2. **数据量建议**:
   - 最少 500 张图片
   - 推荐 1000-2000 张
   - 覆盖不同场景、不同怪物、不同光照

3. **保存位置**:
   ```
   dataset/
   ├── images/
   │   ├── train/      # 80% 训练集
   │   └── val/        # 20% 验证集
   └── labels/
       ├── train/      # 对应标注
       └── val/
   ```

### 步骤 2: 标注数据

**推荐工具**: [LabelImg](https://github.com/HumanSignal/labelImg) 或 [Roboflow](https://roboflow.com/)

**标注类别** (根据游戏实际内容调整):
```yaml
# classes.yaml
names:
  0: normal_monster    # 普通怪
  1: elite_monster     # 精英怪
  2: boss              # BOSS
  3: loot              # 掉落物
  4: player            # 玩家角色 (可选)
  5: npc               # NPC (可选)
```

**标注格式** (YOLO 格式):
```
# 每行: <class_id> <x_center> <y_center> <width> <height>
# 坐标归一化到 0-1

# 示例: 普通怪在图片中心
0 0.5 0.5 0.1 0.15

# 示例: 掉落物在右下角
3 0.8 0.7 0.05 0.05
```

### 步骤 3: 训练模型

**方法 1: 使用 Ultralytics YOLOv8**

```bash
# 安装
pip install ultralytics

# 创建数据集配置文件
cat > game_dataset.yaml <<EOF
path: ./dataset
train: images/train
val: images/val

names:
  0: normal_monster
  1: elite_monster
  2: boss
  3: loot
EOF

# 开始训练
yolo task=detect mode=train model=yolov8n.pt data=game_dataset.yaml epochs=100 imgsz=640 batch=16

# 模型会保存在 runs/detect/train/weights/best.pt
```

**方法 2: 使用 Roboflow (在线训练)**

1. 上传数据到 [Roboflow](https://roboflow.com/)
2. 在线标注或使用 AI 辅助标注
3. 选择 YOLOv8 模型训练
4. 下载训练好的模型

### 步骤 4: 部署模型

```bash
# 将训练好的模型复制到项目目录
cp runs/detect/train/weights/best.pt ./game_yolo.pt

# 测试模型
python game_vision.py
```

---

## 配置示例

### 示例 1: ARPG 游戏 (如暗黑破坏神)

```bash
python game_agent.py \
    --port /dev/tty.usbserial-110 \
    --model game_yolo.pt \
    --capture-region 0,0,1920,1080 \
    --player-pos 960,540 \
    --hp-region 50,50,200,20 \
    --mp-region 50,80,200,20 \
    --hp-key 1 \
    --mp-key 2 \
    --pickup-key f \
    --attack-cooldown 0.5 \
    --hp-threshold 40 \
    --mp-threshold 30
```

**说明**:
- 玩家角色固定在屏幕中心 (960, 540)
- 血条在左上角 (50, 50, 200x20)
- 蓝条在血条下方 (50, 80, 200x20)
- 攻击冷却 0.5 秒（快速攻击）
- 血量低于 40% 补血

### 示例 2: MMORPG 游戏 (如魔兽世界)

```bash
python game_agent.py \
    --port /dev/tty.usbserial-110 \
    --model wow_yolo.pt \
    --capture-region 0,0,2560,1440 \
    --player-pos 1280,720 \
    --hp-region 100,100,300,30 \
    --mp-region 100,140,300,30 \
    --hp-key 1 \
    --mp-key 2 \
    --pickup-key f \
    --attack-cooldown 1.5 \
    --hp-threshold 50 \
    --mp-threshold 40
```

**说明**:
- 2K 分辨率 (2560x1440)
- 攻击冷却 1.5 秒（GCD 公共冷却）
- 血量低于 50% 补血（更安全）

### 示例 3: 无需硬件测试

```bash
# 模拟模式（不需要 Pico 硬件）
python game_agent.py --simulate --sim-duration 30

# 会模拟 30 秒的战斗过程
# 用于验证逻辑和配置
```

---

## 高级配置

### 自定义战斗策略

编辑 `game_agent.py` 中的 `CombatConfig` 类：

```python
@dataclass
class CombatConfig:
    # 攻击方式
    use_mouse_attack: bool = True      # True: 鼠标左键, False: 技能快捷键
    use_skill_rotation: bool = False   # 是否使用技能循环
    
    # 技能循环配置
    skill_keys = ['1', '2', '3', '4']  # 技能快捷键顺序
    
    # 搜索参数
    search_interval: float = 0.3       # 搜索间隔（秒）
    
    # 安全设置
    max_consecutive_fails: int = 10    # 连续失败次数上限
    retreat_distance: float = 300.0    # 撤退距离
```

### 自定义决策逻辑

编辑 `game_vision.py` 中的 `make_decision` 方法：

```python
def make_decision(self, monsters, loots, health):
    # 自定义优先级逻辑
    
    # 示例: 优先攻击精英怪（即使有 BOSS）
    elite = next((m for m in monsters if m.entity_type == EntityType.ELITE_MONSTER), None)
    if elite and elite.distance < 300:
        return {'action': 'attack', 'target': elite, 'reason': '优先精英怪'}
    
    # 示例: 血量低于 50% 立即撤退
    if health.hp_percent < 50:
        return {'action': 'retreat', 'target': None, 'reason': '低血量撤退'}
    
    # ... 其他逻辑
```

### 多角色支持

如果游戏有多个角色（如召唤物、宠物），需要扩展模型类别：

```yaml
# classes.yaml
names:
  0: normal_monster
  1: elite_monster
  2: boss
  3: loot
  4: player
  5: pet               # 宠物
  6: summon            # 召唤物
```

然后在 `EntityType` 中添加：
```python
class EntityType(Enum):
    PET = "pet"
    SUMMON = "summon"
```

---

## 故障排查

### 问题 1: 模型无法识别怪物

**原因**: 训练数据不足或类别不匹配

**解决**:
1. 增加训练数据（至少 500 张）
2. 检查类别名称是否与 `class_mapping` 一致
3. 使用 `game_vision.py` 的 `--debug` 模式查看检测结果

### 问题 2: 血量检测不准确

**原因**: 血条颜色或位置变化

**解决**:
1. 使用 `--debug` 模式查看血条区域
2. 调整 `--hp-region` 坐标
3. 修改 `_calculate_bar_percent` 中的颜色范围

### 问题 3: 攻击时机不对

**原因**: 攻击冷却或距离设置不合理

**解决**:
1. 调整 `--attack-cooldown`（匹配游戏 GCD）
2. 调整 `--attack-range`（匹配攻击距离）
3. 检查游戏是否有前摇动画

### 问题 4: 拾取失败

**原因**: 拾取键错误或距离太远

**解决**:
1. 确认游戏拾取键（通常是 F 或空格）
2. 调整 `--pickup-range`
3. 检查是否需要先移动到掉落物上

---

## 性能优化

### 提高 FPS

```bash
# 使用更小的 YOLO 模型
--model yolov8n.pt      # nano (最快)
--model yolov8s.pt      # small (平衡)
--model yolov8m.pt      # medium (准确)

# 降低输入分辨率
# 在 game_vision.py 中修改:
results = self.model(frame, conf=0.5, imgsz=320, verbose=False)
```

### 降低延迟

```bash
# 减少搜索间隔
--search-interval 0.1   # 100ms (默认 300ms)

# 使用 GPU 推理
# 确保安装了 CUDA 版本的 PyTorch
```

### 减少误操作

```bash
# 增加攻击冷却
--attack-cooldown 1.5

# 提高置信度阈值
# 在 game_vision.py 中修改:
results = self.model(frame, conf=0.7, verbose=False)
```

---

## 安全警告

⚠️ **使用风险**:
- 本系统仅用于学习研究
- 在游戏中使用可能违反服务条款
- 可能导致账号封禁
- 请自行承担风险

⚠️ **硬件安全**:
- 确保 USB-to-TTL 转换器质量可靠
- 避免长时间高负载运行
- 定期检查 Pico 温度

⚠️ **数据安全**:
- 不要在游戏账号中使用重要角色测试
- 建议先在小号或测试服验证
- 定期备份游戏存档

---

## 技术支持

**问题反馈**: 提交 Issue
**功能建议**: 提交 Feature Request
**文档更新**: 欢迎 PR

**相关文档**:
- [API 参考](docs/API_REFERENCE.md)
- [开发指南](docs/DEVELOPMENT_GUIDE.md)
- [故障排查](docs/TROUBLESHOOTING.md)

---

## 更新日志

### v2.1.0 (2026-08-21)
- ✨ 新增游戏视觉模块 (`game_vision.py`)
- ✨ 新增自动化战斗 Agent (`game_agent.py`)
- ✨ 支持怪物识别（普通怪、精英怪、BOSS）
- ✨ 支持掉落物识别和自动拾取
- ✨ 支持血量蓝量检测和自动补充
- ✨ 支持距离计算和智能决策
- ✨ 新增模拟模式（无需硬件测试）

### v2.0.0 (2026-08-18)
- 初始版本
- 基础 HID 控制
- 视觉流水线
- 性能监控工具

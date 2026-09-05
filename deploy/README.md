# 部署说明

## 快速开始

### 1. 烧录固件

**Windows:**
1. 按住 Pico 的 BOOTSEL 按钮
2. 用 USB 线连接电脑
3. 会出现 RPI-RP2 磁盘
4. 将 `pico_hid_firmware.uf2` 拖入磁盘
5. Pico 自动重启并运行固件

**Linux:**
```bash
# 检测 Pico 设备
ls /dev/ttyACM*

# 设置串口权限
sudo usermod -a -G dialout $USER
sudo chmod 666 /dev/ttyACM0

# 使用 picotool 烧录（可选）
picotool load pico_hid_firmware.uf2
picotool reboot
```

### 2. 运行控制系统

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行示例
python examples/example_simple_click.py
```

## 验证部署

运行自检：
```bash
python test_components.py
```

检查串口连接：
```python
from pico_protocol import PicoProtocol
pico = PicoProtocol('/dev/ttyACM0')  # Windows: 'COM3'
print(pico.ping())  # 应返回 PONG
```

## 故障排除

**问题：Pico 无响应**
- 检查 USB 连接
- 确认固件已烧录（LED 应该闪烁）
- 检查串口权限

**问题：鼠标移动不准确**
- 校准坐标系：`python calibrate.py`
- 检查 Bézier 参数配置

**问题：按键延迟异常**
- 检查 Profile 配置
- 验证高斯 RNG 参数

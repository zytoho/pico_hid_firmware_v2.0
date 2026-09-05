#!/bin/bash
# Pico HID Firmware 自动部署脚本

set -e

echo "========================================"
echo "Pico HID Firmware 自动部署"
echo "========================================"
echo ""

# 检测操作系统
OS="$(uname -s)"
case "${OS}" in
    Linux*)     OS_TYPE=Linux;;
    Darwin*)    OS_TYPE=Mac;;
    CYGWIN*|MINGW*|MSYS*) OS_TYPE=Windows;;
    *)          OS_TYPE="Unknown"
esac

echo "检测到操作系统: $OS_TYPE"
echo ""

# Step 1: 检查编译产物
echo "[1/5] 检查编译产物..."
if [ ! -f "pico_hid_firmware/build/pico_hid_firmware.uf2" ]; then
    echo "❌ 固件未编译，正在编译..."
    if command -v nproc >/dev/null 2>&1; then
        JOBS="$(nproc)"
    else
        JOBS="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"
    fi
    cd pico_hid_firmware/build
    make -j"$JOBS"
    cd ../..
fi

if [ -f "pico_hid_firmware/build/pico_hid_firmware.uf2" ]; then
    echo "✅ 固件已就绪: pico_hid_firmware/build/pico_hid_firmware.uf2"
    ls -lh pico_hid_firmware/build/pico_hid_firmware.uf2
else
    echo "❌ 固件编译失败"
    exit 1
fi
echo ""

# Step 2: 检查 Python 环境
echo "[2/5] 检查 Python 环境..."
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✅ Python 环境已准备"
echo ""

# Step 3: 检查串口设备
echo "[3/5] 检查串口设备..."
SERIAL_PORT=""
FOUND_PORTS=()
if [ "$OS_TYPE" = "Linux" ]; then
    for p in /dev/ttyACM* /dev/ttyUSB*; do
        [ -e "$p" ] && FOUND_PORTS+=("$p")
    done
    if [ ${#FOUND_PORTS[@]} -gt 0 ]; then
        echo "✅ 检测到串口设备:"
        ls -l "${FOUND_PORTS[@]}"
        SERIAL_PORT="${FOUND_PORTS[0]}"
        if groups | grep -q dialout; then
            echo "✅ 用户已在 dialout 组"
        else
            echo "⚠️  用户不在 dialout 组，尝试添加..."
            sudo usermod -a -G dialout $USER
            echo "✅ 已添加到 dialout 组，重新登录后生效"
        fi
    else
        echo "⚠️  未检测到 /dev/ttyACM* 或 /dev/ttyUSB* 设备"
        echo "   请确认 Pico / USB-TTL 已连接"
    fi
elif [ "$OS_TYPE" = "Mac" ]; then
    # usbserial = USB-TTL (CH340/CP2102/FTDI)，usbmodem = Pico CDC
    for p in /dev/cu.usbserial* /dev/tty.usbserial* /dev/cu.usbmodem* /dev/tty.usbmodem*; do
        [ -e "$p" ] && FOUND_PORTS+=("$p")
    done
    if [ ${#FOUND_PORTS[@]} -gt 0 ]; then
        echo "✅ 检测到串口设备:"
        ls -l "${FOUND_PORTS[@]}"
        # 优先使用 cu.* ，避免 tty.* 等待载波
        for p in "${FOUND_PORTS[@]}"; do
            case "$p" in
                /dev/cu.*) SERIAL_PORT="$p"; break ;;
            esac
        done
        SERIAL_PORT="${SERIAL_PORT:-${FOUND_PORTS[0]}}"
        echo "   默认串口: $SERIAL_PORT"
    else
        echo "⚠️  未检测到 USB 串口 (usbserial / usbmodem)"
        echo "   请确认 USB-TTL 已连接到 Mac"
    fi
else
    echo "Windows 用户请手动检查设备管理器中的 COM 端口"
fi
echo ""

# Step 4: 运行自检
echo "[4/5] 运行系统自检..."
cd control
python test_components.py
cd ..
echo ""

# Step 5: 提供烧录指导
echo "[5/5] 烧录指导"
echo "========================================"
echo ""
if [ "$OS_TYPE" = "Linux" ] || [ "$OS_TYPE" = "Mac" ]; then
    echo "方法 1: 使用 picotool（推荐）"
    echo "  sudo picotool load pico_hid_firmware/build/pico_hid_firmware.uf2"
    echo "  sudo picotool reboot"
    echo ""
    echo "方法 2: BOOTSEL 模式"
    echo "  1. 按住 Pico 上的 BOOTSEL 按钮"
    echo "  2. 插入 USB 线"
    echo "  3. 挂载 RPI-RP2 磁盘"
    echo "  4. 复制固件文件:"
    echo "     cp pico_hid_firmware/build/pico_hid_firmware.uf2 /media/*/RPI-RP2/"
    echo ""
fi

echo "方法 3: 手动复制"
echo "  固件文件位置:"
echo "  $(pwd)/pico_hid_firmware/build/pico_hid_firmware.uf2"
echo ""

echo "========================================"
echo "部署准备完成！"
echo "========================================"
echo ""
echo "下一步："
echo "1. 烧录固件到 Pico（若尚未烧录）"
echo "2. 激活虚拟环境: source venv/bin/activate"
if [ -n "$SERIAL_PORT" ]; then
    echo "3. 串口已检测: $SERIAL_PORT"
    echo "   自检: python control/test_components.py"
else
    echo "3. 运行自检: python control/test_components.py"
fi
echo ""

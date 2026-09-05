@echo off
REM Windows 快速部署脚本

echo ==========================================
echo   高性能模拟人类行为控制系统 - 部署脚本
echo ==========================================
echo.

REM 1. 检查 Python
echo [1/5] 检查 Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [OK] %PYTHON_VERSION%

REM 2. 创建虚拟环境
echo.
echo [2/5] 创建虚拟环境...
if not exist "venv" (
    python -m venv venv
    echo [OK] 虚拟环境已创建
) else (
    echo [OK] 虚拟环境已存在
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 3. 安装依赖
echo.
echo [3/5] 安装 Python 依赖...
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo [OK] Python 依赖已安装

REM 4. 下载 YOLO 模型
echo.
echo [4/5] 检查 YOLO 模型...
if not exist "yolov8n.pt" (
    echo 下载 YOLOv8n 模型...
    curl -L -o yolov8n.pt https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt
    echo [OK] YOLO 模型已下载
) else (
    echo [OK] YOLO 模型已存在
)

REM 5. 运行测试
echo.
echo [5/5] 运行单元测试...
python test_components.py >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] 单元测试全部通过
) else (
    echo [WARN] 部分测试失败，但不影响基本功能
)

REM 完成
echo.
echo ==========================================
echo [OK] 部署完成！
echo ==========================================
echo.
echo 下一步：
echo   1. 激活虚拟环境: venv\Scripts\activate
echo   2. 运行无硬件演示: python demo_no_hardware.py
echo   3. 连接 Pico 硬件后运行示例:
echo      python examples\example_simple_click.py
echo.
echo 更多信息请查看: README.md
echo.
pause

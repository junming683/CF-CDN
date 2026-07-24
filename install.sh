#!/usr/bin/env bash
# ==================================================
# CF-CDN 测速工具 - Termux / Linux 自动安装脚本
# ==================================================

echo "=================================================="
echo "正在配置 CF-CDN 测速环境..."
echo "--------------------------------------------------"

# 检测操作系统并安装依赖
if [ -n "$TERMUX_VERSION" ] || [ -d "/data/data/com.termux" ]; then
    echo "[+] 检测到 Android Termux 环境，正在检查安装 Python..."
    pkg update -y && pkg install python -y
    BIN_DIR="${PREFIX:-/data/data/com.termux/files/usr}/bin"
else
    echo "[+] 检测到标准 Linux / macOS 环境..."
    BIN_DIR="/usr/local/bin"
fi

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/cfcdn.py"
chmod +x "$SCRIPT_PATH"

if [ -d "$BIN_DIR" ]; then
    CMD_FILE="$BIN_DIR/cfcdn"
    cat << EOF > "$CMD_FILE"
#!/usr/bin/env bash
python3 "$SCRIPT_PATH" "\$@"
EOF
    chmod +x "$CMD_FILE"
    echo "[✔] 快捷指令写入成功: $CMD_FILE"
else
    echo "[!] 警告: 未找到快捷指令目录 $BIN_DIR，尝试写入 ~/.bashrc 或 ~/.zshrc 别名"
    alias_cmd="alias cfcdn='python3 $SCRIPT_PATH'"
    if [ -f "$HOME/.bashrc" ]; then
        echo "$alias_cmd" >> "$HOME/.bashrc"
    fi
    if [ -f "$HOME/.zshrc" ]; then
        echo "$alias_cmd" >> "$HOME/.zshrc"
    fi
fi

echo "--------------------------------------------------"
echo "🎉 安装完成！"
echo "现在你可以随时在命令行输入："
echo "  cfcdn"
echo "直接运行 Cloudflare 域名延迟测试！"
echo "=================================================="

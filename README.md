# 🚀 CF-CDN 域名延迟并发测试工具

这是一个轻量级、跨平台的 **Cloudflare (CF) CDN 域名延迟测试与优选工具**。特别针对 **Android Termux** 进行了优化，同时支持 Linux、macOS 与 Windows。

---

## ✨ 核心特性

- ⚡ **多线程并发测速**：采用并发线程池测试，50+ 域名测试仅需几秒钟即可完成。
- 📊 **智能平均值计算**：每个域名自动 Ping 3 次并解析平均延迟。
- 🔝 **双格式自动导出**：
  - `CDNym.txt`：带延迟数值与前缀（如 `20.180 ms: www.okcupid.com`）
  - `CDNym_clean.txt`：纯域名列表（无任何前缀和延迟，方便直接全选复制到客户端）
- 📱 **Termux 专属快捷命令**：在 Android 手机 Termux 安装后，直接输入 `cfcdn` 即可随时随地发起测试。
- 📝 **支持自定义域名库**：支持读取 `domains.txt`，可自由添加或更新你的节点库。

---

## 📲 安卓 Termux 安装与使用教程

### 1. 一键下载与安装

打开 Android 手机上的 **Termux** app，复制并运行以下命令：

```bash
git clone https://github.com/junming683/CF-CDN.git && cd CF-CDN && bash install.sh
```

> **说明**：安装脚本会自动检查并安装 `python`，并注册全局快捷指令 `cfcdn`。

### 2. 运行测试

安装完成后，你可以在 Termux 任意路径直接输入：

```bash
cfcdn
```

即可直接运行测速！

---

## 🖥️ 其它系统使用说明（Windows / Linux / macOS）

### 运行环境要求
- Python 3.6+

### 运行命令
```bash
# 克隆仓库
git clone https://github.com/junming683/CF-CDN.git
cd CF-CDN

# 运行测试脚本
python cfcdn.py
```

---

## 📁 目录结构

```text
CF-CDN/
├── cfcdn.py          # 核心 Python 测速脚本
├── domains.txt       # 域名列表文件（可自定义修改）
├── install.sh        # Termux / Linux 一键快捷指令配置脚本
├── CDNym.txt         # [测试后生成] 带延迟的完整测试结果
├── CDNym_clean.txt   # [测试后生成] 无前缀纯域名结果（方便一键复制）
└── README.md         # 中文使用说明文档
```

---

## 📄 导出结果示例

测试完成后，会在当前目录下自动生成两个文件：

### 1. `CDNym.txt` (带延迟)
```text
20.180 ms: www.okcupid.com
25.793 ms: www.boba88slot.com
27.158 ms: www.shopify.com
29.318 ms: fbi.gov
31.003 ms: www.udacity.com
```

### 2. `CDNym_clean.txt` (纯域名，直复制版)
```text
www.okcupid.com
www.boba88slot.com
www.shopify.com
download.yunzhongzhuan.com
fbi.gov
www.udacity.com
ip.sb
```

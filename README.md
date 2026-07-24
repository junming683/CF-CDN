# 🚀 CF-CDN 域名延迟并发测试工具

这是一个轻量级、跨平台的 **Cloudflare (CF) CDN 域名延迟测试与优选工具**。特别针对 **Android Termux** 进行了优化，同时支持 Linux、macOS 与 Windows。

---

## ✨ 核心特性

- ⚡ **多线程并发测速**：采用并发线程池测试，50+ 域名测试仅需几秒钟即可完成。
- 📊 **智能平均值计算**：每个域名自动 Ping 3 次并解析平均延迟。
- 🔝 **自动升序排序**：测试完成后自动按延迟由低到高排序，并格式化导出为 `CDNym.txt`。
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
├── cfcdn.py       # 核心 Python 测速脚本
├── domains.txt    # 域名列表文件（可自定义修改）
├── install.sh     # Termux / Linux 一键快捷指令配置脚本
└── README.md      # 中文使用说明文档
```

---

## ⚙️ 自定义域名

你可以直接修改 `domains.txt` 文件来自由添加或删减域名：

```bash
nano domains.txt
```

编辑完成后按 `Ctrl + O` 保存，`Ctrl + X` 退出即可。再次运行 `cfcdn` 即可自动载入你的新域名库。

---

## 📄 导出结果文件说明

测试完成后，会在当前目录下生成 `CDNym.txt` 文件，内容示例如下：

```text
20.180 ms: www.okcupid.com
25.793 ms: www.boba88slot.com
27.158 ms: www.shopify.com
29.318 ms: fbi.gov
31.003 ms: www.udacity.com
...
```

你可以选择延迟最低的域名用于替换客户端地址。

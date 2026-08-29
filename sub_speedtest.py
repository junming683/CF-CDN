#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CF-CDN 扩展模块：VLESS 订阅节点真实代理测速与智能排序工具
运行环境：Android Termux / Linux
功能特性：
  1. 支持按分类拉取订阅（移动优选 / 电信优选 / 直连节点库 / 全量合并）
  2. 白名单拉取订阅 -> 纯内存暂存 -> 通知栏断开 VPN 交互 -> 本地真实网络直连测速
  3. 原生 Socket + TLS + WebSocket + VLESS 协议握手，5 线程轻量并发
  4. 测速完成后自动剔除离线/测速失败节点，按真实下行速率降序排列并追加 [xx.xxMB/s] 前缀
  5. 自动调用 termux-clipboard-set 写入手机剪贴板（需 pkg install termux-api + Termux:API 应用）
  6. 订阅自动备份到 /sdcard/CF-CDN/，剪贴板不可用时逐条打印节点链接方便手动复制
"""

import base64
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

# ================= 基础配置 =================
BASE_URL = "https://dingyue.042499.xyz:8443"

# 订阅源分类定义
SUB_SOURCES = {
    "1": {
        "name": "中国移动优选 (sub.txt)",
        "file": "sub.txt",
        "desc": "移动优选 · Base64 / 节点列表"
    },
    "2": {
        "name": "中国电信优选 (sub_yaml.txt)",
        "file": "sub_yaml.txt",
        "desc": "电信优选 · Clash / 节点列表"
    },
    "3": {
        "name": "直连节点库 (sub_yaml_android.txt)",
        "file": "sub_yaml_android.txt",
        "desc": "直连/混合节点库"
    },
    "4": {
        "name": "全量合并测速 (合并 1+2+3 并去重)",
        "file": "__ALL__",
        "desc": "三网与直连全量节点"
    }
}

# Nginx Basic 认证凭据（若无密码请留空字符串）
NGINX_USER = "admin"
NGINX_PASS = "your_password"

# 测速参数
CONCURRENT_LIMIT = 5            # 并发线程数
TEST_BYTES = 2 * 1024 * 1024     # 单节点测速流量：2MB
TEST_TIMEOUT = 5.0               # 单节点超时时间（秒）
TARGET_HOST = "speed.cloudflare.com"
TARGET_PORT = 80


def get_auth_headers():
    headers = {"User-Agent": "Mozilla/5.0"}
    if NGINX_USER and NGINX_PASS:
        token = base64.b64encode(f"{NGINX_USER}:{NGINX_PASS}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {token}"
    return headers


def copy_to_clipboard(text):
    """将结果写入 Termux 剪贴板（需 termux-api 包 + Termux:API 应用同时安装）"""
    if not shutil.which("termux-clipboard-set"):
        return False
    try:
        p = subprocess.Popen(["termux-clipboard-set"], stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p.communicate(input=text.encode("utf-8"), timeout=10)
        return p.returncode == 0
    except Exception:
        return False


def get_output_dir():
    """获取输出目录：Termux 保存到 /sdcard/CF-CDN/（文件管理器直接可见），其他系统用脚本目录"""
    if os.path.exists("/sdcard"):
        try:
            out_dir = "/sdcard/CF-CDN"
            os.makedirs(out_dir, exist_ok=True)
            return out_dir
        except Exception:
            pass
    return os.path.dirname(os.path.abspath(__file__))


def fetch_single_file(sub_file):
    """单文件内存拉取"""
    url = f"{BASE_URL}/{sub_file}" if not sub_file.startswith("http") else sub_file
    req = urllib.request.Request(url, headers=get_auth_headers())
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    print(f"  [>] 正在拉取订阅: {url} ...")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            raw_data = resp.read().decode("utf-8", errors="ignore").strip()
            return raw_data
    except Exception as e:
        print(f"  [!] 拉取 {sub_file} 失败: {e}")
        return ""


def select_subscription_source():
    """交互选择订阅源"""
    print("\n" + "=" * 60)
    print(" 📡 请选择要拉取测速的订阅源分类：")
    print("=" * 60)
    for k, v in SUB_SOURCES.items():
        print(f"  {k}️⃣  {v['name']}  -->  {v['desc']}")
    print("  5️⃣  自定义订阅链接 / 文件名")
    print("")

    while True:
        try:
            choice = input(" 请输入选项 1 / 2 / 3 / 4 / 5 (默认: 1 移动优选): ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "1"
        if choice in ("1", "2", "3", "4"):
            return SUB_SOURCES[choice]["file"], SUB_SOURCES[choice]["name"]
        elif choice == "5":
            try:
                custom = input(" 请输入订阅文件路径或完整 URL (如 sub.txt): ").strip()
                if not custom:
                    custom = "sub.txt"
                return custom, f"自定义源 ({custom})"
            except (EOFError, KeyboardInterrupt):
                return "sub.txt", SUB_SOURCES["1"]["name"]
        elif choice == "":
            return SUB_SOURCES["1"]["file"], SUB_SOURCES["1"]["name"]
        else:
            print(" ⚠️  请输入有效选项编号 1 ~ 5")


def fetch_sub_to_memory():
    """内存拉取订阅并触发 VPN 断开交互暂停"""
    sub_target, sub_label = select_subscription_source()

    print(f"\n[1/4] 正在拉取【{sub_label}】...")

    raw_contents = []
    if sub_target == "__ALL__":
        for key in ("1", "2", "3"):
            fname = SUB_SOURCES[key]["file"]
            content = fetch_single_file(fname)
            if content:
                raw_contents.append(content)
    else:
        content = fetch_single_file(sub_target)
        if content:
            raw_contents.append(content)

    if not raw_contents:
        print("[!] 订阅内容为空，请检查网络或认证配置")
        return ""

    merged_raw = "\n".join(raw_contents)
    print("[+] 订阅数据已成功载入内存！")
    print("\n" + "=" * 58)
    print(" [🔔 操作提示] ")
    print(" 订阅已拉取并暂存于内存。请立即【下拉手机通知栏断开 VPN】！")
    print(" 断开 VPN 后回到 Termux 按 [回车键]，使用手机真实网络直连测速。")
    print("=" * 58)
    try:
        input("👉 确认已断开 VPN 后按回车继续: ")
    except (EOFError, KeyboardInterrupt):
        pass
    return merged_raw


def parse_vless_nodes(raw_content):
    """解析 Base64 或明文 VLESS 节点列表并自动去重"""
    content = raw_content
    # 若整体为 Base64 则先解码
    if not any(k in content for k in ("vless://", "vmess://", "trojan://", "hysteria2://", "hy2://")):
        try:
            content = base64.b64decode(content).decode("utf-8", errors="ignore")
        except Exception:
            pass

    nodes = []
    seen_keys = set()

    for line in content.splitlines():
        line = line.strip()
        # 去除 YAML 行前导符
        if line.startswith("- "):
            line = line[2:].strip()
        if not line.startswith("vless://"):
            continue

        m = re.search(r"vless://([^@]+)@([^:]+):(\d+)\?([^#]+)#(.*)$", line)
        if m:
            user_uuid = m.group(1).strip()
            host = m.group(2).strip()
            port = int(m.group(3).strip())
            params_str = m.group(4).strip()
            raw_name = m.group(5).strip()

            params = dict(urllib.parse.parse_qsl(params_str))
            net_type = params.get("type", "ws").lower()
            security = params.get("security", "tls").lower()

            # 仅对支持纯 Socket TLS/WS 握手的节点进行真实吞吐量测速
            is_testable = (net_type == "ws" and security in ("tls", "none"))

            dedup_key = (user_uuid, host, port, urllib.parse.unquote(params.get("path", "/")))
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            raw_path = params.get("path", "/")
            clean_path = urllib.parse.unquote(raw_path)
            if not clean_path.startswith("/"):
                clean_path = "/" + clean_path

            nodes.append({
                "raw": line,
                "uuid": user_uuid,
                "host": host,
                "port": port,
                "params_str": params_str,
                "path": clean_path,
                "sni": params.get("sni", host),
                "ws_host": params.get("host", params.get("sni", host)),
                "name": urllib.parse.unquote(raw_name),
                "is_testable": is_testable,
                "speed": 0.0,
                "latency": 9999.0
            })
    return nodes


def test_single_node(node):
    """纯 Python 底层 Socket 模拟 VLESS+WS+TLS 发起真实下载测速"""
    if not node.get("is_testable", True):
        # 非 WS+TLS 协议（如 Reality / TCP）无法通过纯 WS 握手测速，保留原状
        node["speed"] = 0.0
        node["latency"] = 8888.0
        print(f"  [ SKIPPED ] {node['name'][:28]} (非 WS+TLS 协议)")
        return node

    host = node["host"]
    port = node["port"]
    user_uuid = node["uuid"]
    path = node["path"]
    sni = node["sni"]
    ws_host = node["ws_host"]

    try:
        start_time = time.time()
        # 1. 建立 TLS Socket 连接
        raw_sock = socket.create_connection((host, port), timeout=TEST_TIMEOUT)
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        sock = ssl_ctx.wrap_socket(raw_sock, server_hostname=sni if sni else host)

        # 2. 发起 WebSocket 升级握手 (Sec-WebSocket-Key 必须是 16 字节随机二进制 Base64)
        ws_key = base64.b64encode(os.urandom(16)).decode()
        ws_req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {ws_host}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(ws_req.encode("utf-8"))

        header_buf = b""
        while b"\r\n\r\n" not in header_buf:
            chunk = sock.recv(1024)
            if not chunk:
                break
            header_buf += chunk

        if b"101" not in header_buf:
            sock.close()
            return node

        # 3. 构造 VLESS 协议头 (0x00=版本, UUID=16字节, 0x00=附加信息长度, 0x01=TCP, 端口=2字节, 0x02=域名类型, 域名长度+域名)
        uid_bytes = uuid.UUID(user_uuid).bytes
        target_bytes = TARGET_HOST.encode("utf-8")
        vless_hdr = bytearray([0x00]) + uid_bytes + bytearray([0x00, 0x01])
        vless_hdr += struct.pack(">H", TARGET_PORT) + bytearray([0x02, len(target_bytes)]) + target_bytes

        http_payload = (
            f"GET /__down?bytes={TEST_BYTES} HTTP/1.1\r\n"
            f"Host: {TARGET_HOST}\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("utf-8")

        payload = bytes(vless_hdr) + http_payload
        p_len = len(payload)

        # 4. 封装 WebSocket 二进制掩码帧 (Opcode 0x82)
        mask = os.urandom(4)
        frame = bytearray([0x82])
        if p_len < 126:
            frame.append(0x80 | p_len)
        elif p_len <= 65535:
            frame.append(0x80 | 126)
            frame.extend(struct.pack(">H", p_len))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack(">Q", p_len))

        frame.extend(mask)
        masked_payload = bytearray(p_len)
        for i in range(p_len):
            masked_payload[i] = payload[i] ^ mask[i % 4]
        frame.extend(masked_payload)

        # 5. 发送请求并统计吞吐量
        sock.sendall(frame)
        sock.settimeout(TEST_TIMEOUT)

        first_byte_time = None
        total_downloaded = 0

        while True:
            chunk = sock.recv(32768)
            if not chunk:
                break
            if first_byte_time is None:
                first_byte_time = time.time()
            total_downloaded += len(chunk)
            if total_downloaded >= TEST_BYTES or (time.time() - start_time) > TEST_TIMEOUT:
                break

        sock.close()

        if total_downloaded > 0 and first_byte_time is not None:
            latency_ms = round((first_byte_time - start_time) * 1000, 1)
            duration = max(time.time() - first_byte_time, 0.05)
            speed_mb_s = round((total_downloaded / (1024 * 1024)) / duration, 2)
            node["speed"] = speed_mb_s
            node["latency"] = latency_ms
    except Exception:
        node["speed"] = 0.0
        node["latency"] = 9999.0

    status_tag = f"{node['speed']:>5.2f} MB/s | {node['latency']:>6.1f}ms" if node["speed"] > 0 else "  FAILED  "
    print(f"  [{status_tag}] {node['name'][:28]}")
    return node


def build_link(node):
    """重构节点名称并生成单条 VLESS 链接"""
    # 去除可能已存在的旧测速标签
    clean_name = re.sub(r"^\[\d+(\.\d+)?MB/s\]-", "", node["name"])
    speed_label = f"[{node['speed']:.2f}MB/s]" if node["speed"] > 0 else "[OFFLINE]"
    new_name = f"{speed_label}-{clean_name}"
    encoded_name = urllib.parse.quote(new_name)
    return f"vless://{node['uuid']}@{node['host']}:{node['port']}?{node['params_str']}#{encoded_name}"


def build_final_subscription(online_nodes):
    """生成最终 Base64 订阅文本（调用方需保证只传入测速成功的在线节点）"""
    plain_sub = "\n".join(build_link(node) for node in online_nodes)
    return base64.b64encode(plain_sub.encode("utf-8")).decode("utf-8")


def main():
    print("=" * 60)
    print("  CF-CDN 订阅节点测速与智能排序工具 (Termux 优化版)")
    print("=" * 60)

    raw_sub = fetch_sub_to_memory()
    if not raw_sub:
        return

    nodes = parse_vless_nodes(raw_sub)
    if not nodes:
        print("[!] 未解析到有效 VLESS 节点")
        return

    print(f"\n[2/4] 共载入 {len(nodes)} 个独立节点，启动 {CONCURRENT_LIMIT} 线程并发测速...")
    tested_nodes = []
    with ThreadPoolExecutor(max_workers=CONCURRENT_LIMIT) as executor:
        results = executor.map(test_single_node, nodes)
        for res in results:
            tested_nodes.append(res)

    print("\n[3/4] 正在按真实下载速率降序重排...")
    # 优先按速度降序；速度相同时按延迟升序
    sorted_nodes = sorted(tested_nodes, key=lambda x: (x["speed"], -x["latency"]), reverse=True)

    # 只保留测速成功的在线节点，离线/测速失败节点全部剔除
    online_nodes = [n for n in sorted_nodes if n["speed"] > 0]
    offline_count = len(sorted_nodes) - len(online_nodes)
    print(f"[+] 测速完成：可用节点 {len(online_nodes)}/{len(sorted_nodes)}，已剔除 {offline_count} 个离线/测速失败节点")

    if not online_nodes:
        print("\n[!] 所有节点均测速失败，本次不生成订阅（避免清空客户端节点），请检查网络后重试。")
        return

    print("\n[4/4] 重新编码并导出订阅（仅含在线节点）...")
    final_base64 = build_final_subscription(online_nodes)

    # 同步备份到本地文件（Termux 下位于 /sdcard/CF-CDN/，文件管理器直接可见）
    out_dir = get_output_dir()
    out_file = os.path.join(out_dir, f"VLESS订阅-{time.strftime('%Y%m%d-%H%M%S')}.txt")
    try:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(final_base64)
        print(f"📁 订阅已备份到: {out_file}")
    except Exception as e:
        print(f"[!] 订阅备份保存失败: {e}")

    if copy_to_clipboard(final_base64):
        print(f"\n✅ 已剔除全部离线节点，{len(online_nodes)} 个在线节点的订阅已写入手机剪贴板，去客户端粘贴导入即可！")
    else:
        print("\n[⚠] 未检测到可用的 termux-clipboard-set，无法自动写入剪贴板。")
        print("    想启用一键复制：Termux 里执行 pkg install termux-api ，并安装 Termux:API 应用后重跑本工具。")
        print("    目前可以：① 部分客户端支持「从文件导入」上面的备份文件；② 长按逐条复制下面的节点链接：\n")
        for node in online_nodes:
            print(build_link(node))


if __name__ == "__main__":
    main()
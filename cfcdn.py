#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CF-CDN 智能多网/多运营商 Cloudflare CDN 真实带宽与延迟测速工具
支持 Android Termux / Linux / macOS / Windows

核心特性：
  1. 多源动态在线 API 自动同步（vps789.com + ipdb.api.030101.xyz + 090227.xyz）
  2. 内置 vps789 官方 Token 授权，拉取 CT/CM/CU 专属分流库与全网 Top20 优选池
  3. 运营商精准分流（电信 / 移动 / 联通 / 三网全量通用）
  4. 双阶段深度真·测速（并发 Ping 过滤 + Cloudflare 官方真实下载带宽测试）
  5. 解决纯 IP 测速 SSL 握手报错与假 0MB/s 问题（支持 TLS SNI / Host 伪装）
  6. 智能分类推荐（综合最佳 Top4、高带宽 Top4、极低延迟 Top4）与纯节点直复制区域
  7. 内存保护与多并发模式（防 Android Termux OOM 强杀）
"""

import os
import sys
import re
import json
import time
import socket
import ssl
import platform
import subprocess
import http.client
import urllib.request
import concurrent.futures

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OUTPUT_FILE = "CDNym.txt"
OUTPUT_CLEAN_FILE = "CDNym_clean.txt"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAIN_FILE = os.path.join(SCRIPT_DIR, "domains.txt")

# vps789 API 授权 Token
VPS789_TOKEN = "1V1B837SN4VBG42SC1X83DHJ0SMTR8SK"

# ================= 运营商专属配置与在线 API =================

ISP_CONFIG = {
    "1": {
        "name": "中国电信 (China Telecom)",
        "desc": "美西直连 / 大带宽抗丢包节点 (SJC/LAX)",
        "vps789_key": "CT",
        "ipdb_types": ["bestcf", "bestproxy"],
        "extra_api_urls": [
            "https://cf.090227.xyz/ct?ips=20",
        ],
        "ping_threshold": 350.0,  # 电信直连美西正常物理延迟在 140~220ms，放宽门槛确保真实美西节点进入测速
        "priority_prefixes": ["104.16.", "104.17.", "104.18.", "104.19.", "162.159.", "198.41.", "172.67."],
        "priority_domains": [
            "ct.090227.xyz",
            "telecom.cloudflare.1874.fun",
            "cf-ct.090227.xyz",
            "us.090227.xyz",
            "shopify.com",
            "www.visa.com",
            "speed.cloudflare.com",
            "dash.cloudflare.com",
            "cloudflare.com",
        ],
    },
    "2": {
        "name": "中国移动 (China Mobile)",
        "desc": "香港 / 新加坡 / 日本 CMI 低延迟节点",
        "vps789_key": "CM",
        "ipdb_types": ["bestcf", "bestproxy"],
        "extra_api_urls": [
            "https://cf.090227.xyz/cmcc?ips=20",
        ],
        "ping_threshold": 160.0,  # 移动严选亚洲低延迟直连
        "priority_prefixes": ["104.28.", "172.67.", "104.21.", "104.22.", "104.23.", "104.24.", "104.25.", "108.162.", "141.101."],
        "priority_domains": [
            "cm.090227.xyz",
            "mobile.cloudflare.1874.fun",
            "cf-cm.090227.xyz",
            "icook.hk",
            "icook.tw",
            "singapore.com",
            "japan.com",
            "freeyx.cloudflare88.eu.org",
            "ip.sb",
            "time.is",
        ],
    },
    "3": {
        "name": "中国联通 (China Unicom)",
        "desc": "美西直连 / 亚洲软银 AS4837 节点",
        "vps789_key": "CU",
        "ipdb_types": ["bestcf", "bestproxy"],
        "extra_api_urls": [
            "https://cf.090227.xyz/cu?ips=20",
        ],
        "ping_threshold": 260.0,
        "priority_prefixes": ["104.16.", "104.17.", "104.28.", "172.67.", "104.21."],
        "priority_domains": [
            "cu.090227.xyz",
            "unicom.cloudflare.1874.fun",
            "cf-cu.090227.xyz",
            "skk.moe",
            "shopify.com",
            "speed.cloudflare.com",
        ],
    },
    "4": {
        "name": "三网全量 / 综合通用 (Universal)",
        "desc": "聚合三网在线 API 与全量 1000+ 节点库",
        "vps789_key": "AllAvg",
        "ipdb_types": ["bestcf", "bestproxy"],
        "extra_api_urls": [
            "https://cf.090227.xyz/ct?ips=10",
            "https://cf.090227.xyz/cu?ips=10",
            "https://cf.090227.xyz/cmcc?ips=10",
        ],
        "ping_threshold": 280.0,
        "priority_prefixes": [],
        "priority_domains": [
            "cloudflare.1874.fun",
            "cf.090227.xyz",
            "cdn.cloudflare.net",
            "shopify.com",
            "speed.cloudflare.com",
        ],
    }
}


def get_output_dir():
    """
    获取输出目录：
    - Android Termux: 优先保存到 /sdcard/CF-CDN/（手机文件管理器直接可见）
    - 其他系统: 保存到当前脚本目录
    """
    if os.path.exists("/sdcard"):
        out_dir = "/sdcard/CF-CDN"
        try:
            os.makedirs(out_dir, exist_ok=True)
            test_file = os.path.join(out_dir, ".test_write")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return out_dir
        except Exception:
            pass
    return SCRIPT_DIR


def is_valid_target(item):
    """验证是否为合法的 IP 或域名"""
    s = str(item).strip()
    if not s or s.startswith("#"):
        return False
    # IPv4
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', s):
        parts = [int(p) for p in s.split('.')]
        return all(0 <= p <= 255 for p in parts)
    # IPv6
    if ':' in s and re.match(r'^[0-9a-fA-F:]+$', s):
        return True
    # 域名（排除带有 MB, KB, ms 等非域名杂质）
    if re.match(r'^[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+\.?$', s):
        if not any(s.lower().endswith(ext) for ext in ['.mb', '.kb', '.ms', '.b/s', '.b']):
            return True
    return False


def fetch_online_apis(isp_key):
    """
    多源在线 API 自动抓取与解析：
      1. vps789.com (Token 授权):
         - https://vps789.com/openApi/cfIpApi?token=xxx -> 提取 CT/CM/CU/AllAvg 专属库
         - https://vps789.com/openApi/cfIpTop20?token=xxx -> 提取全网 Top20 优选池
      2. ipdb.api.030101.xyz (https://ipdb.api.030101.xyz/?type=bestcf;bestproxy) -> 提取 030101 优选
      3. cf.090227.xyz (https://cf.090227.xyz/...) -> 补充三网实时 IP
    """
    cfg = ISP_CONFIG[isp_key]
    online_ips = []
    seen = set()

    def add_target(target):
        t = str(target).strip()
        if is_valid_target(t) and t.lower() not in seen:
            seen.add(t.lower())
            online_ips.append(t)

    print("\n[+] 正在自动同步各大在线 API 优选数据库......")

    # ---- 1. vps789.com Token 授权 API ----
    # 1.1 专属分类库 (CT / CM / CU / AllAvg)
    try:
        url_vps_api = f"https://vps789.com/openApi/cfIpApi?token={VPS789_TOKEN}"
        req = urllib.request.Request(url_vps_api, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='ignore'))
            if data.get("code") == 0:
                vps_key = cfg.get("vps789_key", "AllAvg")
                vps_data = data.get("data", {})
                count = 0
                if isp_key == "4":
                    for k in ["CT", "CM", "CU", "AllAvg"]:
                        for item in vps_data.get(k, []):
                            if "ip" in item:
                                add_target(item["ip"])
                                count += 1
                else:
                    for item in vps_data.get(vps_key, []):
                        if "ip" in item:
                            add_target(item["ip"])
                            count += 1
                print(f" [✔] [vps789.com] 成功同步 {count} 个 [{vps_key}] 专属优选节点")
    except Exception:
        print(" [-] [vps789.com cfIpApi] 接口连接超时，自动跳过")

    # 1.2 全网 Top20 优选池
    try:
        url_vps_top = f"https://vps789.com/openApi/cfIpTop20?token={VPS789_TOKEN}"
        req = urllib.request.Request(url_vps_top, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='ignore'))
            if data.get("code") == 0:
                top_items = data.get("data", {}).get("good", [])
                top_count = 0
                for item in top_items:
                    if "ip" in item:
                        add_target(item["ip"])
                        top_count += 1
                print(f" [✔] [vps789.com] 成功同步 {top_count} 个 Top20 全网优质节点")
    except Exception:
        pass

    # ---- 2. ipdb.api.030101.xyz API ----
    try:
        types_str = ";".join(cfg.get("ipdb_types", ["bestcf", "bestproxy"]))
        url_ipdb = f"https://ipdb.api.030101.xyz/?type={types_str}"
        req = urllib.request.Request(url_ipdb, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            count = 0
            for line in content.splitlines():
                ip = line.strip()
                if is_valid_target(ip):
                    add_target(ip)
                    count += 1
            print(f" [✔] [ipdb.api.030101.xyz] 成功同步 {count} 个优选官方/反代节点")
    except Exception:
        print(" [-] [ipdb.api.030101.xyz] 接口连接超时，自动跳过")

    # ---- 3. cf.090227.xyz 补充 API ----
    for url in cfg.get("extra_api_urls", []):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                content = resp.read().decode('utf-8', errors='ignore')
                for line in content.splitlines():
                    ip = line.strip()
                    if is_valid_target(ip):
                        add_target(ip)
        except Exception:
            pass

    if online_ips:
        print(f"[✔] 在线 API 聚合去重完成，共获得 {len(online_ips)} 个高优先级实时在线节点！")
    else:
        print("[-] 在线 API 暂未返回数据，将直接使用本地专属节点库。")

    return online_ips


def load_candidate_nodes(isp_key, limit=None):
    """根据运营商选择加载匹配的节点库（在线 API + 本地专属）"""
    cfg = ISP_CONFIG[isp_key]
    candidates = []
    seen = set()

    # 1. 优先加入专属优质域名
    for d in cfg.get("priority_domains", []):
        if d.lower() not in seen:
            seen.add(d.lower())
            candidates.append(d)

    # 2. 动态拉取在线 API (vps789.com + 030101.xyz + 090227)
    api_ips = fetch_online_apis(isp_key)
    for ip in api_ips:
        if ip.lower() not in seen:
            seen.add(ip.lower())
            candidates.append(ip)

    # 3. 读取本地 domains.txt (带运营商网段优先级)
    if os.path.exists(DOMAIN_FILE):
        prefixes = cfg.get("priority_prefixes", [])
        priority_local = []
        normal_local = []

        with open(DOMAIN_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                item = line.strip()
                if not is_valid_target(item) or item.lower() in seen:
                    continue

                if prefixes and any(item.startswith(pfx) for pfx in prefixes):
                    priority_local.append(item)
                else:
                    normal_local.append(item)

        for item in priority_local:
            if item.lower() not in seen:
                seen.add(item.lower())
                candidates.append(item)

        for item in normal_local:
            if item.lower() not in seen:
                seen.add(item.lower())
                candidates.append(item)

    if limit and len(candidates) > limit:
        candidates = candidates[:limit]

    return candidates


def ping_domain(domain):
    """底层调用系统 ping 发送 3 个包，解析平均延迟 (avg ms)"""
    is_win = platform.system().lower() == "windows"
    is_ipv6 = ":" in domain

    if is_win:
        cmd = ["ping", "-6" if is_ipv6 else "-4", "-n", "3", "-w", "1000", domain]
    else:
        cmd = ["ping6" if is_ipv6 else "ping", "-c", "3", "-W", "1", domain]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4)
        output = res.stdout

        if is_win:
            match = re.search(r'(?:平均|Average)\s*=\s*(\d+)ms', output)
            if match:
                avg = float(match.group(1))
                print(f"[Ping] {domain:<32} 平均延迟: {avg:5.1f} ms")
                return (avg, domain)
        else:
            match = re.search(r'rtt min/avg/max/[^=]+=\s*[\d\.]+/([\d\.]+)/', output)
            if match:
                avg = float(match.group(1))
                print(f"[Ping] {domain:<32} 平均延迟: {avg:5.1f} ms")
                return (avg, domain)
            match_alt = re.search(r'round-trip min/avg/max = [\d\.]+/([\d\.]+)/', output)
            if match_alt:
                avg = float(match_alt.group(1))
                print(f"[Ping] {domain:<32} 平均延迟: {avg:5.1f} ms")
                return (avg, domain)
    except Exception:
        pass

    print(f"[Ping] {domain:<32} 超时/不可达")
    return None


def test_download_speed_single(item, duration=2.5):
    """
    单节点真·下载带宽测速 (MB/s)
    采用 Cloudflare 官方真实数据流测速机制 + SNI / Host 伪装，完美解决纯 IP 报错与小文件测速失真
    """
    avg, domain = item
    speed_mb = 0.0

    # 策略 1: 针对 Cloudflare Anycast IP 与官方/反代域名，发起官方速度流下载
    try:
        addr_info = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
        if addr_info:
            target_ip = addr_info[0][4][0]
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            sock = socket.create_connection((target_ip, 443), timeout=3.0)
            ssock = ctx.wrap_socket(sock, server_hostname='speed.cloudflare.com')

            conn = http.client.HTTPSConnection(target_ip, port=443, context=ctx, timeout=3.0)
            conn.sock = ssock
            conn.request('GET', '/__down?bytes=50000000', headers={'Host': 'speed.cloudflare.com', 'User-Agent': 'Mozilla/5.0'})
            resp = conn.getresponse()

            if resp.status == 200:
                downloaded = 0
                start_t = time.time()
                while time.time() - start_t < duration:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                elapsed = time.time() - start_t
                conn.close()
                if elapsed > 0 and downloaded > 0:
                    speed_mb = (downloaded / (1024 * 1024)) / elapsed
                    speed_mb = round(speed_mb, 2)
            else:
                conn.close()
    except Exception:
        pass

    # 策略 2: 如果策略 1 未测出（例如自定义第三方反代站或特殊域名），回退为常规根路径测速
    if speed_mb <= 0.0 and not (domain.replace('.', '').isdigit() or ':' in domain):
        try:
            req = urllib.request.Request(
                f"https://{domain}/",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept-Encoding": "identity"
                }
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            start_t = time.time()
            downloaded = 0
            with urllib.request.urlopen(req, context=ctx, timeout=duration + 2) as resp:
                while time.time() - start_t < duration:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
            elapsed = time.time() - start_t
            if elapsed > 0 and downloaded > 0:
                speed_mb = round((downloaded / (1024 * 1024)) / elapsed, 2)
        except Exception:
            pass

    if speed_mb > 0.0:
        print(f"[下载测速] {domain:<32} -> {speed_mb:5.2f} MB/s (延迟: {avg:5.1f}ms)")
        return (speed_mb, avg, domain)
    else:
        print(f"[下载测速] {domain:<32} ->  0.00 MB/s (测速无响应)")
        return (0.0, avg, domain)


def categorize_results(results):
    """
    根据测速数据进行智能分类（每类精选 Top 4，互不重复）
    1. 综合最佳优选 (Top 4)
    2. 高带宽 / 大流量优选 (Top 4)
    3. 极低延迟优选 (Top 4)
    """
    best_list = []
    bandwidth_list = []
    latency_list = []
    used_domains = set()

    # 1. 综合最佳优选：按速度降序，排除极端高延迟 (>320ms) 的节点，选取 Top 4
    sorted_by_speed = sorted(results, key=lambda x: (-x[0], x[1]))
    for item in sorted_by_speed:
        if len(best_list) >= 4:
            break
        speed, avg, domain = item
        if avg <= 320.0 and domain not in used_domains:
            best_list.append(item)
            used_domains.add(domain)

    # 2. 高带宽 / 大流量优选：在剩余节点中取纯速度最高 Top 4
    for item in sorted_by_speed:
        if len(bandwidth_list) >= 4:
            break
        speed, avg, domain = item
        if domain not in used_domains:
            bandwidth_list.append(item)
            used_domains.add(domain)

    # 3. 极低延迟优选：在剩余节点中按延迟升序取 Top 4
    sorted_by_latency = sorted(results, key=lambda x: (x[1], -x[0]))
    for item in sorted_by_latency:
        if len(latency_list) >= 4:
            break
        speed, avg, domain = item
        if domain not in used_domains:
            latency_list.append(item)
            used_domains.add(domain)

    return best_list, bandwidth_list, latency_list


def main():
    out_dir = get_output_dir()
    current_out = os.path.join(out_dir, OUTPUT_FILE)
    current_clean_out = os.path.join(out_dir, OUTPUT_CLEAN_FILE)

    print("\n" + "=" * 60)
    print(" 🚀 CF-CDN 智能多网/多运营商 Cloudflare 真·测速工具")
    print("=" * 60)
    print("\n 请选择你的宽带运营商（针对性优化路由与丢包）：\n")
    print("  1️⃣  中国电信 (China Telecom) -> 优选美西直连/大带宽抗丢包节点")
    print("  2️⃣  中国移动 (China Mobile)   -> 优选香港/新加坡/亚洲CMI低延迟节点")
    print("  3️⃣  中国联通 (China Unicom)   -> 优选美西/日本软银4837节点")
    print("  4️⃣  三网全量 / 综合通用测速   -> 包含全部节点库与三网在线API")
    print("")

    while True:
        try:
            isp_choice = input(" 请输入运营商编号 1 / 2 / 3 / 4 (默认: 4 全网通用): ").strip()
        except (EOFError, KeyboardInterrupt):
            isp_choice = "4"
        if isp_choice in ("1", "2", "3", "4"):
            break
        elif isp_choice == "":
            isp_choice = "4"
            break
        else:
            print(" ⚠️  请输入 1、2、3 或 4")

    selected_isp = ISP_CONFIG[isp_choice]

    print("\n" + "-" * 60)
    print(f" 已选择: 【{selected_isp['name']}】({selected_isp['desc']})")
    print("-" * 60)

    print("\n 请选择测速并发模式：\n")
    print("  1️⃣  极速模式  - Ping 30线程 + 下载 15线程 (适合旗舰设备/电脑，测速最快)")
    print("  2️⃣  稳定模式  - Ping 12线程 + 下载 6线程  (适合普通手机，防系统强杀) [推荐]")
    print("  3️⃣  精简快测  - 仅测试前 50 个高优先级精选节点 (1 分钟极速出结果)")
    print("")

    limit_count = None
    while True:
        try:
            mode_choice = input(" 请输入模式编号 1 / 2 / 3 (默认: 2 稳定模式): ").strip()
        except (EOFError, KeyboardInterrupt):
            mode_choice = "2"
        if mode_choice == "1":
            ping_workers, download_workers = 30, 15
            mode_name = "极速模式"
            break
        elif mode_choice == "" or mode_choice == "2":
            ping_workers, download_workers = 12, 6
            mode_name = "稳定模式"
            break
        elif mode_choice == "3":
            ping_workers, download_workers = 15, 8
            limit_count = 50
            mode_name = "精简快测模式"
            break
        else:
            print(" ⚠️  请输入 1、2 或 3")

    # 1. 动态拉取在线 API + 加载节点
    nodes = load_candidate_nodes(isp_choice, limit=limit_count)
    if not nodes:
        print("[!] 错误: 未能加载到有效节点，请检查网络或 domains.txt 文件。")
        return

    print("\n" + "=" * 60)
    print(f" 🚀 [{selected_isp['name']}] [{mode_name}] 共载入 {len(nodes)} 个候选节点")
    print(f" 并发参数: Ping {ping_workers} 线程 / 下载 {download_workers} 线程")
    print("=" * 60)
    print(" 阶段一：正在进行高并发 Ping 延迟与丢包探测 (取 3 次平均值)......\n")

    # 2. 阶段一：Ping 延迟过滤
    ping_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=ping_workers) as executor:
        futures = [executor.submit(ping_domain, node) for node in nodes]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                ping_results.append(res)

    if not ping_results:
        print("\n[!] 未能探测到任何可 Ping 通节点，请检查本地网络连接。")
        return

    ping_results.sort(key=lambda x: x[0])
    threshold = selected_isp["ping_threshold"]

    # 根据运营商专属门槛筛选进入阶段二的候选节点
    top_candidates = [item for item in ping_results if item[0] <= threshold]
    if len(top_candidates) < 10:
        top_candidates = ping_results[:25]
    elif len(top_candidates) > 60:
        top_candidates = top_candidates[:60]

    print("\n" + "=" * 60)
    print(f" 阶段二：精选出 {len(top_candidates)} 个有效候选节点，正在并发测试真实下载带宽 (MB/s)......")
    print("=" * 60 + "\n")

    # 3. 阶段二：真实下载测速
    final_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=download_workers) as executor:
        futures = [executor.submit(test_download_speed_single, item) for item in top_candidates]
        for future in concurrent.futures.as_completed(futures):
            speed, avg, domain = future.result()
            if speed > 0.0:
                final_results.append((speed, avg, domain))

    if not final_results:
        print("\n[!] 提示: 本轮未测得有效下载带宽节点，可能是晚高峰网络波动，建议稍后重试。")
        return

    # 4. 智能分类
    best_list, bandwidth_list, latency_list = categorize_results(final_results)

    # 5. 详细数据表格视图
    print("\n" + "=" * 60)
    print(f" 📊 测速结果详细数据 (已为你精选出 {len(final_results)} 个高速节点):")
    print("=" * 60)
    for speed, avg, domain in sorted(final_results, key=lambda x: (-x[0], x[1])):
        print(f"  {domain:<35} | 带宽: {speed:5.2f} MB/s | 延迟: {avg:5.1f} ms")

    # 6. 按分类及纯域名/IP 列表输出（方便直接复制）
    print("\n" + "=" * 60)
    print(" 📋 按分类纯节点列表整理如下，方便直接长按复制：")
    print("=" * 60 + "\n")

    print("一、 综合最佳优选")
    for s, a, d in best_list:
        print(d)
    print("")

    print("二、 高带宽 / 大流量优选")
    for s, a, d in bandwidth_list:
        print(d)
    print("")

    print("三、 极低延迟优选")
    for s, a, d in latency_list:
        print(d)
    print("")

    print("=" * 60)

    # 7. 保存文件
    out_lines = []
    clean_lines = []

    out_lines.append(f"# CF-CDN 测速结果 [{selected_isp['name']}] - {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    out_lines.append("一、 综合最佳优选\n")
    for s, a, d in best_list:
        out_lines.append(f"{s:.2f} MB/s | {a:.1f} ms : {d}\n")
        clean_lines.append(f"{d}\n")
    out_lines.append("\n二、 高带宽 / 大流量优选\n")
    for s, a, d in bandwidth_list:
        out_lines.append(f"{s:.2f} MB/s | {a:.1f} ms : {d}\n")
        clean_lines.append(f"{d}\n")
    out_lines.append("\n三、 极低延迟优选\n")
    for s, a, d in latency_list:
        out_lines.append(f"{s:.2f} MB/s | {a:.1f} ms : {d}\n")
        clean_lines.append(f"{d}\n")

    with open(current_out, "w", encoding="utf-8") as f:
        f.writelines(out_lines)

    with open(current_clean_out, "w", encoding="utf-8") as f:
        f.writelines(clean_lines)

    print("\n" + "-" * 60)
    print(" 💡 客户端填法防坑指引：")
    print("  • 【连接地址 / Address】：填上方测出来的优选 IP 或优选域名")
    print("  • 【伪装域名 / Host / SNI】：必须填你自己节点的真实域名（保证证书有效）")
    print("  • 【端口 / Port】：支持 443 / 8443 / 2053 / 2083 / 2087 / 2096 等")
    print(f"\n 📁 结果已自动保存到:")
    print(f"  📌 纯节点列表: {current_clean_out}")
    print(f"  📌 详细速度表: {current_out}")
    print("-" * 60 + "\n")


if __name__ == "__main__":
    main()

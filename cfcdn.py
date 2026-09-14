#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CF-CDN 智能多网/多运营商 Cloudflare CDN 真实带宽与延迟测速 & 分析工具
特别针对 Android Termux 手机环境深度调优
原生集成 youxuanIP-analysis 智能分类算法
支持 Android Termux / Linux / macOS / Windows

Termux 专属特性：
  1. 深度集成 youxuanIP-analysis 纯文本规范输出（手机端长按即可整段复制）
  2. 支持 Termux:API 自动写入手机系统剪贴板（无需手动框选）
  3. 自动同步保存到手机内部存储 /sdcard/CF-CDN/（手机文件管理器直接打开）
  4. 多源动态在线 API 自动同步（vps789.com + ipdb.api.030101.xyz + 090227.xyz）
  5. 内存与并发控制（防 Android 系统 OOM 强杀）
  6. 支持“真·测速模式”与“导入已有测速文件分析模式”双模运行
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
E2E_CONFIG_FILE = os.path.join(SCRIPT_DIR, "mynode.ini")

# vps789 API 授权 Token（优先取环境变量 VPS789_TOKEN，未设置时用内置的免费公共 token）
VPS789_TOKEN = os.environ.get("VPS789_TOKEN") or "1V1B837SN4VBG42SC1X83DHJ0SMTR8SK"

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
        "ping_threshold": 350.0,
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
        "ping_threshold": 160.0,
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


def try_copy_to_clipboard(text):
    """在 Android Termux 下尝试调用系统剪贴板"""
    try:
        res = subprocess.run(["which", "termux-clipboard-set"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0:
            p = subprocess.Popen(["termux-clipboard-set"], stdin=subprocess.PIPE)
            p.communicate(input=text.encode("utf-8"))
            return True
    except Exception:
        pass
    return False


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
    # 域名
    if re.match(r'^[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+\.?$', s):
        if not any(s.lower().endswith(ext) for ext in ['.mb', '.kb', '.ms', '.b/s', '.b']):
            return True
    return False


def load_e2e_config():
    """读取端到端真实链路测速配置 mynode.ini（私有文件，已被 .gitignore 忽略）

    格式：
        domain=你的域名
        path=/test.bin
    配置存在且合法时，下载测速改为「候选IP + 你的域名作 SNI/Host」拉取你自己
    VPS 上的文件，测出 手机→CF边缘→回源VPS 完整链路的真实速度。
    """
    if not os.path.exists(E2E_CONFIG_FILE):
        return None
    domain = None
    path = "/test.bin"
    try:
        with open(E2E_CONFIG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key, val = key.strip().lower(), val.strip()
                if key == "domain" and val:
                    domain = re.sub(r'^https?://', '', val).split("/")[0]
                elif key == "path" and val:
                    path = val if val.startswith("/") else "/" + val
    except Exception:
        return None
    if domain and is_valid_target(domain):
        return (domain, path)
    return None


def fetch_online_apis(isp_key):
    """多源在线 API 自动抓取与解析"""
    cfg = ISP_CONFIG[isp_key]
    online_ips = []
    seen = set()

    def add_target(target):
        t = str(target).strip()
        if is_valid_target(t) and t.lower() not in seen:
            seen.add(t.lower())
            online_ips.append(t)

    print("\n[+] 正在自动同步各大在线 API 优选数据库......")

    # 1. vps789.com Token 授权 API
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

    # 2. ipdb.api.030101.xyz API
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

    # 3. cf.090227.xyz 补充 API
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
    """根据运营商选择加载匹配的节点库"""
    cfg = ISP_CONFIG[isp_key]
    candidates = []
    seen = set()

    for d in cfg.get("priority_domains", []):
        if d.lower() not in seen:
            seen.add(d.lower())
            candidates.append(d)

    api_ips = fetch_online_apis(isp_key)
    for ip in api_ips:
        if ip.lower() not in seen:
            seen.add(ip.lower())
            candidates.append(ip)

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


def test_download_speed_single(item, duration=2.5, e2e=None):
    """单节点真·下载带宽测速 (MB/s)

    e2e=(domain, path) 时启用端到端模式：SNI/Host 换成你自己的域名，
    下载你 VPS 上的文件，测的是 手机→CF边缘→回源VPS 的完整真实链路。
    """
    avg, domain = item
    speed_mb = 0.0

    if e2e:
        sni, path = e2e
        # 固定纯字母参数：绕开 CF 边缘可能残留的旧 301 缓存，同时避开 WAF 对特殊符号的拦截
        sep = "&" if "?" in path else "?"
        req_path = f"{path}{sep}bypass=cfcdn"
        # Range 限 30MB：候选多时防止把手机流量跑爆；206 = Range 命中，同样算成功
        req_headers = {'Host': sni, 'User-Agent': 'Mozilla/5.0', 'Range': 'bytes=0-31457279'}
    else:
        sni = "speed.cloudflare.com"
        req_path = "/__down?bytes=50000000"
        req_headers = {'Host': sni, 'User-Agent': 'Mozilla/5.0'}

    try:
        addr_info = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
        if addr_info:
            target_ip = addr_info[0][4][0]
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            sock = socket.create_connection((target_ip, 443), timeout=5.0)
            ssock = ctx.wrap_socket(sock, server_hostname=sni)

            conn = http.client.HTTPSConnection(target_ip, port=443, context=ctx, timeout=5.0)
            conn.sock = ssock
            conn.request('GET', req_path, headers=req_headers)
            resp = conn.getresponse()

            if resp.status in (200, 206):
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

    if speed_mb <= 0.0 and e2e is None and not (domain.replace('.', '').isdigit() or ':' in domain):
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


# ================= youxuanIP-analysis 核心算法与格式生成 =================

def run_youxuan_analysis(results):
    """
    youxuanIP-analysis 核心算法实现：
      - 综合最佳优选 (Top 4): 速度降序，排除 >300ms，顺延补齐
      - 高带宽 / 大流量优选 (Top 4): 排除已用，速度降序
      - 极低延迟优选 (Top 4): 排除已用，延迟 <100ms -> <150ms -> 顺延补齐
      - 三个类别之间域名互不重复
    """
    best_list = []
    bandwidth_list = []
    latency_list = []
    used_domains = set()

    # 1. 综合最佳优选：按速度从高到低排序，选取 Top4 域名。同时兼顾延迟，若延迟过高（>300ms）则顺延下一个。
    by_speed = sorted(results, key=lambda x: (-x[0], x[1]))
    for item in by_speed:
        if len(best_list) >= 4:
            break
        speed, avg, domain = item
        if avg <= 300.0 and domain not in used_domains:
            best_list.append(item)
            used_domains.add(domain)

    # 若不足 4 个则顺延补齐
    if len(best_list) < 4:
        for item in by_speed:
            if len(best_list) >= 4:
                break
            if item[2] not in used_domains:
                best_list.append(item)
                used_domains.add(item[2])

    # 2. 高带宽 / 大流量优选：排除综合最佳已用的域名后，选取速度排名 Top4 的域名。
    for item in by_speed:
        if len(bandwidth_list) >= 4:
            break
        if item[2] not in used_domains:
            bandwidth_list.append(item)
            used_domains.add(item[2])

    # 3. 极低延迟优选：排除已用域名后，按延迟从低到高排序，选取延迟 <100ms 的域名 Top4。如果不足4个则放宽到 <150ms 补齐，仍不足顺延。
    by_latency = sorted(results, key=lambda x: (x[1], -x[0]))
    # 第一梯队: < 100ms
    for item in by_latency:
        if len(latency_list) >= 4:
            break
        if item[1] < 100.0 and item[2] not in used_domains:
            latency_list.append(item)
            used_domains.add(item[2])

    # 第二梯队: < 150ms
    if len(latency_list) < 4:
        for item in by_latency:
            if len(latency_list) >= 4:
                break
            if item[1] < 150.0 and item[2] not in used_domains:
                latency_list.append(item)
                used_domains.add(item[2])

    # 第三梯队: 任意剩余
    if len(latency_list) < 4:
        for item in by_latency:
            if len(latency_list) >= 4:
                break
            if item[2] not in used_domains:
                latency_list.append(item)
                used_domains.add(item[2])

    return best_list, bandwidth_list, latency_list


def format_skill_output(best_list, bandwidth_list, latency_list):
    """严格按照 youxuanIP-analysis Skill 模板生成纯文本输出"""
    lines = []
    lines.append("按分类及纯域名列表整理如下，方便直接复制：\n")
    lines.append("一、 综合最佳优选\n")
    for s, a, d in best_list:
        lines.append(d)
    lines.append("\n二、 高带宽 / 大流量优选\n")
    for s, a, d in bandwidth_list:
        lines.append(d)
    lines.append("\n三、 极低延迟优选\n")
    for s, a, d in latency_list:
        lines.append(d)

    return "\n".join(lines)


def analyze_existing_file(file_path):
    """解析已有测速 txt 文件的分析模式"""
    if not os.path.exists(file_path):
        print(f"\n[错误] 文件未找到: {file_path}")
        return

    print(f"\n[+] 正在读取并分析测速数据文件: {file_path} ......")

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    pattern = re.compile(r'([\d\.]+)\s*MB/s\s*\|\s*([\d\.]+)\s*ms\s*[:：]\s*(\S+)')
    parsed_results = []
    for line in content.splitlines():
        m = pattern.search(line)
        if m:
            speed = float(m.group(1))
            latency = float(m.group(2))
            domain = m.group(3).strip()
            parsed_results.append((speed, latency, domain))

    if not parsed_results:
        print("[!] 错误: 文件内容不符合 `速度 MB/s | 延迟 ms : 域名` 测速格式，无法解析。")
        return

    print(f"[✔] 成功解析出 {len(parsed_results)} 条有效测速数据！\n")

    best_list, bandwidth_list, latency_list = run_youxuan_analysis(parsed_results)
    skill_text = format_skill_output(best_list, bandwidth_list, latency_list)

    print("=" * 60)
    print(skill_text)
    print("=" * 60)

    # 自动写入剪贴板（Termux:API）
    if try_copy_to_clipboard(skill_text):
        print("\n [📋] 已自动将上述分类纯节点复制到手机剪贴板！可以直接去粘贴使用。")

    # 导出到文件
    out_dir = get_output_dir()
    clean_out = os.path.join(out_dir, "CDNym_clean.txt")
    with open(clean_out, "w", encoding="utf-8") as f:
        f.write(skill_text + "\n")

    print(f"\n[✔] 分析结果已保存到: {clean_out}")


def main():
    # 检查是否有命令行参数（直接分析文件）
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--analyze" and len(sys.argv) > 2:
            analyze_existing_file(sys.argv[2])
            return
        elif os.path.isfile(arg):
            analyze_existing_file(arg)
            return

    out_dir = get_output_dir()
    current_out = os.path.join(out_dir, OUTPUT_FILE)
    current_clean_out = os.path.join(out_dir, OUTPUT_CLEAN_FILE)

    print("\n" + "=" * 60)
    print(" 🚀 CF-CDN 智能多网测速 & youxuanIP-analysis 综合工具")
    print(" 📱 Termux 手机环境专属调优版 (支持一键复制与存储直读)")
    print("=" * 60)
    print("\n 请选择功能模式：\n")
    print("  1️⃣  中国电信 (China Telecom) -> 优选美西直连/大带宽抗丢包节点")
    print("  2️⃣  中国移动 (China Mobile)   -> 优选香港/新加坡/亚洲CMI低延迟节点")
    print("  3️⃣  中国联通 (China Unicom)   -> 优选美西/日本软银4837节点")
    print("  4️⃣  三网全量 / 综合通用测速   -> 包含全部节点库与三网在线API")
    print("  5️⃣  导入已有测速文件进行分析 (youxuanIP-analysis 模式)")
    print("  6️⃣  VLESS 订阅节点真实测速与重排 (移动/电信/直连/全量 · 写入剪贴板)")
    print("")

    while True:
        try:
            choice = input(" 请输入选项编号 1 / 2 / 3 / 4 / 5 / 6 (默认: 4 全网通用): ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "4"
        if choice in ("1", "2", "3", "4", "5", "6"):
            break
        elif choice == "":
            choice = "4"
            break
        else:
            print(" ⚠️  请输入 1、2、3、4、5 或 6")

    # 如果选 6: VLESS 订阅节点测速与重排模式
    if choice == "6":
        try:
            import sub_speedtest
            sub_speedtest.main()
        except ImportError:
            sys.path.insert(0, SCRIPT_DIR)
            import sub_speedtest
            sub_speedtest.main()
        return

    # 如果选 5: 文件分析模式
    if choice == "5":
        try:
            default_file = os.path.join(out_dir, OUTPUT_FILE)
            prompt_file = f" 请输入测速 txt 文件路径 (默认: {default_file}): "
            f_path = input(prompt_file).strip()
            if not f_path:
                f_path = default_file
            analyze_existing_file(f_path)
            return
        except (EOFError, KeyboardInterrupt):
            return

    selected_isp = ISP_CONFIG[choice]

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

    # 端到端真实链路测速：检测到 mynode.ini 时，可改用「候选IP + 你的域名」
    # 下载你自己 VPS 上的文件，测出 手机→CF→你VPS 的完整真实速度
    e2e_target = None
    e2e_cfg = load_e2e_config()
    if e2e_cfg:
        print(f"\n 检测到私有配置 mynode.ini: {e2e_cfg[0]}{e2e_cfg[1]}")
        print(" 端到端模式 = 通过候选IP下载你自己VPS上的文件（真实使用路径）")
        try:
            ans = input(" 是否启用端到端真实链路测速？Y/n (默认: Y): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans in ("", "y", "yes"):
            e2e_target = e2e_cfg
            print(" ✔ 已启用端到端模式，单节点测速 8 秒（测持续吞吐，非瞬时峰值）")
        else:
            print(" ↩ 已跳过，仍使用 Cloudflare 官方测速文件")

    # 1. 动态拉取在线 API + 加载节点
    nodes = load_candidate_nodes(choice, limit=limit_count)
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

    top_candidates = [item for item in ping_results if item[0] <= threshold]
    if len(top_candidates) < 10:
        top_candidates = ping_results[:25]
    elif len(top_candidates) > 60:
        top_candidates = top_candidates[:60]

    # 端到端模式下载的是自家 VPS 的真实文件，候选举 30 个封顶，控制总流量
    if e2e_target and len(top_candidates) > 30:
        top_candidates = top_candidates[:30]

    print("\n" + "=" * 60)
    print(f" 阶段二：精选出 {len(top_candidates)} 个有效候选节点，正在并发测试真实下载带宽 (MB/s)......")
    print("=" * 60 + "\n")

    # 3. 阶段二：真实下载测速
    final_results = []
    dl_duration = 8.0 if e2e_target else 2.5
    with concurrent.futures.ThreadPoolExecutor(max_workers=download_workers) as executor:
        futures = [executor.submit(test_download_speed_single, item, dl_duration, e2e_target) for item in top_candidates]
        for future in concurrent.futures.as_completed(futures):
            speed, avg, domain = future.result()
            if speed > 0.0:
                final_results.append((speed, avg, domain))

    if not final_results:
        print("\n[!] 提示: 本轮未测得有效下载带宽节点，可能是晚高峰网络波动，建议稍后重试。")
        return

    # 4. youxuanIP-analysis 智能分类
    best_list, bandwidth_list, latency_list = run_youxuan_analysis(final_results)

    # 5. 详细数据表格视图
    print("\n" + "=" * 60)
    print(f" 📊 测速结果详细数据 (已为你精选出 {len(final_results)} 个高速节点):")
    print("=" * 60)
    for speed, avg, domain in sorted(final_results, key=lambda x: (-x[0], x[1])):
        print(f"  {domain:<35} | 带宽: {speed:5.2f} MB/s | 延迟: {avg:5.1f} ms")

    # 6. youxuanIP-analysis 标准纯文本输出
    skill_output_text = format_skill_output(best_list, bandwidth_list, latency_list)

    print("\n" + "=" * 60)
    print(skill_output_text)
    print("=" * 60)

    # 自动写入剪贴板（Termux:API）
    if try_copy_to_clipboard(skill_output_text):
        print("\n [📋] 已自动将上述分类纯节点复制到手机剪贴板！可以直接去粘贴使用。")

    # 7. 保存文件
    out_lines = []
    out_lines.append(f"# CF-CDN 测速结果 [{selected_isp['name']}] - {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    out_lines.append("一、 综合最佳优选\n")
    for s, a, d in best_list:
        out_lines.append(f"{s:.2f} MB/s | {a:.1f} ms : {d}\n")
    out_lines.append("\n二、 高带宽 / 大流量优选\n")
    for s, a, d in bandwidth_list:
        out_lines.append(f"{s:.2f} MB/s | {a:.1f} ms : {d}\n")
    out_lines.append("\n三、 极低延迟优选\n")
    for s, a, d in latency_list:
        out_lines.append(f"{s:.2f} MB/s | {a:.1f} ms : {d}\n")

    with open(current_out, "w", encoding="utf-8") as f:
        f.writelines(out_lines)

    with open(current_clean_out, "w", encoding="utf-8") as f:
        f.write(skill_output_text + "\n")

    print("\n" + "-" * 60)
    print(" 💡 客户端填法防坑指引：")
    print("  • 【连接地址 / Address】：填上方测出来的优选 IP 或优选域名")
    print("  • 【伪装域名 / Host / SNI】：必须填你自己节点的真实域名（保证证书有效）")
    print("  • 【端口 / Port】：支持 443 / 8443 / 2053 / 2083 / 2087 / 2096 等")
    print(f"\n 📁 结果已自动保存到手机内部存储（手机文件管理器直接可见）:")
    print(f"  📌 youxuanIP-analysis 标准分类文件: {current_clean_out}")
    print(f"  📌 详细速度报告: {current_out}")
    print("-" * 60 + "\n")


if __name__ == "__main__":
    main()

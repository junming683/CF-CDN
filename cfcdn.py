#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CF-CDN 域名/IP 延迟与真实下载带宽双重测速工具
支持 Android Termux / Linux / macOS / Windows
支持 1000+ 节点、动态 250ms 延迟门槛筛选与多线程 HTTP 下载测速

并发线程配置（防止 Android OOM Killer 强杀进程）:
  - Ping 阶段: 10 线程（稳定，不撑爆内存）
  - 下载测速阶段: 6 线程（稳定，不撑爆内存）
"""

import os
import sys
import re
import time
import platform
import subprocess
import urllib.request
import concurrent.futures

OUTPUT_FILE = "CDNym.txt"
OUTPUT_CLEAN_FILE = "CDNym_clean.txt"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAIN_FILE = os.path.join(SCRIPT_DIR, "domains.txt")


def get_output_dir():
    """
    获取输出目录：
    - Android Termux: 优先保存到 /sdcard/CF-CDN/（用户可在文件管理器中看到）
    - 其他系统: 保存到当前目录
    """
    # 检测是否为 Android Termux 环境
    if os.path.exists("/sdcard"):
        out_dir = "/sdcard/CF-CDN"
        try:
            os.makedirs(out_dir, exist_ok=True)
            # 写一个测试文件验证权限
            test_file = os.path.join(out_dir, ".test_write")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return out_dir
        except Exception:
            pass
    # 回退到脚本所在目录
    return SCRIPT_DIR


def fetch_online_api_ips():
    """尝试从电信/联通/移动 API 接口获取最新动态优选 IP"""
    api_urls = [
        "https://cf.090227.xyz/ct?ips=5",
        "https://cf.090227.xyz/cu?ips=5",
        "https://cf.090227.xyz/cmcc?ips=5",
    ]
    online_ips = []
    print("[+] 正在尝试自动在线获取三网最新动态优选 IP......")
    for url in api_urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                content = resp.read().decode('utf-8')
                for line in content.splitlines():
                    ip = line.strip()
                    if ip and re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                        online_ips.append(ip)
        except Exception:
            pass

    if online_ips:
        print(f"[✔] 成功自动获取 {len(online_ips)} 个在线实时优选 IP！")
    else:
        print("[-] 在线 API 接口暂不可用，使用本地全量域名/IP 库进行测试。")
    return online_ips


def load_domains():
    if not os.path.exists(DOMAIN_FILE):
        print(f"[错误] 未找到域名配置文件: {DOMAIN_FILE}")
        return []
    domains = []

    online_ips = fetch_online_api_ips()
    domains.extend(online_ips)

    with open(DOMAIN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if line not in domains:
                    domains.append(line)
    return domains


def ping_domain(domain):
    """底层调用系统 ping 发送 3 个包，解析 min/avg/max 中的 avg (平均延迟)"""
    is_win = platform.system().lower() == "windows"
    is_ipv6 = ":" in domain

    if is_win:
        cmd = ["ping", "-6" if is_ipv6 else "-4", "-n", "3", domain]
    else:
        cmd = ["ping6" if is_ipv6 else "ping", "-c", "3", domain]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        output = res.stdout

        if is_win:
            match = re.search(r'(?:平均|Average)\s*=\s*(\d+)ms', output)
            if match:
                avg = float(match.group(1))
                print(f"[Ping 测试] {domain:<35} 3次平均延迟: {avg:.1f} ms")
                return (avg, domain)
        else:
            match = re.search(r'rtt min/avg/max/[^=]+=\s*[\d\.]+/([\d\.]+)/', output)
            if match:
                avg = float(match.group(1))
                print(f"[Ping 测试] {domain:<35} 3次平均延迟: {avg:.1f} ms")
                return (avg, domain)
            match_alt = re.search(r'round-trip min/avg/max = [\d\.]+/([\d\.]+)/', output)
            if match_alt:
                avg = float(match_alt.group(1))
                print(f"[Ping 测试] {domain:<35} 3次平均延迟: {avg:.1f} ms")
                return (avg, domain)
    except Exception:
        pass

    print(f"[Ping 测试] {domain:<35} 超时/失败")
    return None


def test_download_speed_single(item, duration=2.5):
    """单节点 HTTP/HTTPS 下载测速"""
    avg, domain = item
    target = f"[{domain}]" if ":" in domain and not domain.startswith("[") else domain
    url = f"https://{target}/"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Encoding": "identity"
        }
    )

    start_time = time.time()
    downloaded = 0
    try:
        with urllib.request.urlopen(req, timeout=duration + 2) as response:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if time.time() - start_time >= duration:
                    break
        elapsed = time.time() - start_time
        if elapsed > 0 and downloaded > 0:
            speed_mbs = (downloaded / (1024 * 1024)) / elapsed
            res_speed = round(speed_mbs, 2)
            print(f"[下载测速] {domain:<35} -> {res_speed:.2f} MB/s (Ping: {avg:.1f}ms)")
            return (res_speed, avg, domain)
    except Exception:
        pass

    print(f"[下载测速] {domain:<35} -> 0.00 MB/s (不可用/超时)")
    return (0.0, avg, domain)


def main():
    out_dir = get_output_dir()
    current_out = os.path.join(out_dir, OUTPUT_FILE)
    current_clean_out = os.path.join(out_dir, OUTPUT_CLEAN_FILE)

    # ---- 模式选择 ----
    print("")
    print("==================================================")
    print(" 🚀 CF-CDN 域名/IP 真·测速工具")
    print("==================================================")
    print("")
    print(" 请选择测速模式：")
    print("")
    print("  1️⃣  极速模式  - Ping 30线程 + 下载 15线程")
    print("      适合: 旗舰手机/平板、内存充足 (>=6GB)")
    print("      注意: 内存不足时可能被系统强杀 (signal 9)")
    print("")
    print("  2️⃣  稳定模式  - Ping 10线程 + 下载 6线程")
    print("      适合: 所有设备，不会被系统强杀")
    print("      注意: 速度较慢，1000+节点约需 5~10 分钟")
    print("")

    while True:
        try:
            choice = input(" 请输入 1 或 2 (默认: 2 稳定模式): ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "2"
        if choice == "1":
            ping_workers = 30
            download_workers = 15
            mode_name = "极速模式"
            break
        elif choice == "" or choice == "2":
            ping_workers = 10
            download_workers = 6
            mode_name = "稳定模式"
            break
        else:
            print(" ⚠️  请输入 1 或 2")

    domains = load_domains()
    print("")
    print("==================================================")
    print(f" 🚀 [{mode_name}] 全量收录 {len(domains)} 个节点 | Ping:{ping_workers}线程 / 下载:{download_workers}线程")
    print("==================================================")
    print(" 阶段一：正在进行海量并发 3 次 Ping 延迟探测 (取平均值)......\n")

    ping_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=ping_workers) as executor:
        futures = [executor.submit(ping_domain, domain) for domain in domains]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                ping_results.append(res)

    if not ping_results:
        print("\n[!] 未能测试到有效节点，请检查网络连接。")
        return

    ping_results.sort(key=lambda x: x[0])

    # 将所有 Ping 平均延迟 <= 250ms 的节点全部纳入阶段二
    top_candidates = [item for item in ping_results if item[0] <= 250.0]
    if not top_candidates:
        top_candidates = ping_results[:30]

    print("\n" + "=" * 50)
    print(f" 阶段二：已匹配到 {len(top_candidates)} 个延迟 <= 250ms 的节点，正在并发进行真实下载测速 (MB/s)......")
    print("=" * 50 + "\n")

    final_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=download_workers) as executor:
        futures = [executor.submit(test_download_speed_single, item) for item in top_candidates]
        for future in concurrent.futures.as_completed(futures):
            speed, avg, domain = future.result()
            if speed > 0.0:
                final_results.append((speed, avg, domain))

    if not final_results:
        print("\n[!] 提示: 暂未测得有效 HTTP 下载速度的节点，请稍后再试。")
        return

    final_results.sort(key=lambda x: (-x[0], x[1]))

    # ---- 详细数据视图 ----
    print("\n" + "=" * 50)
    print(f" 📊 测速结果详细数据 (精选出 {len(final_results)} 个高速可用节点):")
    print("=" * 50)
    for speed, avg, domain in final_results:
        print(f"  {domain:<35} | 速度: {speed:5.2f} MB/s | 延迟: {avg:5.1f} ms")

    # ---- 纯域名/IP 直复制区域（每行一个，行间加空行防止 IM 合并两列）----
    print("\n" + "=" * 50)
    print(f" 📋 纯域名/IP 直复制区域 (共 {len(final_results)} 个高速可用节点):")
    print("=" * 50)

    out_lines = []
    clean_lines = []
    for speed, avg, domain in final_results:
        # 每个域名单独一行，后跟一个空行，确保复制到 IM 时不会两列粘连
        print(domain)
        print()
        out_lines.append(f"{speed:.2f} MB/s | {avg:.1f} ms: {domain}\n")
        clean_lines.append(f"{domain}\n")

    print("=" * 50)

    # ---- 保存文件 ----
    with open(current_out, "w", encoding="utf-8") as f:
        f.writelines(out_lines)

    with open(current_clean_out, "w", encoding="utf-8") as f:
        f.writelines(clean_lines)

    print("\n" + "-" * 50)
    print(f" 💡 提示: 已为您测得 {len(final_results)} 个高速可用节点！")
    print(f" 直接长按框选【纯域名/IP 直复制区域】中的内容复制即可。")
    print(f"\n 📁 文件已保存到（手机文件管理器可直接访问）:")
    print(f"  📌 纯节点文件 : {current_clean_out}")
    print(f"  📌 详细速度文件: {current_out}")
    print("-" * 50 + "\n")


if __name__ == "__main__":
    main()

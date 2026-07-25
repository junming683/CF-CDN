#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CF-CDN 域名/IP 延迟与真实下载带宽双重测速工具
支持 Android Termux / Linux / macOS / Windows
自动支持 IPv4, IPv6 与 域名测速
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

def load_domains():
    if not os.path.exists(DOMAIN_FILE):
        print(f"[错误] 未找到域名配置文件: {DOMAIN_FILE}")
        return []
    domains = []
    with open(DOMAIN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                domains.append(line)
    return domains

def ping_domain(domain):
    """底层调用系统 ping 发送 3 个包，解析 min/avg/max 中的 avg (平均延迟)"""
    is_win = platform.system().lower() == "windows"
    
    # 判断是否为 IPv6 地址
    is_ipv6 = ":" in domain
    if is_win:
        cmd = ["ping", "-6" if is_ipv6 else "-4", "-n", "3", domain]
    else:
        cmd = ["ping6" if is_ipv6 else "ping", "-c", "3", domain]
        
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=6)
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

def test_download_speed(domain, duration=3):
    """测试真实的 HTTP/HTTPS 下载速度 (MB/s)"""
    target = f"[{domain}]" if ":" in domain and not domain.startswith("[") else domain
    url = f"https://{target}/"
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    
    start_time = time.time()
    downloaded = 0
    try:
        with urllib.request.urlopen(req, timeout=duration + 2) as response:
            while True:
                chunk = response.read(32 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if time.time() - start_time >= duration:
                    break
        elapsed = time.time() - start_time
        if elapsed > 0 and downloaded > 0:
            speed_mbs = (downloaded / (1024 * 1024)) / elapsed
            return round(speed_mbs, 2)
    except Exception:
        pass
    return 0.0

def main():
    domains = load_domains()
    print("==================================================")
    print(f" 🚀 CF-CDN 域名/IP 真·测速工具 (共收录 {len(domains)} 个节点)")
    print("==================================================")
    print(" 阶段一：正在并发测试 3 次 Ping 延迟 (取平均值)......\n")
    
    ping_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(ping_domain, domain) for domain in domains]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                ping_results.append(res)
                
    if not ping_results:
        print("\n[!] 未能测试到有效节点，请检查网络连接。")
        return
        
    ping_results.sort(key=lambda x: x[0])
    
    top_candidates = ping_results[:15]
    
    print("\n" + "=" * 50)
    print(" 阶段二：正在对低延迟节点进行真实下载速度测速 (MB/s)......")
    print("=" * 50 + "\n")
    
    final_results = []
    for avg, domain in top_candidates:
        print(f"正在测试 {domain:<35} 实际下载速度...", end="", flush=True)
        speed = test_download_speed(domain, duration=2.5)
        print(f" -> {speed:.2f} MB/s (3次Ping平均: {avg:.1f}ms)")
        if speed > 0.0:
            final_results.append((speed, avg, domain))
            
    if not final_results:
        print("\n[!] 提示: 暂未测得有效 HTTP 下载速度的节点，请稍后再试。")
        return

    # 严格按照【实际下载速度】由高到低降序排序
    final_results.sort(key=lambda x: (-x[0], x[1]))
    
    current_out = os.path.abspath(OUTPUT_FILE)
    current_clean_out = os.path.abspath(OUTPUT_CLEAN_FILE)
    
    print("\n" + "=" * 50)
    print(" 🏆 最终优选排序结果 (已过滤 0 MB/s 节点，仅保留有效高速节点/域名):")
    print("=" * 50)
    
    out_lines = []
    clean_lines = []
    for speed, avg, domain in final_results:
        print(domain)
        out_lines.append(f"{speed:.2f} MB/s | {avg:.1f} ms: {domain}\n")
        clean_lines.append(f"{domain}\n")

    with open(current_out, "w", encoding="utf-8") as f:
        f.writelines(out_lines)

    with open(current_clean_out, "w", encoding="utf-8") as f:
        f.writelines(clean_lines)

    print("\n" + "-" * 50)
    print(f" 提示: 已为您精选出 {len(final_results)} 个【有效可用】的节点，可直接长按复制！")
    print(" 文件保存完整路径如下:")
    print(f"  📌 纯节点/域名文件: {current_clean_out}")
    print(f"  📌 详细速度文件: {current_out}")
    print("-" * 50 + "\n")

if __name__ == "__main__":
    main()

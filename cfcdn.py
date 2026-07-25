#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CF-CDN 域名/IP 延迟与真实下载带宽双重测速工具
支持 Android Termux / Linux / macOS / Windows
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

DEFAULT_DOMAINS = """
# === 1. 企业级/高优先级线路 ===
shopify.com
www.shopify.com
www.visa.com
www.visa.co.jp
www.visa.com.sg
www.visa.com.hk
www.visa.com.tw
www.visakorea.com
www.okcupid.com
www.udacity.com
www.udemy.com
www.digitalocean.com
www.glassdoor.com

# === 2. Cloudflare 官方及基础设施节点 ===
time.cloudflare.com
cloudflare.com
dash.cloudflare.com
developers.cloudflare.com
community.cloudflare.com
blog.cloudflare.com
pages.dev
workers.dev

# === 3. IP/网络工具类 ===
ip.sb
time.is
iplocation.io
www.iplocation.net
whatismyipaddress.com
www.whatismyip.com
www.whoer.net
www.ipchicken.com
download.yunzhongzhuan.com

# === 4. 区域路由节点 ===
singapore.com
japan.com
russia.com
malaysia.com
icook.hk
icook.tw
fbi.gov
www.who.int
www.wto.org
www.gov.ua
gur.gov.ua
www.zsu.gov.ua
www.gco.gov.qa

# === 5. 社区常用及第三方优选域名 ===
skk.moe
www.baipiao.eu.org
log.bpminecraft.com
www.pcmag.com
www.boba88slot.com
www.hugedomains.com
cf.090227.xyz
"""

def init_domain_file():
    if not os.path.exists(DOMAIN_FILE):
        with open(DOMAIN_FILE, "w", encoding="utf-8") as f:
            f.write(DEFAULT_DOMAINS.strip())
        print(f"[提示] 已自动创建默认域名文件: {DOMAIN_FILE}")

def load_domains():
    init_domain_file()
    domains = []
    with open(DOMAIN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                domains.append(line)
    return domains

def ping_domain(domain):
    is_win = platform.system().lower() == "windows"
    cmd = ["ping", "-n" if is_win else "-c", "3", domain]
    
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=6)
        output = res.stdout
        
        if is_win:
            match = re.search(r'(?:平均|Average)\s*=\s*(\d+)ms', output)
            if match:
                avg = float(match.group(1))
                print(f"[Ping 测试] {domain:<30} 延迟: {avg:.1f} ms")
                return (avg, domain)
        else:
            match = re.search(r'rtt min/avg/max/[^=]+=\s*[\d\.]+/([\d\.]+)/', output)
            if match:
                avg = float(match.group(1))
                print(f"[Ping 测试] {domain:<30} 延迟: {avg:.1f} ms")
                return (avg, domain)
            match_alt = re.search(r'round-trip min/avg/max = [\d\.]+/([\d\.]+)/', output)
            if match_alt:
                avg = float(match_alt.group(1))
                print(f"[Ping 测试] {domain:<30} 延迟: {avg:.1f} ms")
                return (avg, domain)
    except Exception:
        pass
        
    print(f"[Ping 测试] {domain:<30} 超时/失败")
    return None

def test_download_speed(domain, duration=3):
    """测试真实的 HTTP 下载速度 (MB/s)"""
    url = f"https://{domain}/"
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
    print(" 阶段一：正在并发测试 Ping 延迟......\n")
    
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
    
    # 挑选延迟最低的前 12 个域名进行真实下载速度测试
    top_candidates = ping_results[:12]
    
    print("\n" + "=" * 50)
    print(" 阶段二：正在对低延迟节点进行真实下载速度测速 (MB/s)......")
    print("=" * 50 + "\n")
    
    final_results = []
    for avg, domain in top_candidates:
        print(f"正在测试 {domain:<30} 实际下载速度...", end="", flush=True)
        speed = test_download_speed(domain, duration=2.5)
        print(f" -> {speed:.2f} MB/s (Ping: {avg:.1f}ms)")
        final_results.append((speed, avg, domain))
        
    # 按实际下载速度优先降序，其次按 Ping 延迟升序
    final_results.sort(key=lambda x: (-x[0], x[1]))
    
    current_out = os.path.abspath(OUTPUT_FILE)
    current_clean_out = os.path.abspath(OUTPUT_CLEAN_FILE)
    
    print("\n" + "=" * 50)
    print(" 🏆 最终优选排序结果 (按真实下载速度降序):")
    print("=" * 50)
    
    out_lines = []
    clean_lines = []
    for speed, avg, domain in final_results:
        # 直接输出纯域名，方便复制
        print(domain)
        out_lines.append(f"{speed:.2f} MB/s | {avg:.1f} ms: {domain}\n")
        clean_lines.append(f"{domain}\n")
        
    # 补全剩下的未测下载速度但 Ping 成功的节点
    tested_domains = {r[2] for r in final_results}
    for avg, domain in ping_results:
        if domain not in tested_domains:
            out_lines.append(f"0.00 MB/s | {avg:.1f} ms: {domain}\n")
            clean_lines.append(f"{domain}\n")

    with open(current_out, "w", encoding="utf-8") as f:
        f.writelines(out_lines)

    with open(current_clean_out, "w", encoding="utf-8") as f:
        f.writelines(clean_lines)

    print("\n" + "-" * 50)
    print(" 提示: 上方已按【下载速度】选出最佳纯域名，可直接长按复制！")
    print(" 文件保存完整路径如下:")
    print(f"  📌 纯域名文件: {current_clean_out}")
    print(f"  📌 详细速度文件: {current_out}")
    print("-" * 50 + "\n")

if __name__ == "__main__":
    main()

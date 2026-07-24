#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CF-CDN 域名延迟并发测速工具
支持 Android Termux / Linux / macOS / Windows
"""

import os
import sys
import re
import platform
import subprocess
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
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8)
        output = res.stdout
        
        if is_win:
            match = re.search(r'(?:平均|Average)\s*=\s*(\d+)ms', output)
            if match:
                avg = float(match.group(1))
                print(f"正在测试 {domain:<30} 的ping值...... {avg:.3f} ms")
                return (avg, domain)
        else:
            match = re.search(r'rtt min/avg/max/[^=]+=\s*[\d\.]+/([\d\.]+)/', output)
            if match:
                avg = float(match.group(1))
                print(f"正在测试 {domain:<30} 的ping值...... {avg:.3f} ms")
                return (avg, domain)
            match_alt = re.search(r'round-trip min/avg/max = [\d\.]+/([\d\.]+)/', output)
            if match_alt:
                avg = float(match_alt.group(1))
                print(f"正在测试 {domain:<30} 的ping值...... {avg:.3f} ms")
                return (avg, domain)
    except Exception:
        pass
        
    print(f"正在测试 {domain:<30} 的ping值...... 超时/失败")
    return None

def main():
    domains = load_domains()
    print(f"目前已收录 {len(domains)} 个 CF-CDN 域名 (不定期更新域名列表)")
    print("-" * 50)
    print("每个域名 Ping 3 次，取平均值排序......")
    print("注意: Ping 值高低仅供参考，与速度无关\n")
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(ping_domain, domain) for domain in domains]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
                
    results.sort(key=lambda x: x[0])
    
    current_out = os.path.abspath(OUTPUT_FILE)
    current_clean_out = os.path.abspath(OUTPUT_CLEAN_FILE)
    
    print("\n" + "=" * 50)
    print(" 排序结果已完成（纯域名直复制版本）：")
    print("=" * 50)
    
    out_lines = []
    clean_lines = []
    for avg, domain in results:
        # 直接在屏幕打印纯域名，方便长按选择复制
        print(domain)
        out_lines.append(f"{avg:.3f} ms: {domain}\n")
        clean_lines.append(f"{domain}\n")
        
    with open(current_out, "w", encoding="utf-8") as f:
        f.writelines(out_lines)

    with open(current_clean_out, "w", encoding="utf-8") as f:
        f.writelines(clean_lines)

    print("\n" + "-" * 50)
    print(" 提示: 上方已输出纯域名列表，可直接长按复制！")
    print(" 文件保存完整路径如下:")
    print(f"  📌 纯域名文件: {current_clean_out}")
    print(f"  📌 带延迟文件: {current_out}")
    print("-" * 50 + "\n")

if __name__ == "__main__":
    main()

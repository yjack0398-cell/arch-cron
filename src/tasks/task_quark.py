"""
X 平台抓取并上传至夸克网盘 工作流

使用 Playwright 浏览器模拟方式上传文件到夸克网盘
"""

import os
import sys
import asyncio
import argparse
import json

# 将 src 目录添加到 sys.path，解决直接运行时的 ModuleNotFoundError
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
from core.x_scraper import XScraper
from uploaders.uploader_quark import UploaderQuark

load_dotenv()

async def main():
    parser = argparse.ArgumentParser(description="X 平台抓取并上传至 夸克网盘 工作流")
    parser.add_argument('--users', type=str, required=True, help="逗号分隔的 X 用户名列表")
    parser.add_argument('--time_range', type=str, default="1个月", help="抓取时间范围 (当天/3天/1周/1个月/1年/全部)")
    args = parser.parse_args()
    
    users = [u.strip() for u in args.users.split(',') if u.strip()]
    cookies_x = os.getenv("TWITTER_COOKIES")
    cookies_quark = os.getenv("COOKIES_QUARK")
    
    if not cookies_quark:
        print("⚠️ 未配置 夸克网盘 COOKIES，无法上传！")
        return

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        
        # 加载夸克 Cookie
        try:
            cookies = json.loads(cookies_quark)
            clean_list = []
            for c in cookies:
                domain = c.get('domain', '')
                if domain.endswith('quark.cn'):
                    domain = '.quark.cn'
                clean = {
                    'name': c.get('name', ''),
                    'value': c.get('value', ''),
                    'domain': domain,
                    'path': c.get('path', '/'),
                }
                clean_list.append(clean)
            await context.add_cookies(clean_list)
            print(f"✅ 已加载 {len(clean_list)} 条夸克 Cookie")
        except Exception as e:
            print(f"⚠️ 解析夸克 Cookies 失败: {e}")
            await browser.close()
            return

        # 创建上传器（Playwright 浏览器模拟方式）
        uploader = UploaderQuark(cookies_raw=cookies_quark, browser_context=context)
        
        for user in users:
            print(f"\n🚀 开始处理 [夸克网盘] 备份任务: {user} | 范围: {args.time_range}")
            scraper = XScraper(username=user, time_range=args.time_range, cookies_raw=cookies_x)
            files = await scraper.fetch_media_files()
            
            if files:
                await uploader.upload_files(files=files, remote_root=f"Twitter_Archive/{user}")
            else:
                print(f"  ℹ️ {user}: 没有发现新的媒体文件")
            scraper.cleanup()
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

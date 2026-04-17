"""夸克网盘目录结构扫描工具：扫描 3 级目录并推导番剧/系列目录规律"""
import asyncio
import sys
import os
import json

from dotenv import load_dotenv

# 确保加载根目录的 .env
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

async def test_quark_api():
    from playwright.async_api import async_playwright

    cookies_quark = os.getenv("COOKIES_QUARK")
    if not cookies_quark:
        print("❌ 未配置 COOKIES_QUARK，请检查 .env")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080},
        )

        try:
            cookies = json.loads(cookies_quark)
            clean_list = []
            for c in cookies:
                domain = c.get('domain', '')
                if domain.endswith('quark.cn'):
                    domain = '.quark.cn'
                clean_list.append({
                    'name': c.get('name', ''),
                    'value': c.get('value', ''),
                    'domain': domain,
                    'path': c.get('path', '/'),
                })
            await context.add_cookies(clean_list)
        except Exception as e:
            print(f"❌ 解析 Cookie 失败: {e}")
            return

        page = await context.new_page()

        api_info = {}
        
        async def on_request(request):
            if 'api/file' in request.url and request.method == 'POST':
                print(f"✅ Intercepted file API request: {request.url}")
                api_info['url'] = request.url
                api_info['headers'] = request.headers
                api_info['post_data'] = request.post_data

        page.on('request', on_request)

        print("Navigating to Quark Pan...")
        await page.goto("https://pan.quark.cn", timeout=30000)
        await asyncio.sleep(5)
        
        print("\n=== API Info gathered ===")
        if api_info:
            print(f"URL: {api_info['url']}")
            print("Headers keys:", list(api_info['headers'].keys()))
            if 'authorization' in api_info['headers']:
                print("Has Authorization!")
            print(f"Payload: {api_info['post_data']}")
        else:
            print("No file API intercepted.")
            
        await browser.close()

asyncio.run(test_quark_api())

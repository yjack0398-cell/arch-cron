import os
import sys
import asyncio
import argparse

# 将 src 目录添加到 sys.path，确保可以导入 core 和 uploaders
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
from core.x_scraper import XScraper
from uploaders.uploader_115 import Uploader115

load_dotenv()

async def main():
    parser = argparse.ArgumentParser(description="X 平台抓取并上传至 115网盘 工作流")
    parser.add_argument('--users', type=str, required=True, help="逗号分隔的 X 用户名列表")
    args = parser.parse_args()
    
    users = [u.strip() for u in args.users.split(',') if u.strip()]
    cookies_x = os.getenv("TWITTER_COOKIES")
    cookies_115 = os.getenv("COOKIES_115")
    
    if not cookies_115:
        print("⚠️ 未配置 115 网盘 COOKIES，无法上传！")
        return

    uploader = Uploader115(cookies_raw=cookies_115)
    
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")

    for user in users:
        print(f"\n🚀 开始处理 [115网盘] 备份任务: {user}")
        scraper = XScraper(username=user, cookies_raw=cookies_x)
        files = await scraper.fetch_media_files()
        
        if files:
            uploader.upload_files(
                files=files,
                remote_root="Twitter_Archive",
                user_name=user,
                today_str=today_str
            )
        scraper.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

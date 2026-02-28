import os
import asyncio
import glob
import argparse
from dotenv import load_dotenv

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.x_scraper import XScraper

load_dotenv()

async def main():
    parser = argparse.ArgumentParser(description="X 平台抓取并上传至 Google Photos 工作流")
    parser.add_argument('--users', type=str, required=True, help="逗号分隔的 X 用户名列表")
    args = parser.parse_args()
    
    users = [u.strip() for u in args.users.split(',') if u.strip()]
    cookies_x = os.getenv("TWITTER_COOKIES")
    token_gp = os.getenv("GOOGLE_PHOTOS_TOKEN")
    
    if not token_gp:
        print("⚠️ 未配置 Google Photos Token，无法上传！")
        return

    try:
         from google_photos_uploader import GooglePhotosUploader
         uploader = GooglePhotosUploader(token_base64=token_gp)
    except ImportError as e:
         print(f"❌ 缺少依赖模块: {e}")
         return
    except Exception as e:
         print(f"❌ 初始化 Google Photos 客户端失败: {e}")
         return
         
    for user in users:
        print(f"\n🚀 开始处理 [Google Photos] 备份任务: {user}")
        scraper = XScraper(username=user, cookies_raw=cookies_x)
        files = await scraper.fetch_media_files()
        
        if files:
            album_name = f"X_Archive_{user}"
            print(f"☁️ 准备上传 {len(files)} 个文件到相册 '{album_name}'...")
            for local_file in files:
                uploader.upload_file(local_file, album_name=album_name)

        scraper.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

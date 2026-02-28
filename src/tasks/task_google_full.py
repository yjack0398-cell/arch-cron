import os
import asyncio
import glob
import argparse
import subprocess
import shutil
from dotenv import load_dotenv

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.x_scraper import XScraper

load_dotenv()

async def main():
    parser = argparse.ArgumentParser(description="X 平台全量历史媒体抓取并上传至 Google Photos")
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
        print(f"\n🚀 开始处理 [全量档案提取] 备份任务: {user}")
        scraper = XScraper(username=user, cookies_raw=cookies_x)
        cookie_file = scraper._prepare_cookies_file()
        
        user_download_dir = scraper.user_download_dir
        if os.path.exists(user_download_dir):
            shutil.rmtree(user_download_dir)
        os.makedirs(user_download_dir, exist_ok=True)
        
        print(f"📥 正在执行 gallery-dl 全量深度抓取 {user}，此过程可能会持续很久...")
        # 目标提取该用户发送的所有带媒体的内容
        target_url = f"https://x.com/{user}/media"
        
        cmd = [
            "gallery-dl",
            target_url,
            "--directory", user_download_dir,
            "--cookies", cookie_file if cookie_file else ""
        ]
        
        # 移除非法空参数
        cmd = [c for c in cmd if c]
        
        try:
            subprocess.run(cmd, check=False)
        except Exception as e:
            print(f"❌ gallery-dl 运行出错（请检查是否已安装 pip install gallery-dl）: {e}")
        
        # gallery-dl 通常会创建很多子文件夹，我们用 glob 递归提取所有文件
        all_files = glob.glob(f"{user_download_dir}/**/*", recursive=True)
        files = [f for f in all_files if os.path.isfile(f)]
        
        if files:
            album_name = f"X_Archive_{user}"
            print(f"☁️ 准备分批上传 {len(files)} 个高清媒体文件到专属相册 '{album_name}'...")
            for local_file in files:
                uploader.upload_file(local_file, album_name=album_name)
        else:
            print(f"📭 未未能下载到 {user} 的任何媒体文件。")

        scraper.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

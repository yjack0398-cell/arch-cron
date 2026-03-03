import os
import shutil
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import subprocess
import glob

# 加载环境变量
load_dotenv()

class XScraper:
    def __init__(self, username: str, time_range: str = "1个月", download_root: str = "downloads", cookies_raw: str = None):
        """
        初始化 X 平台爬虫。
        :param username: 需要抓取的 X 用户名
        :param time_range: 抓取的时间范围 (当天/3天/1周/1个月/1年/全部)
        :param download_root: 下载文件的临时根目录
        :param cookies_raw: X 平台的原始 Cookie 字符串 (JSON 格式)
        """
        self.username = username
        self.time_range = time_range
        self.download_root = download_root
        self.cookies_raw = cookies_raw
        self.user_download_dir = os.path.join(self.download_root, self.username)
        self.today_str = datetime.now().strftime("%Y-%m-%d")

    async def _load_cookies(self, context):
        import json
        if not self.cookies_raw:
            return
        try:
            cookies = json.loads(self.cookies_raw)
            valid_count = 0
            for cookie in cookies:
                try:
                    clean = {
                        'name': cookie.get('name', ''),
                        'value': cookie.get('value', ''),
                        'sameSite': 'Lax'
                    }
                    domain = cookie.get('domain', '')
                    if domain:
                        clean['domain'] = domain
                        clean['path'] = cookie.get('path', '/')
                    else:
                        continue
                    if cookie.get('secure'):
                        clean['secure'] = True
                    if cookie.get('httpOnly'):
                        clean['httpOnly'] = True
                    if cookie.get('expirationDate'):
                        clean['expires'] = cookie['expirationDate']
                    
                    await context.add_cookies([clean])
                    valid_count += 1
                except Exception:
                    continue
            print(f"✅ X 平台：加载了 {valid_count} 个 Cookies")
        except Exception as e:
            print(f"⚠️ X 平台：解析 Cookies 失败: {e}")

    def _prepare_cookies_file(self) -> str:
        """为 yt-dlp 准备 Netscape 格式的 Cookie 文件"""
        if not self.cookies_raw:
            return None
        cookie_file = "twitter_cookies.txt"
        import json
        try:
            data = json.loads(self.cookies_raw)
            if isinstance(data, list):
                with open(cookie_file, 'w') as f:
                    f.write("# Netscape HTTP Cookie File\n")
                    for c in data:
                        domain = c.get('domain', '')
                        flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                        path = c.get('path', '/')
                        secure = 'TRUE' if c.get('secure') else 'FALSE'
                        expiration = str(int(c.get('expirationDate', 0)))
                        name = c.get('name', '')
                        value = c.get('value', '')
                        f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")
                return cookie_file
        except:
            pass
        return None

    async def scrape_tweet_urls(self, context) -> list:
        """利用 Playwright 页面滚动抓取带有媒体的推文链接，动态基于时间范围"""
        from datetime import datetime, timedelta, timezone
        now_utc = datetime.now(timezone.utc)
        
        # 确定时间限制与最大滚动次数
        if self.time_range == "当天":
            time_limit = now_utc - timedelta(days=1)
            max_scrolls = 25
        elif self.time_range == "3天":
            time_limit = now_utc - timedelta(days=3)
            max_scrolls = 40
        elif self.time_range == "1周":
            time_limit = now_utc - timedelta(days=7)
            max_scrolls = 60
        elif self.time_range == "1个月":
            time_limit = now_utc - timedelta(days=30)
            max_scrolls = 150
        elif self.time_range == "1年":
            time_limit = now_utc - timedelta(days=365)
            max_scrolls = 1000
        elif self.time_range == "全部":
            time_limit = datetime.min.replace(tzinfo=timezone.utc)
            max_scrolls = 3000
        else: # default 1 个月
            time_limit = now_utc - timedelta(days=30)
            max_scrolls = 150
            self.time_range = "1个月"

        page = await context.new_page()
        tweet_urls = set()
        print(f"🔎 正在扫描主页 (目标范围: {self.time_range}): https://x.com/{self.username}")
        try:
            await page.goto(f"https://x.com/{self.username}", timeout=60000)
            try:
                 await page.wait_for_selector('article[data-testid="tweet"]', timeout=30000)
            except Exception as e:
                 current_url = page.url
                 title = await page.title()
                 print(f"⚠️ XScraper 等待推文超时 (可能是登录失败或该账号无新内容)")
                 print(f"🔍 调试信息: 当前 URL 为 {current_url} | 页面标题: {title}")
                 if "login" in current_url or "account/access" in current_url:
                     print("🚨 致命错误: 您的 X 平台访问被重定向到了登录页或锁定页，这代表所使用的 TWITTER_COOKIES 必然已失效，请重新提取并配置 Cookie。")
                 elif "suspended" in current_url:
                     print("🚨 致命错误: 该推特账号已被封禁 (Suspended)。")
                 return []

            reached_time_limit = False

            for i in range(max_scrolls):
                if reached_time_limit:
                    print(f"  ⏳ 已抓取到 {self.time_range} 前的数据，停止向下滚动。")
                    break

                articles = await page.locator('article[data-testid="tweet"]').all()
                for article in articles:
                    try:
                        # 检查推文时间
                        time_loc = article.locator('time').first
                        if await time_loc.count() > 0:
                            date_str = await time_loc.get_attribute('datetime')
                            if date_str:
                                # date_str 格式如 '2025-02-15T12:00:00.000Z'
                                tweet_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                if tweet_date < time_limit:
                                    reached_time_limit = True

                        has_media = False
                        if await article.locator('div[data-testid="tweetPhoto"]').count() > 0:
                            has_media = True
                        elif await article.locator('div[data-testid="videoPlayer"]').count() > 0:
                            has_media = True
                            
                        if has_media:
                            link_loc = article.locator('a[href*="/status/"]').first
                            if await link_loc.count() > 0:
                                href = await link_loc.get_attribute("href")
                                full_url = f"https://x.com{href}".split("?")[0]
                                tweet_urls.add(full_url)
                    except:
                        continue
                
                # 向下滚动 2500 像素，等待新内容加载
                await page.evaluate("window.scrollBy(0, 2500)")
                # 给网页一点时间渲染后面的推文
                await asyncio.sleep(2.5)
                
                if i > 0 and i % 10 == 0:
                    print(f"  ... 已滚动 {i} 次，目前采集到 {len(tweet_urls)} 个媒体推文。")

        except Exception as e:
            print(f"⚠️ 抓取 {self.username} 页面异常: {e}")
        finally:
            await page.close()
            
        return list(tweet_urls)

    async def fetch_media_files(self) -> list:
        """
        完整工作流：下载该用户的所有媒体到本地
        返回本地下载好的文件绝对路径列表。
        """
        # 1. 准备本地目录
        if os.path.exists(self.user_download_dir):
            shutil.rmtree(self.user_download_dir)
        os.makedirs(self.user_download_dir, exist_ok=True)
        
        cookie_file = self._prepare_cookies_file()

        # 2. 抓取 URLs
        async with async_playwright() as p:
            launch_args = ['--disable-blink-features=AutomationControlled', '--no-sandbox']
            browser = await p.chromium.launch(headless=True, args=launch_args)
            context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
            await self._load_cookies(context)
            
            tweet_urls = await self.scrape_tweet_urls(context)
            await browser.close()

        if not tweet_urls:
            print(f"📭 用户 {self.username} 最近没有带媒体的推文。")
            return []

        print(f"📥 发现 {len(tweet_urls)} 条带有媒体的推文，开始下载...")

        # 3. 使用 gallery-dl 替代 yt-dlp 执行下载
        for url in tweet_urls:
            cmd = [
                "gallery-dl",
                url,
                "--directory", self.user_download_dir,
            ]
            if cookie_file:
                 cmd.extend(["--cookies", cookie_file])
            
            subprocess.run(cmd, check=False)

        # 4. 收集下载的文件 (由于 gallery-dl 可能会生成多级子文件夹，例如 twitter/用户名/图片.jpg)
        all_files = glob.glob(f"{self.user_download_dir}/**/*", recursive=True)
        files = [f for f in all_files if os.path.isfile(f)]
        
        # 按照新到旧进行排序 (优先依赖文件的 mtime 属性，因为 gallery-dl 默认会将文件的修改时间设为推文发布时间)
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        if not files:
            print(f"⚠️ [{self.username}] 下载管线结束，但没有抓到文件。")
            return []

        return files

    def cleanup(self):
        """清理临时生成的下载目录"""
        if os.path.exists(self.user_download_dir):
            shutil.rmtree(self.user_download_dir, ignore_errors=True)
        print(f"🗑️ 已清理 {self.username} 的临时文件。")

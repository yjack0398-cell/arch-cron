"""
磁力链接自动追踪与夸克云盘离线下载工作流

功能流程:
1. 读取 magnet_series.json 配置，获取各番号系列的前缀和当前最新编号
2. 对每个系列，递推出下一个预期番号
3. 调用 MagnetScraper (sukebei.nyaa.si) 搜索该番号
4. 若搜索到结果，提取最优磁力链接
5. 提交磁力链接至夸克网盘离线下载
6. 更新 magnet_series.json 中的 last_number

用法:
    python src/tasks/task_magnet_sync.py [--dry_run] [--series "zPP系列"] [--target quark|115]
"""

import os
import sys
import json
import asyncio
import argparse

# 将 src 目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

load_dotenv()

# 配置文件路径
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'magnet_series.json')


def load_series_config() -> dict:
    """加载番号系列配置"""
    config_abs = os.path.abspath(CONFIG_PATH)
    if not os.path.exists(config_abs):
        print(f"❌ 配置文件不存在: {config_abs}")
        sys.exit(1)

    with open(config_abs, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return {k: v for k, v in data.items() if isinstance(v, dict) and 'prefix' in v}


def save_series_config(config: dict):
    """保存更新后的配置（保留 _说明 字段）"""
    config_abs = os.path.abspath(CONFIG_PATH)

    with open(config_abs, 'r', encoding='utf-8') as f:
        original = json.load(f)

    original.update(config)

    with open(config_abs, 'w', encoding='utf-8') as f:
        json.dump(original, f, ensure_ascii=False, indent=2)


def generate_next_keyword(prefix: str, last_number: int) -> str:
    """根据前缀和当前最大编号生成下一个搜索关键字"""
    next_num = last_number + 1
    if next_num < 1000:
        return f"{prefix}{next_num:03d}"
    return f"{prefix}{next_num}"


async def process_single_series(
    series_name: str,
    series_config: dict,
    scraper,
    uploader,
    dry_run: bool = True,
    check_count: int = 3,
) -> int:
    """处理单个番号系列：检查多个连续编号"""
    prefix = series_config["prefix"]
    last_number = series_config.get("last_number", 0)
    success_total = 0

    print(f"\n{'='*50}")
    print(f"📁 系列: {series_name} | 前缀: {prefix} | 当前最新: {last_number}")
    print(f"{'='*50}")

    for offset in range(1, check_count + 1):
        target_number = last_number + offset
        keyword = generate_next_keyword(prefix, last_number + offset - 1)
        print(f"\n🎯 [{offset}/{check_count}] 搜索目标: {keyword}")

        # MagnetScraper 是纯 HTTP 同步调用
        magnet = scraper.search_best_magnet(keyword)

        if not magnet:
            print(f"  📭 {keyword} 暂无资源，可能尚未发布")
            break

        if dry_run:
            print(f"  🧪 [DRY RUN] 将会提交磁力: {magnet[:60]}...")
            series_config["last_number"] = target_number
            success_total += 1
        else:
            submitted = await uploader.add_offline_download(magnet)
            if submitted:
                series_config["last_number"] = target_number
                success_total += 1
                print(f"  ✅ {keyword} 已成功提交离线下载！")
            else:
                print(f"  ❌ {keyword} 提交离线下载失败")

    return success_total


async def main():
    parser = argparse.ArgumentParser(description="磁力链接自动追踪与夸克云盘离线下载工作流")
    parser.add_argument('--dry_run', action='store_true', default=False,
                        help="演习模式：只搜索不提交（默认关闭）")
    parser.add_argument('--series', type=str, default=None,
                        help="指定只处理某个系列（如 'zPP系列'），不指定则处理全部启用的系列")
    parser.add_argument('--target', type=str, default='quark', choices=['quark', '115'],
                        help="目标云盘（quark 或 115，默认 quark）")
    parser.add_argument('--check_count', type=int, default=3,
                        help="每个系列向前探测的编号数量（默认3）")
    args = parser.parse_args()

    print("🚀 磁力链接自动追踪工作流启动\n")
    if args.dry_run:
        print("⚠️  [DRY RUN 演习模式] 只搜索和评分，不会提交任何离线下载任务\n")

    # 加载配置
    all_config = load_series_config()

    # 筛选要处理的系列
    if args.series:
        if args.series not in all_config:
            print(f"❌ 配置中不存在系列: {args.series}")
            print(f"   可用系列: {', '.join(all_config.keys())}")
            return
        series_to_process = {args.series: all_config[args.series]}
    else:
        series_to_process = {k: v for k, v in all_config.items() if v.get("enabled", True)}

    if not series_to_process:
        print("⚠️ 没有启用的系列需要处理")
        return

    print(f"📋 本次将处理 {len(series_to_process)} 个系列: {', '.join(series_to_process.keys())}\n")

    # 初始化磁力搜索引擎（纯 HTTP，无需 Playwright）
    from core.magnet_scraper import MagnetScraper
    scraper = MagnetScraper()

    # 初始化上传器
    uploader = None
    pw = None
    browser = None

    if not args.dry_run:
        if args.target == 'quark':
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
            )

            cookies_quark = os.getenv("COOKIES_QUARK")
            if not cookies_quark:
                print("❌ 非演习模式下目标为 quark 时必须配置 COOKIES_QUARK 环境变量")
                await browser.close()
                await pw.stop()
                return

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
                print(f"❌ 解析夸克 Cookies 失败: {e}")
                await browser.close()
                await pw.stop()
                return

            from uploaders.uploader_quark import UploaderQuark
            uploader = UploaderQuark(cookies_raw=cookies_quark, browser_context=context)

        elif args.target == '115':
            cookies_115 = os.getenv("COOKIES_115")
            if not cookies_115:
                print("❌ 非演习模式下目标为 115 时必须配置 COOKIES_115 环境变量")
                return
            from uploaders.uploader_115 import Uploader115
            uploader = Uploader115(cookies_raw=cookies_115)

    # 逐个系列处理
    total_success = 0
    for name, config in series_to_process.items():
        count = await process_single_series(
            series_name=name,
            series_config=config,
            scraper=scraper,
            uploader=uploader,
            dry_run=args.dry_run,
            check_count=args.check_count,
        )
        total_success += count

    # 关闭资源
    if browser:
        await browser.close()
    if pw:
        await pw.stop()

    # 保存更新后的配置
    save_series_config(series_to_process)

    # 汇总报告
    print(f"\n{'='*50}")
    print(f"📊 工作流结算报告")
    print(f"  ▶ 处理系列数: {len(series_to_process)}")
    print(f"  ▶ 成功提交磁力: {total_success}")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())

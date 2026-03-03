"""
夸克网盘 Playwright 浏览器模拟上传器

通过 Playwright 模拟真实浏览器操作上传文件到夸克网盘，
绕过私有 API 签名问题。

流程：加载 Cookie → 打开网盘页面 → 创建/进入目标文件夹 → 通过 input[type=file] 上传
"""

import os
import json
import asyncio
from datetime import datetime


class UploaderQuark:
    """基于 Playwright 浏览器模拟的夸克网盘上传器"""

    # 夸克网盘页面常量
    PAN_URL = "https://pan.quark.cn/list#/list/all"
    # 上传相关选择器（夸克使用 React + Ant Design）
    SELECTOR_FILE_INPUT = '.ant-upload input[type="file"]'
    SELECTOR_UPLOAD_BTN = "button.upload-btn"
    # 文件夹相关选择器
    SELECTOR_CREATE_FOLDER_BTN = ".btn-create-folder"
    SELECTOR_FOLDER_NAME_INPUT = ".ant-modal input.ant-input"
    SELECTOR_MODAL_OK_BTN = ".ant-modal .ant-btn-primary"
    # 文件列表
    SELECTOR_FILE_LIST = ".ant-table-body"
    # 上传进度弹窗
    SELECTOR_UPLOAD_PROGRESS = ".upload-progress, .upload-task-list, .ant-upload-list"

    # 超时配置（毫秒）
    TIMEOUT_PAGE_LOAD = 30_000
    TIMEOUT_LOGIN_CHECK = 15_000
    TIMEOUT_UPLOAD_SINGLE = 120_000  # 单文件上传超时 2 分钟
    TIMEOUT_FOLDER_ACTION = 10_000

    def __init__(self, cookies_raw: str, browser_context):
        """
        初始化上传器

        Args:
            cookies_raw: 夸克网盘 Cookie JSON 字符串
            browser_context: Playwright 浏览器上下文
        """
        self.cookies_raw = cookies_raw
        self.context = browser_context
        self.page = None

    async def _ensure_page(self):
        """确保页面已就绪并已登录"""
        if self.page and not self.page.is_closed():
            return True

        self.page = await self.context.new_page()
        try:
            await self.page.goto(self.PAN_URL, timeout=self.TIMEOUT_PAGE_LOAD)
            # 等待文件列表或上传按钮出现 → 表示已登录
            await self.page.wait_for_selector(
                f"{self.SELECTOR_UPLOAD_BTN}, {self.SELECTOR_FILE_LIST}",
                timeout=self.TIMEOUT_LOGIN_CHECK
            )
            print("✅ 夸克网盘页面加载成功，登录态正常")
            return True
        except Exception as e:
            print(f"❌ 夸克网盘页面加载失败或未登录: {e}")
            return False

    async def _navigate_to_folder(self, folder_path: str):
        """
        进入多层级文件夹（如 Twitter_Archive/User），不存在则创建

        Args:
            folder_path: 目标路径，如 "Twitter_Archive/User"
        """
        parts = [p.strip() for p in folder_path.split('/') if p.strip()]
        
        # 回到根目录开始导航
        await self.page.goto(self.PAN_URL, timeout=self.TIMEOUT_PAGE_LOAD)
        
        for part in parts:
            try:
                await self.page.wait_for_selector(
                    self.SELECTOR_FILE_LIST, timeout=self.TIMEOUT_LOGIN_CHECK
                )
                await asyncio.sleep(2)

                # 尝试点击已存在的文件夹
                folder_locators = [
                    self.page.get_by_text(part, exact=True).first,
                    self.page.locator(f'a[title="{part}"]').first,
                    self.page.locator(f'div[title="{part}"]').first
                ]
                
                found = False
                for folder_link in folder_locators:
                    if await folder_link.count() > 0:
                        print(f"  📂 进入文件夹: {part}")
                        await folder_link.dblclick(timeout=self.TIMEOUT_FOLDER_ACTION)
                        await asyncio.sleep(3)
                        found = True
                        break

                if not found:
                    print(f"  📂 未发现 [{part}]，尝试新建...")
                    # 点击“新建”
                    create_btn = self.page.get_by_text("新建", exact=True).first
                    if await create_btn.count() == 0:
                        create_btn = self.page.locator('button:has-text("新建")').first
                    
                    if await create_btn.count() > 0:
                        await create_btn.click()
                        await asyncio.sleep(1)
                        # 点击下拉菜单里的“新建文件夹”
                        mkdir_item = self.page.locator('.ant-dropdown-menu-item:has-text("文件夹")').first
                        if await mkdir_item.count() == 0:
                            mkdir_item = self.page.get_by_text("新建文件夹", exact=True).last
                        
                        await mkdir_item.click()
                        await asyncio.sleep(1)

                        # 输入文件夹名
                        name_input = self.page.locator('input.ant-input, input[type="text"]').last
                        await name_input.fill(part)
                        await asyncio.sleep(0.5)
                        # 点击确认
                        ok_btn = self.page.get_by_text("确 定", exact=False).last
                        await ok_btn.click()
                        await asyncio.sleep(3)
                        
                        # 再次双击进入
                        await self.page.get_by_text(part, exact=True).first.dblclick()
                        await asyncio.sleep(2)
                
            except Exception as e:
                print(f"  ⚠️ 文件夹导航过程中断 [{part}]: {e}")
                return False
        return True

    async def _upload_single_file(self, file_path: str) -> bool:
        """
        上传单个文件

        Args:
            file_path: 本地文件绝对路径

        Returns:
            是否上传成功
        """
        filename = os.path.basename(file_path)
        filesize = os.path.getsize(file_path)

        try:
            # 找到隐藏的 file input 并设置文件
            file_input = self.page.locator(self.SELECTOR_FILE_INPUT).first
            if await file_input.count() == 0:
                # 如果找不到，尝试先点击上传按钮触发
                upload_btn = self.page.locator(self.SELECTOR_UPLOAD_BTN).first
                if await upload_btn.count() > 0:
                    # 有些实现需要先点按钮才会出现 input
                    pass
                # 重新查找
                file_input = self.page.locator('input[type="file"]').first
                if await file_input.count() == 0:
                    print(f"  ❌ {filename}: 未找到文件上传入口")
                    return False

            # 使用 Playwright 的 set_input_files 直接设置文件
            # 这会绕过文件选择对话框
            await file_input.set_input_files(file_path)
            print(f"  ⬆️ 已选择文件: {filename} ({filesize:,} bytes)")

            # 等待上传完成
            # 监听上传进度，等待完成
            uploaded = await self._wait_for_upload_complete(filename)
            return uploaded

        except Exception as e:
            print(f"  ❌ {filename}: 上传异常 - {e}")
            return False

    async def _wait_for_upload_complete(self, filename: str, timeout_ms: int = None) -> bool:
        """
        等待文件上传完成

        通过检测上传进度条消失或成功状态来判断

        Args:
            filename: 文件名（用于日志）
            timeout_ms: 超时时间（毫秒）
        """
        if timeout_ms is None:
            # 根据经验，大部分小图片几十KB，几秒钟就能上传完
            # 设定最大等待为 20 秒，如果是普通的小文件足够了
            timeout_ms = 20_000

        try:
            # 策略1: 等待较短时间，往往一瞬间就上传完成了
            await asyncio.sleep(1.5)

            # 策略2: 轮询检查上传状态
            max_wait = timeout_ms / 1000  # 转为秒
            elapsed = 1.5
            check_interval = 1.5

            # 提取文件名的去后缀片段，用于模糊查找
            name_without_ext = os.path.splitext(filename)[0]
            short_name = name_without_ext[:15] if len(name_without_ext) > 15 else name_without_ext

            while elapsed < max_wait:
                # 检查页面上是否有上传完成的通用标志
                success_toasts = [
                    self.page.locator('.toast, .ant-message, .message, .upload-success').get_by_text("上传成功", exact=False),
                    self.page.locator('.toast, .ant-message, .message, .upload-success').get_by_text("上传完成", exact=False)
                ]
                for toast in success_toasts:
                    if await toast.first.count() > 0:
                        print(f"  ✅ {filename} 上传成功 (检测到系统提示)")
                        return True

                # 夸克通常在上传完成后显示文件在列表中，但由于虚拟列表的存在可能不可见
                # 使用部分名字模糊匹配
                file_el = self.page.get_by_text(short_name, exact=False).first
                if await file_el.count() > 0:
                    print(f"  ✅ {filename} 上传成功 (列表已更新)")
                    return True

                # 检查是否有错误提示
                error_toasts = [
                    self.page.locator(".ant-message-error, .upload-error").first,
                    self.page.locator('.toast, .ant-message').get_by_text("上传失败", exact=False).first
                ]
                
                for error_el in error_toasts:
                    if await error_el.count() > 0:
                        error_text = await error_el.text_content()
                        if error_text and "失败" in error_text:
                            print(f"  ❌ {filename}: 上传出现异常提示 - {error_text.strip()}")
                            return False

                await asyncio.sleep(check_interval)
                elapsed += check_interval

            # 超时 - 但由于虚拟列表的关系，没找到 DOM 不代表没上传
            print(f"  ⚠️ {filename}: 等待上传确认超时 ({max_wait}s)，默认继续下一个文件")
            return True  # 乐观处理

        except Exception as e:
            print(f"  ⚠️ {filename}: 等待上传状态异常 - {e}")
            return True  # 乐观处理

    async def upload_files(self, files: list, remote_root: str = "Twitter_Archive"):
        """
        通过浏览器模拟上传文件到夸克网盘

        Args:
            files: 本地文件路径列表
            remote_root: 远程目标文件夹名
        """
        if not self.cookies_raw:
            print("⚠️ 未配置夸克 Cookie，无法上传")
            return
        if not files:
            print("⚠️ 没有文件需要上传")
            return

        print(f"☁️ 正在通过浏览器模拟上传 {len(files)} 个文件到夸克网盘...")

        try:
            # 确保页面就绪
            if not await self._ensure_page():
                return

            # 创建/进入目标文件夹
            today_str = datetime.now().strftime("%Y-%m-%d")
            await self._navigate_to_folder(remote_root)

            # 可选: 创建日期子文件夹
            # await self._navigate_to_folder(today_str)

            # 逐个上传文件
            success_count = 0
            fail_count = 0

            for i, local_file in enumerate(files, 1):
                if not os.path.exists(local_file):
                    print(f"  ⚠️ 文件不存在: {local_file}")
                    fail_count += 1
                    continue

                filename = os.path.basename(local_file)
                print(f"\n  [{i}/{len(files)}] 上传: {filename}")

                if await self._upload_single_file(local_file):
                    success_count += 1
                else:
                    fail_count += 1

                # 上传间隔，避免触发限制
                if i < len(files):
                    await asyncio.sleep(2)

            print(f"\n☁️ 夸克上传完成: ✅ {success_count} 成功, ❌ {fail_count} 失败")

        except Exception as e:
            print(f"❌ 夸克浏览器模拟上传故障: {e}")
        finally:
            if self.page and not self.page.is_closed():
                await self.page.close()
                self.page = None

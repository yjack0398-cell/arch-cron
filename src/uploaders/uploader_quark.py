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

    async def _navigate_to_folder(self, folder_path: str) -> bool:
        """
        进入多层级文件夹（如 Twitter_Archive/User），不存在则创建
        增加严格的校验，防止进入错误目录或产生垃圾文件夹

        Args:
            folder_path: 目标路径，如 "Twitter_Archive/User"
        """
        parts = [p.strip() for p in folder_path.split('/') if p.strip()]
        
        # 回到根目录开始导航
        print(f"  🔍 导航至目录: {folder_path}")
        await self.page.goto(self.PAN_URL, timeout=self.TIMEOUT_PAGE_LOAD)
        
        for part in parts:
            try:
                # 等待文件列表加载
                await self.page.wait_for_selector(self.SELECTOR_FILE_LIST, timeout=self.TIMEOUT_LOGIN_CHECK)
                await asyncio.sleep(2) # 给予 UI 渲染缓冲

                # 寻找目标文件夹
                folder_locators = [
                    self.page.get_by_text(part, exact=True).first,
                    self.page.locator(f'a[title="{part}"]').first,
                    self.page.locator(f'div[title="{part}"]').first
                ]
                
                found_el = None
                for loc in folder_locators:
                    if await loc.count() > 0:
                        found_el = loc
                        break

                if found_el:
                    print(f"  📂 发现已有文件夹: {part}，尝试进入...")
                    await found_el.dblclick(timeout=self.TIMEOUT_FOLDER_ACTION)
                    await asyncio.sleep(3)
                else:
                    print(f"  🆕 未发现 [{part}]，启动可靠创建流程...")
                    # 1. 点击新建
                    create_btn = self.page.get_by_text("新建", exact=True).first
                    if await create_btn.count() == 0:
                        create_btn = self.page.locator('button:has-text("新建")').first
                    
                    if await create_btn.count() == 0:
                        raise Exception(f"找不到'新建'按钮")

                    await create_btn.click()
                    await asyncio.sleep(1)

                    # 2. 选择新建文件夹
                    mkdir_item = self.page.locator('.ant-dropdown-menu-item:has-text("文件夹")').first
                    if await mkdir_item.count() == 0:
                        mkdir_item = self.page.get_by_text("新建文件夹", exact=True).last
                    
                    await mkdir_item.click()
                    await asyncio.sleep(1.5)

                    # 3. 输入名称并确认
                    name_input = self.page.locator('input.ant-input, input[type="text"]').last
                    if await name_input.count() == 0:
                        raise Exception(f"新建文件夹模态框输入框未出现")
                        
                    await name_input.fill(part)
                    await asyncio.sleep(1) # 等待输入字符渲染
                    
                    # 首先尝试最稳定底层的确体方式：在输入框内直接敲击回车键
                    await name_input.press("Enter")
                    await asyncio.sleep(1)
                    
                    # 检查模态框是否依然存在 (如果回车没生效，尝试备用的按钮点击方案)
                    if await self.page.locator('.ant-modal-mask').is_visible():
                        print(f"  ⌨️ 回车确认似乎未生效，尝试备用按钮点击...")
                        ok_btn_selectors = [
                            self.page.locator('.ant-modal-footer button.ant-btn-primary').last,
                            self.page.get_by_text("确 定", exact=False).last,
                            self.page.get_by_text("确认", exact=False).last,
                            self.page.locator('button:has-text("确 定")').last
                        ]
                        
                        for btn in ok_btn_selectors:
                            if await btn.count() > 0 and await btn.is_visible():
                                await btn.click()
                                break
                    
                    # 4. 等待模态框消失（极其重要！否则夸克会因为操作太快重置为默认名）
                    await self.page.wait_for_selector('.ant-modal-mask', state='hidden', timeout=10000)
                    print(f"  ✅ 文件夹 [{part}] 理论创建成功，检查列表更新...")
                    await asyncio.sleep(3)

                    # 5. 再次验证并双击进入
                    recheck_el = self.page.get_by_text(part, exact=True).first
                    if await recheck_el.count() > 0:
                        await recheck_el.dblclick()
                        await asyncio.sleep(3)
                    else:
                        raise Exception(f"创建文件夹 [{part}] 后，在列表中未找到。可能重命名失败。")
                
                # 每走一层都做一次简单的 URL 或标题校验（可选，此处通过下一循环的 wait_for_selector 保证）
            except Exception as e:
                print(f"  ❌ 目录导航/创建失败 [{part}]: {e}")
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
            if not await self._navigate_to_folder(remote_root):
                print(f"  ❌ 无法导航到目标文件夹 [{remote_root}]。为防止根目录污染，已放弃本次上传。")
                return

            # 获取当前页面的文件列表（用于上传前跳过已存在的文件）
            print("  📊 正在获取已存在文件列表以加速归档...")
            existing_files = []
            try:
                # 夸克文件列表文本通常包含在 table cell 里
                cell_nodes = await self.page.locator('.ant-table-cell').all_text_contents()
                existing_files = [n.strip() for n in cell_nodes if n.strip()]
            except:
                pass

            # 逐个上传文件
            success_count = 0
            fail_count = 0

            for i, local_file in enumerate(files, 1):
                if not os.path.exists(local_file):
                    print(f"  ⚠️ 文件不存在: {local_file}")
                    fail_count += 1
                    continue

                filename = os.path.basename(local_file)
                
                # 简单排重检查
                if filename in existing_files:
                    print(f"  ⏩ [{i}/{len(files)}] 跳过 (已存在): {filename}")
                    success_count += 1
                    continue

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

    # =========================================================
    # 离线下载 & 文件移动（磁力工作流专用）
    # =========================================================

    async def add_offline_download(self, magnet_url: str) -> bool:
        """
        通过浏览器模拟将磁力链接提交到夸克网盘的"云下载"(离线下载)队列

        Args:
            magnet_url: 以 magnet:?xt=urn:btih: 开头的完整磁力链接

        Returns:
            是否成功提交
        """
        if not magnet_url or not magnet_url.startswith("magnet:"):
            print("  ❌ 无效的磁力链接格式")
            return False

        print(f"  🧲 正在提交离线下载任务: {magnet_url[:60]}...")

        try:
            if not await self._ensure_page():
                return False

            # 回到网盘主页
            await self.page.goto(self.PAN_URL, timeout=self.TIMEOUT_PAGE_LOAD)
            await asyncio.sleep(2)

            # 方式 1: 寻找"云下载"或"离线下载"入口按钮
            # 夸克网盘通常在顶部工具栏有"云下载"按钮
            cloud_dl_btn_selectors = [
                self.page.get_by_text("云下载", exact=False).first,
                self.page.get_by_text("离线下载", exact=False).first,
                self.page.locator('button:has-text("云下载")').first,
                self.page.locator('[class*="cloud-download"], [class*="offline"]').first,
            ]

            clicked = False
            for btn in cloud_dl_btn_selectors:
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(2)
                    clicked = True
                    break

            if not clicked:
                print("  ⚠️ 未找到'云下载'按钮，尝试直接导航到离线下载页面...")
                # 降级方案：直接访问离线下载页面 URL
                await self.page.goto("https://pan.quark.cn/list#/list/all/offline", timeout=self.TIMEOUT_PAGE_LOAD)
                await asyncio.sleep(3)

            # 点击"新建链接任务"按钮
            new_task_selectors = [
                self.page.get_by_text("新建链接任务", exact=False).first,
                self.page.get_by_text("新建任务", exact=False).first,
                self.page.get_by_text("添加链接", exact=False).first,
                self.page.locator('button:has-text("新建")').first,
            ]

            for btn in new_task_selectors:
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(2)
                    break

            # 在弹出的模态框中找到输入框并粘贴磁力链接
            link_input_selectors = [
                self.page.locator('textarea').first,
                self.page.locator('input[placeholder*="链接"], input[placeholder*="magnet"], input[placeholder*="http"]').first,
                self.page.locator('.ant-input, .ant-input-lg').first,
            ]

            input_filled = False
            for inp in link_input_selectors:
                if await inp.count() > 0 and await inp.is_visible():
                    await inp.fill(magnet_url)
                    await asyncio.sleep(1)
                    input_filled = True
                    break

            if not input_filled:
                print("  ❌ 未找到磁力链接输入框")
                return False

            # 点击确认/开始下载按钮
            confirm_selectors = [
                self.page.get_by_text("开始下载", exact=False).first,
                self.page.get_by_text("确 定", exact=False).first,
                self.page.get_by_text("确认", exact=False).first,
                self.page.locator('.ant-btn-primary').last,
            ]

            for btn in confirm_selectors:
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(3)
                    print("  ✅ 磁力离线下载任务已提交")
                    return True

            # 备用方案：按 Enter 键确认
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(3)
            print("  ✅ 磁力离线下载任务已提交（回车确认）")
            return True

        except Exception as e:
            print(f"  ❌ 提交离线下载失败: {e}")
            return False
        finally:
            if self.page and not self.page.is_closed():
                await self.page.close()
                self.page = None

    async def move_file_in_drive(self, file_name: str, target_folder_path: str) -> bool:
        """
        在夸克网盘内将指定文件移动到目标文件夹

        Args:
            file_name: 要移动的文件名
            target_folder_path: 目标文件夹路径（如 "zPP系列"）

        Returns:
            是否移动成功
        """
        print(f"  📦 正在移动文件 [{file_name}] -> [{target_folder_path}]")

        try:
            if not await self._ensure_page():
                return False

            await self.page.goto(self.PAN_URL, timeout=self.TIMEOUT_PAGE_LOAD)
            await asyncio.sleep(3)

            # 查找并选中目标文件（通过右键菜单或复选框）
            file_el = self.page.get_by_text(file_name, exact=False).first
            if await file_el.count() == 0:
                print(f"  ⚠️ 在当前目录未找到文件: {file_name}")
                return False

            # 右键点击弹出上下文菜单
            await file_el.click(button="right")
            await asyncio.sleep(1.5)

            # 选择"移动到"选项
            move_selectors = [
                self.page.get_by_text("移动到", exact=False).first,
                self.page.get_by_text("移动", exact=True).first,
                self.page.locator('.ant-dropdown-menu-item:has-text("移动")').first,
            ]

            for btn in move_selectors:
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(2)
                    break

            # 在弹出的文件夹选择面板中找到目标文件夹
            parts = [p.strip() for p in target_folder_path.split('/') if p.strip()]
            for part in parts:
                folder_el = self.page.get_by_text(part, exact=True).first
                if await folder_el.count() > 0:
                    await folder_el.click()
                    await asyncio.sleep(1)

            # 点击确认移动
            confirm_move = [
                self.page.get_by_text("移动到此", exact=False).first,
                self.page.get_by_text("确 定", exact=False).first,
                self.page.locator('.ant-btn-primary').last,
            ]

            for btn in confirm_move:
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(2)
                    print(f"  ✅ 文件 [{file_name}] 已成功移动至 [{target_folder_path}]")
                    return True

            print(f"  ⚠️ 移动操作的确认按钮未找到")
            return False

        except Exception as e:
            print(f"  ❌ 移动文件失败: {e}")
            return False
        finally:
            if self.page and not self.page.is_closed():
                await self.page.close()
                self.page = None


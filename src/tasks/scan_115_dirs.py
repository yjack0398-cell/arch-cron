"""
115网盘目录智能扫描与系列配置生成工具

功能：
1. 从指定的 115 网盘目录（CID）开始向下递归扫描。
2. 识别可能的“番号系列”文件夹（如包含多个视频文件）。
3. 使用正则智能提取文件夹内文件的统一番号前缀（prefix）和最大编号（last_number）。
4. 自动合并更新到 `src/config/magnet_series.json`。

用法：
    python src/tasks/scan_115_dirs.py --start_cid 0 --depth 3
"""

import os
import sys
import json
import re
import argparse
import time
from typing import Dict, List, Tuple

# 将 src 目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from p115client import P115Client

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'magnet_series.json')

# 常见的视频文件扩展名
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.wmv', '.rmvb', '.iso', '.ts'}

# 番号提取正则解析器
# 匹配常见的番号格式：字母(1-5个) + 连字符(可选) + 数字(2-5个)
# 例如：SSIS-001, PRED-435, MIDV123, IPZZ-100
PATTERN_SERIAL = re.compile(r'([A-Za-z]{2,5})[-_]?(\d{2,5})')

def init_115_client() -> P115Client:
    """初始化 115 客户端"""
    cookies_raw = os.getenv("COOKIES_115")
    
    if not cookies_raw:
        cookie_file = os.path.join(os.path.dirname(__file__), '..', 'config', '115.com_cookies.json')
        if os.path.exists(cookie_file):
            try:
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    cookies_raw = f.read()
            except Exception as e:
                pass

    if not cookies_raw:
        print("❌ 未找到 COOKIES_115 环境变量，也未找到 115.com_cookies.json 文件")
        sys.exit(1)

    # 尝试解析 JSON 格式的 Cookie
    try:
        data = json.loads(cookies_raw)
        if isinstance(data, list):
            valid_cookies = []
            for c in data:
                if c.get('name') and c.get('value'):
                    # 只保留 115 相关的 cookie，避免请求头过大导致 400 Bad Request
                    domain = c.get('domain', '')
                    if '115.com' in domain:
                        valid_cookies.append(f"{c.get('name')}={c.get('value')}")
            cookie_str = "; ".join(valid_cookies)
        else:
            cookie_str = cookies_raw
    except Exception:
        cookie_str = cookies_raw

    try:
        client = P115Client(cookie_str)
        # 测试登录有效性
        resp = client.fs_files({'cid': 0, 'limit': 1})
        if resp.get('state'):
            print("✅ 115 网盘登录成功")
            return client
        else:
            print(f"❌ 115 登录验证失败: {resp}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 初始化 115 客户端异常: {e}")
        sys.exit(1)


def analyze_directory_content(files: List[dict]) -> Tuple[str, int, int]:
    """
    分析目录下的文件，尝试提取统一的番号前缀和最大编号
    
    Returns:
        (prefix, max_number, valid_video_count)
        如果无法提取出统一后缀，prefix 为 None
    """
    videos = [f for f in files if 'n' in f and 'fid' in f] # fid 存在表示是文件
    videos = [v for v in videos if os.path.splitext(v['n'])[1].lower() in VIDEO_EXTS]
    
    if not videos:
        return None, 0, 0
        
    prefix_counts = {}
    max_numbers = {}
    
    for v in videos:
        name = v['n']
        # 去除通常的无用前缀如 [115.com] 等
        name = re.sub(r'\[.*?\]', '', name)
        
        # 提取经常包含在最前面的广告网址前缀，如 "hhd800.com@FNS-139" => 截断 @
        if '@' in name:
            name = name.split('@')[-1]
            
        # 移除部分顽固的站名/字符串特征，避免误导番号正则（例如 hhd800 完美符合 3字母+数字正则）
        name = re.sub(r'(hhd800|fsm\d+|115\.com|hdza)', '', name, flags=re.IGNORECASE)
        # 去掉如 "m.xxx.com-番号" 中的网址部分
        name = re.sub(r'[a-zA-Z0-9_-]+\.(com|net|org|cn|tv|cc|vip|xyz).*?[-_]', '', name, flags=re.IGNORECASE)
        
        match = PATTERN_SERIAL.search(name)
        if match:
            # 标准化前缀：全部大写，始终带一个连字符
            raw_prefix = match.group(1).upper()
            prefix = f"{raw_prefix}-"
            
            number = int(match.group(2))
            
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
            if prefix not in max_numbers or number > max_numbers[prefix]:
                max_numbers[prefix] = number
                
    if not prefix_counts:
        return None, 0, len(videos)
        
    # 找出最常见的前缀（主导前缀）
    best_prefix = max(prefix_counts.items(), key=lambda x: x[1])[0]
    best_max_num = max_numbers[best_prefix]
    
    # 只有当主导前缀覆盖了至少 30% 的视频文件时，才认为这是一个系列目录
    if prefix_counts[best_prefix] / len(videos) >= 0.3:
        return best_prefix, best_max_num, len(videos)
        
    return None, 0, len(videos)


def scan_115_recursive(client: P115Client, current_cid: int, current_path: str, current_depth: int, max_depth: int, results: dict):
    """
    递归扫描 115 网盘目录
    """
    if current_depth > max_depth:
        return
        
    print(f"  {'  ' * current_depth}📂 正在扫描: {current_path or '/'} (CID: {current_cid})")
    
    try:
        # 获取当前目录下的所有项目（分页获取为了安全起见这里先拿前 500 个）
        # client.fs_files 默认 limit=32，我们需要多拿一点
        items = []
        offset = 0
        limit = 100
        retry_count = 0
        while True:
            try:
                resp = client.fs_files({'cid': current_cid, 'offset': offset, 'limit': limit})
                
                if not resp or not resp.get('state') or 'data' not in resp:
                    break
                    
                batch = resp['data']
            except Exception as req_e:
                # 捕获 405 Method Not Allowed 等由于请求过快的错误
                retry_count += 1
                if retry_count > 3:
                    print(f"  {'  ' * current_depth}⚠️ 网络请求发生连续异常: {req_e}")
                    break
                print(f"  {'  ' * current_depth}⏳ 请求受限或异常，等待 3 秒后重试... ({retry_count}/3)")
                time.sleep(3)
                continue
            
            # 正常请求后清零重试计数，并加很小的延迟防止被 115 继续限流
            retry_count = 0
            time.sleep(0.5)
            
            if not batch:
                break
                
            items.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
            
        # 分离目录和文件
        directories = [i for i in items if 'cid' in i and 'fid' not in i]
        files = [i for i in items if 'fid' in i]
        
        # 分析当前目录的文件内容
        prefix, max_num, vid_count = analyze_directory_content(files)
        
        if prefix and max_num > 0:
            dir_name = os.path.basename(current_path) if current_path else "Root"
            print(f"  {'  ' * current_depth}✨ 发现系列! 目录: [{dir_name}] -> 前缀: {prefix}, 最大编号: {max_num} (包含 {vid_count} 个视频)")
            
            # 记录到结果中
            # 如果配置字典里已经有这个目录名（有可能是用户手动改过），我们以用户为主，不覆盖名字
            # 这里默认以文件夹名字作为 JSON key
            results[dir_name] = {
                "prefix": prefix,
                "last_number": max_num,
                "enabled": True,
                "_debug_path": current_path,
                "_debug_vid_count": vid_count
            }
            
        # 递归扫描子目录
        for d in directories:
            # 过滤掉一些明显的无关目录
            if d['n'].startswith('.') or d['n'] in ('System Volume Information', '$RECYCLE.BIN'):
                continue
                
            next_path = f"{current_path}/{d['n']}" if current_path else d['n']
            scan_115_recursive(client, d['cid'], next_path, current_depth + 1, max_depth, results)
            
    except Exception as e:
        print(f"  {'  ' * current_depth}❌ 扫描失败 CID={current_cid}: {e}")


def update_magnet_json(new_series: dict):
    """将扫描结果合并更新到 magnet_series.json"""
    config_abs = os.path.abspath(CONFIG_PATH)
    
    original = {}
    if os.path.exists(config_abs):
        with open(config_abs, 'r', encoding='utf-8') as f:
            original = json.load(f)
            
    # 如果原始文件是空的或者没配置过说明
    if "_说明" not in original:
        original["_说明"] = "每个 key 是网盘中对应的目录名。此处结构由 scan_115_dirs.py 自动生成。"

    updated_count = 0
    added_count = 0
    
    for key, new_data in new_series.items():
        if key in original and isinstance(original[key], dict) and 'prefix' in original[key]:
            # 已存在，只更新 last_number (如果新的更大)
            old_num = original[key].get('last_number', 0)
            new_num = new_data['last_number']
            if new_num > old_num:
                original[key]['last_number'] = new_num
                updated_count += 1
                print(f"  🔄 更新 [{key}]: {old_num} -> {new_num}")
                
            # 清理无用的 debug 字段以免污染配置
            if '_debug_path' in original[key]:
                del original[key]['_debug_path']
            if '_debug_vid_count' in original[key]:
                del original[key]['_debug_vid_count']
        else:
            # 新增系列
            # 整理出干净的字典写入
            clean_data = {
                "prefix": new_data["prefix"],
                "last_number": new_data["last_number"],
                "enabled": True
            }
            original[key] = clean_data
            added_count += 1
            print(f"  ➕ 新增 [{key}]: {clean_data['prefix']} (最新: {clean_data['last_number']})")
            
    # 只清除占位符配置 (比如前缀是占位符并且 last_number 为 0 的)
    keys_to_delete = []
    for k, v in original.items():
        if isinstance(v, dict) and 'prefix' in v and v.get('last_number') == 0:
            if v['prefix'] in ("PPXXX-", "XXYY-", "PP-", "DLDSS-", "SIS-", "MIDV-", "IPZZ-"):
                if k not in new_series:
                    keys_to_delete.append(k)
    
    for k in keys_to_delete:
        print(f"  🗑️ 移除默认无数据的占位配置: [{k}]")
        del original[k]

    with open(config_abs, 'w', encoding='utf-8') as f:
        json.dump(original, f, ensure_ascii=False, indent=2)
        
    print(f"\n🎉 配置更新完成！成功添加 {added_count} 个新系列，更新了 {updated_count} 个系列的进度。")
    print(f"文件已保存至: {config_abs}")


def main():
    parser = argparse.ArgumentParser(description="115网盘目录智能扫描与系列配置生成")
    parser.add_argument('--start_cid', type=int, default=0, help="扫描起始目录的 CID (默认 0 即根目录)")
    parser.add_argument('--depth', type=int, default=3, help="向下递归扫描的最大深度 (默认 3)")
    args = parser.parse_args()

    print("🚀 115网盘目录智能扫描开始")
    print(f"参数: 起始CID={args.start_cid}, 最大深度={args.depth}\n")

    client = init_115_client()
    
    results = {}
    print(f"开始遍历树状结构...\n")
    scan_115_recursive(
        client=client,
        current_cid=args.start_cid,
        current_path="",
        current_depth=0,
        max_depth=args.depth,
        results=results
    )
    
    if not results:
        print("\n⚠️ 扫描结束，未发现任何符合编号规律的视频系列文件夹。")
        return
        
    print(f"\n✅ 扫描结束，共提取出 {len(results)} 个潜在系列。开始合并到配置文件...")
    update_magnet_json(results)

if __name__ == "__main__":
    main()

import os
import shutil
import hashlib
from pathlib import Path
import re
from collections import defaultdict

# ==========================================
# 🛑 核心配置区域 (正式运行前务必修改这里)
# ==========================================

# 1. 你的 Google Takeout 解压后的根目录
# 包含类似 "Photos from 2020", "旅行相册" 等文件夹的父目录
SOURCE_DIR = r"D:\GoogleTakeout\Takeout\Google 照片"

# 2. 整理后的纯净版输出目录 (脚本会将去重和合并后的文件搬运到这里)
DEST_DIR = r"D:\GooglePhotos_Cleaned"

# 3. 重复文件回收站 (发现的重复项会被挪到这里供最后观察，绝对安全，不会暴力删除)
DUPLICATES_DIR = r"D:\GooglePhotos_Duplicates"

# 4. 演习模式开关：
# True:  只扫描并打印会发生什么，【绝对不会】修改或移动任何本地文件。建议首次必须用 True 跑一遍。
# False: 动真格！实际开始物理移动文件。
DRY_RUN = True

# ==========================================

# 定义我们要处理的媒体文件后缀 (自动过滤掉 Takeout 产生的垃圾 JSON 文件)
MEDIA_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp', # 图片
    '.mp4', '.mov', '.avi', '.mkv', '.webm', '.ts', '.3gp'              # 视频
}

def get_file_hash(filepath, chunk_size=8192):
    """计算文件的 MD5 哈希值，用于在字节层面上验证是否为 100% 相同的文件"""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(f"读取文件出错 {filepath}: {e}")
        return None

def clean_album_name(folder_name):
    """
    清理相册名称，提取出核心名称。
    用于处理 Google Takeout 中出现的 "旅行相册", "旅行相册 (1)", "旅行相册 (2)" 乱象。
    使用正则切割掉末尾的 " (数字)"
    """
    pattern = re.compile(r'^(.*?)( \(\d+\))?$')
    match = pattern.match(folder_name)
    if match:
        return match.group(1).strip()
    return folder_name

def main():
    print("🚀 开始 Google 相册本地去重重组归档工作流...\n")
    if DRY_RUN:
        print("⚠️  [当前处于 DRY_RUN 演习模式] - 只打印日志，物理文件绝对安全！\n")
    else:
        print("🔥  [警告! 当前处于实弹模式] - 文件将实际被剪切和移动！\n")
    
    source_path = Path(SOURCE_DIR)
    dest_path = Path(DEST_DIR)
    dup_path = Path(DUPLICATES_DIR)

    if not source_path.exists():
        print(f"❌ 严重错误: 找不到源目录 '{source_path}'，请检查上方配置！")
        return

    # ---------------------------------------------------------
    # 阶段 1: 扫描并分组同名相册
    # ---------------------------------------------------------
    print("📦 [阶段 1/3] 正在扫描子目录，识别孪生同名相册...")
    
    album_groups = defaultdict(list)
    for item in source_path.iterdir():
        if item.is_dir():
            clean_name = clean_album_name(item.name)
            album_groups[clean_name].append(item)

    album_mapping = {}
    for clean_name, paths in album_groups.items():
        # 基于文件夹在操作系统中的创建时间/修改时间进行排序，将最旧的视为“母本相册”
        paths.sort(key=lambda p: p.stat().st_mtime)
        
        target_album_path = dest_path / clean_name # 融合后的最终相册名
        for p in paths:
            album_mapping[p] = target_album_path

    print(f"    => 分析完毕，共有 {len(album_groups)} 个独立类目，分布在 {len(album_mapping)} 个源文件夹中。\n")

    # ---------------------------------------------------------
    # 阶段 2: 实施文件迁移与严格的哈希重叠检测
    # ---------------------------------------------------------
    print(f"🔍 [阶段 2/3] 开始遍历媒体并执行哈希检测...")
    
    if not DRY_RUN:
        dest_path.mkdir(parents=True, exist_ok=True)
        dup_path.mkdir(parents=True, exist_ok=True)

    seen_hashes = {} 
    stats = {"processed": 0, "moved": 0, "duplicates": 0, "ignored_json": 0, "errors": 0}

    for src_dir, target_album in album_mapping.items():
        # print(f"  > [聚合] {src_dir.name}  ->  {target_album.name}")
        
        if not DRY_RUN:
            target_album.mkdir(parents=True, exist_ok=True)
            
        for file_path in src_dir.rglob('*'):
            if file_path.is_file():
                # 无视无意义的 JSON 元数据文件 (它们没有哈希比对价值，且属于废料)
                if file_path.suffix.lower() not in MEDIA_EXTENSIONS:
                    stats["ignored_json"] += 1
                    continue
                    
                stats["processed"] += 1
                
                # 开始核心：块级读取计算 MD5
                file_hash = get_file_hash(file_path)
                
                if not file_hash:
                    stats["errors"] += 1
                    continue
                
                # 去重逻辑核心分发
                if file_hash in seen_hashes:
                    # 【发现重复】
                    stats["duplicates"] += 1
                    # 防止重复文件名冲突，追加哈希前8位
                    dup_file_dest = dup_path / f"{file_path.stem}_dup_{file_hash[:8]}{file_path.suffix}"
                    
                    if not DRY_RUN:
                        try:
                            shutil.move(str(file_path), str(dup_file_dest))
                        except Exception as e:
                            print(f"    [错误] 移至垃圾站失败: {file_path}")
                else:
                    # 【全新真迹】
                    target_file = target_album / file_path.name
                    
                    # 极端边缘情况：不同文件碰巧同名（例如都叫 IMG_001.JPG 但哈希不同）
                    counter = 1
                    while target_file.exists() and seen_hashes.get(file_hash) != str(target_file):
                        target_file = target_album / f"{file_path.stem}_{counter}{file_path.suffix}"
                        counter += 1
                        
                    seen_hashes[file_hash] = str(target_file)
                    stats["moved"] += 1
                    
                    if not DRY_RUN:
                        try:
                            shutil.move(str(file_path), str(target_file))
                        except Exception as e:
                            print(f"    [错误] 迁移真迹失败: {file_path}")

    # ---------------------------------------------------------
    # 阶段 3: 汇总报告
    # ---------------------------------------------------------
    print("\n✅ [阶段 3/3] 工作流结算报告")
    print("="*40)
    print(f"  ▶ 累计扫描媒体文件:  {stats['processed']}")
    print(f"  ▶ 成功清洗并迁移真迹: {stats['moved']}")
    print(f"  ▶ 拦截致命重复垃圾:  {stats['duplicates']}")
    print(f"  ▶ 自动丢弃附属 JSON:  {stats['ignored_json']}")
    print(f"  ▶ 异常读取失败数目:  {stats['errors']}")
    print("="*40)
    
    if DRY_RUN:
        print("\n💡 温馨提示：目前只是演习，文件原封不动。")
        print("如果您对输出结果感到满意，请将脚本第20行的 DRY_RUN = True 改为 False 后重新运行！")


if __name__ == "__main__":
    main()

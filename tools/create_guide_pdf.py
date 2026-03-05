import os
import markdown
import subprocess

md_path = r"e:\work\xai_public_staging\docs\Google_BigQuery_to_Excel_Ultimate_Guide.md"
html_path = r"e:\work\xai_public_staging\docs\temp_guide.html"
pdf_path = r"e:\work\xai_public_staging\docs\Google_BigQuery_to_Excel_Ultimate_Guide.pdf"

# 1. 读取 Markdown 内容
try:
    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()
except FileNotFoundError:
    print(f"Error: 找不到文件 {md_path}")
    exit(1)

# 2. 转换为带扩展支持的 HTML
html_content = markdown.markdown(text, extensions=['toc', 'extra'])

# 3. 注入排版极致精美的 CSS 样式 (模拟一本高质量出版物)
beautiful_html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>零基础数据架构师之路：Google BigQuery 终极手册</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Microsoft YaHei", sans-serif;
            color: #333;
            line-height: 1.8;
            padding: 40px;
            max-width: 800px;
            margin: auto;
            background-color: #fff;
        }}
        h1 {{
            color: #1a73e8;
            border-bottom: 3px solid #1a73e8;
            padding-bottom: 12px;
            font-size: 2.2em;
            margin-top: 50px;
        }}
        h2 {{
            color: #202124;
            background: #f8f9fa;
            padding: 10px 15px;
            border-left: 5px solid #1a73e8;
            border-radius: 4px;
            margin-top: 40px;
        }}
        h3 {{ color: #e53935; margin-top: 30px; }}
        blockquote {{
            background: #fff8e1;
            border-left: 5px solid #ff9800;
            padding: 15px 20px;
            margin: 20px 0;
            border-radius: 0 4px 4px 0;
            font-style: italic;
            color: #555;
        }}
        code {{
            background-color: #f1f3f4;
            padding: 2px 6px;
            border-radius: 3px;
            color: #d93025;
            font-family: Consolas, monospace;
        }}
        pre {{
            background-color: #f8f9fa;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
            overflow-x: auto;
        }}
        hr {{ border: 0; height: 1px; background: #e0e0e0; margin: 40px 0; }}
        a {{ color: #1a73e8; text-decoration: none; }}
        ul, ol {{ padding-left: 20px; margin-bottom: 20px; }}
        li {{ margin-bottom: 8px; }}
    </style>
</head>
<body>
    {html_content}
</body>
</html>
"""

# 4. 保存为临时 HTML 文件
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(beautiful_html)

# 5. 调用浏览器无外设模式转换
executable_paths = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
]

browser_exe = None
for path in executable_paths:
    if os.path.exists(path):
        browser_exe = path
        break

if not browser_exe:
    print("未能找到系统中的 Edge 或 Chrome 浏览器。转换终止。")
else:
    print(f"找到浏览器引擎: {browser_exe}，正在压制高级排版 PDF...")
    command = [
        browser_exe,
        '--headless',
        '--disable-gpu',
        '--run-all-compositor-stages-before-draw',
        f'--print-to-pdf={pdf_path}',
        f'file:///{html_path.replace(chr(92), "/")}'
    ]
    try:
        subprocess.run(command, check=True)
        print(f"🎉 成功生成高级排版 PDF: {pdf_path}")
    except subprocess.CalledProcessError as e:
        print(f"生成 PDF 时出现错误: {e}")
    finally:
        # 清理残余
        if os.path.exists(html_path):
            os.remove(html_path)

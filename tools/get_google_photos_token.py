import os
import json
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Google Photos API 权限范围
# 我们只需要 appendonly 权限来创建相册和上传媒体
SCOPES = [
    'https://www.googleapis.com/auth/photoslibrary.appendonly',
    'https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata'
]

def main():
    print("="*50)
    print(" Google Photos 自动化授权凭证获取工具")
    print("="*50)
    
    creds = None
    # 生成的 token 会保存在 token.json 中
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        except Exception as e:
            print(f"⚠️ 读取现有 token.json 失败: {e}，将重新授权。")
            
    # 如果没有可用的凭证，让用户登录
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 凭证已过期，尝试刷新...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"⚠️ 刷新凭证失败: {e}，将重新打开浏览器授权。")
                creds = None
                
        if not creds:
            if not os.path.exists('tools/credentials.json'):
                print("❌ 错误：未找到 'tools/credentials.json' 文件！\n")
                print("请按照以下步骤获取：")
                print("1. 访问 Google Cloud Console: https://console.cloud.google.com/")
                print("2. 创建一个新项目并启用 'Photos Library API'")
                print("3. 前往 'API 和服务' -> 'OAuth 同意屏幕' 配置为外部，并在测试用户中加入你的自己账号邮箱")
                print("4. 前往 '凭据' -> 点击 '创建凭据' -> 选择 'OAuth 客户端 ID'")
                print("5. 应用类型选择 '桌面应用' (Desktop App)")
                print("6. 下载 JSON 格式凭据文件，重命名为 'credentials.json' 并放在本脚本同一级目录(tools/)下。")
                return
            
            print("🌐 准备打开浏览器进行 Google 账号授权...")
            try:
                flow = InstalledAppFlow.from_client_secrets_file('tools/credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                print(f"❌ 授权过程失败: {e}")
                return
            
        # 将授权信息保存给后续运行使用
        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())
            
    print("\n✅ 授权成功！")
    print("已在当前目录生成 'token.json' 文件。")
    print("-" * 50)
    
    # 读取出 token 内容并对其进行 BASE64 编码，方便直接填入 GitHub Secrets
    with open('token.json', 'r') as token_file:
        token_str = token_file.read()
        encoded = base64.b64encode(token_str.encode('utf-8')).decode('utf-8')
        
    print("🎯 请将以下完整内容 (包括 ==) 复制粘贴到 GitHub Secrets 的 GOOGLE_PHOTOS_TOKEN 中：\n")
    print(encoded)
    print("\n" + "-" * 50)
    print("⚠️ 提示: 以后该脚本可随时运行以重新获取 Token。")

if __name__ == '__main__':
    main()

import os
import time
import sys

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("❌ 缺少官方 SDK！请先在终端运行安装命令: pip install google-genai")
    sys.exit(1)

# 1. 初始化鉴权
# 推荐做法是在执行前设置环境变量:
# Windows (PowerShell): $env:GEMINI_API_KEY="你的_api_key"
# Windows (CMD): set GEMINI_API_KEY=你的_api_key
# Mac/Linux: export GEMINI_API_KEY="你的_api_key"

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    # 填入您的真实 API 密钥，或者在 GitHub Action 中配置 Secrets 并在 env 中导出
    print("❌ 错误：未配置 GEMINI_API_KEY。请在环境变量或 GitHub Secrets 中设置它。")
    sys.exit(1)

# 创建客户端
client = genai.Client(api_key=api_key)

def generate_video_auto():
    # 这里自定义您的提示词内容
    prompt = "A futuristic city skyline at sunset, with flying cars and neon lights, high quality, cinematic lighting, 4k"
    
    # 支持的模型 (根据官方文档): 
    # - veo-3.1-generate-preview (画质最好，生成较慢，成本高)
    # - veo-3.1-fast-generate-preview (生成更快，适合快速预览)
    # - veo-2.0-generate-001 (Veo 2 模型)
    model_name = "veo-2.0-generate-001"
    
    print(f"🚀 开始提交视频生成任务...\n提示词: {prompt}\n模型: {model_name}")

    try:
        # 2. 调用最新 Veo 3.1 模型生成视频
        operation = client.models.generate_videos(
            model=model_name, 
            prompt=prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio="16:9", # 其他支持的比例详见文档
            )
        )
        
        print(f"⏳ 任务已提交! Operation Name: {getattr(operation, 'name', 'N/A')}")
        print("因为渲染环境需要极高的算力，这通常需要几分钟。请耐心等待...")
        
        # 3. 轮询获取最新状态
        while not operation.done:
            print("查询状态中...")
            time.sleep(15) # 官方建议每 10~15 秒轮询一次
            # 刷新操作状态 (注意最新 SDK 应该传入 operation 本身，而不是 operation.name)
            operation = client.operations.get(operation)
            
        # 4. 判断结果
        if operation.error:
            print(f"❌ 视频生成失败: {operation.error}")
            return
            
        print("✅ 视频生成完毕！开始下载保存...")
        
        # 5. 结果落盘 (基于最新的 google-genai 文档)
        if hasattr(operation.response, 'generated_videos') and operation.response.generated_videos:
             generated_video = operation.response.generated_videos[0]
             
             # 获取带有下载链接的完整文件对象
             client.files.download(file=generated_video.video)
             
             output_filename = f"generated_video_{int(time.time())}.mp4"
             generated_video.video.save(output_filename)
             
             print(f"🎉 成功！文件已保存到当前目录: {output_filename}")
        else:
             print("⚠️ 响应中没有包含生成的视频信息。")
             print(operation.response)
             
    except Exception as e:
        print(f"❌ 发生异常: {e}")
        print("如果是认证错误，请检查 API Key。如果是 Quota/权限错误，说明当前账号尚未对 Veo 3.1 获取相应的白名单权限，或额度不足。")

if __name__ == "__main__":
    generate_video_auto()

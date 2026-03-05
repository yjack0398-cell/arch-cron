import os
import sys
import time

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("❌ 缺少官方 SDK！请先在终端运行安装命令: pip install google-genai")
    sys.exit(1)

# 获取环境变量中的 API Key
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    # 填入您的真实 API 密钥，或者在环境变量中设置
    print("❌ 错误：未配置 GEMINI_API_KEY。请在环境变量中设置。")
    sys.exit(1)

# 创建客户端
client = genai.Client(api_key=api_key)

def generate_image_auto():
    # 自定义提示词
    prompt = "Create a vivid picture of a futuristic cyberpunk city with flying neon cars"
    
    # 使用最新的 Gemini 3.1 Flash Image (Nano Banana 2)
    model_name = "gemini-3.1-flash-image-preview"
    
    print(f"🚀 开始提交图像生成任务...\n提示词: {prompt}\n模型: {model_name}")

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"], # 强制要求只返回图像
                image_config=types.ImageConfig(
                    aspect_ratio="16:9",
                    image_size="2K" # 3.1 flash 支持 2K 甚至 4K (通过图片扩写特性)
                )
            )
        )
        
        # 结果落盘
        saved_count = 0
        if response.parts:
            for i, part in enumerate(response.parts):
                if part.text:
                    print(f"文本回复: {part.text}")
                elif part.inline_data:
                    output_filename = f"generated_image_{int(time.time())}_{i}.png"
                    # 从 inline_data 提取 image 并保存
                    image = part.as_image()
                    image.save(output_filename)
                    print(f"🎉 成功！图像已保存在当前目录下: {output_filename}")
                    saved_count += 1
        
        if saved_count == 0:
            print("⚠️ 未生成任何图片，响应内容如下：")
            print(response.model_dump_json(indent=2))

    except Exception as e:
        print(f"❌ 发生异常: {e}")
        print("遇到错误可能的原因：API 密钥无效、网络不支持、或配额受限。")

if __name__ == "__main__":
    generate_image_auto()

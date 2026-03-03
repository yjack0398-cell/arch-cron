import os
import json
import base64
import asyncio
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import requests

class GooglePhotosUploader:
    def __init__(self, token_base64: str):
        """
        初始化 Google Photos 客户端。
        :param token_base64: 存放在环境变量中经过 Base64 编码的 token.json 内容。
        """
        self.creds = None
        self.service = None
        self._album_cache = {}
        self._authenticate(token_base64)

    def _authenticate(self, token_base64: str):
        try:
            token_json_str = base64.b64decode(token_base64).decode('utf-8')
            token_data = json.loads(token_json_str)
            self.creds = Credentials.from_authorized_user_info(token_data)
            self.service = build('photoslibrary', 'v1', credentials=self.creds, static_discovery=False)
            print("✅ Google Photos 客户端初始化并验权成功。")
        except Exception as e:
            raise Exception(f"Google Photos 鉴权失败: {e}")

    def _get_or_create_album(self, album_name: str) -> str:
        """
        查找或创建相册，返回 Album ID。
        注意：API 只能列出由当前应用（Client ID）创建的相册。
        """
        if album_name in self._album_cache:
            if self._album_cache[album_name] is None:
                return None
            return self._album_cache[album_name]

        max_retries = 4
        for attempt in range(max_retries):
            try:
                # 首先列出相册
                response = self.service.albums().list(pageSize=50, excludeNonAppCreatedData=True).execute()
                albums = response.get('albums', [])

                for album in albums:
                    if album.get('title') == album_name:
                        self._album_cache[album_name] = album.get('id')
                        return album.get('id')

                # 如果不存在，则创建新相册
                print(f"  📂 (Google Photos) 正在新建相册: {album_name}")
                create_body = {
                    "album": {
                        "title": album_name
                    }
                }
                new_album = self.service.albums().create(body=create_body).execute()
                self._album_cache[album_name] = new_album.get('id')
                return new_album.get('id')
                
            except HttpError as e:
                if e.resp.status == 429:
                    wait_time = 15 * (attempt + 1)
                    print(f"⚠️  (Google Photos) 相册API触发速率限制 (429)，等待 {wait_time} 秒后重试 ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ (Google Photos) 获取/创建相册失败 (HttpError): {e}")
                    self._album_cache[album_name] = None
                    return None
            except Exception as e:
                print(f"❌ (Google Photos) 获取/创建相册过程发生异常: {e}")
                self._album_cache[album_name] = None
                return None

        # 如果尝试全部失败，标记为空以防止后续相同文件的风暴轰炸
        print(f"❌ (Google Photos) {album_name} 获取/创建重试耗尽。")
        self._album_cache[album_name] = None
        return None

    def _upload_bytes(self, local_file: str) -> str:
        """
        第一步：上传文件的字节码并获取 uploadToken。
        """
        upload_url = 'https://photoslibrary.googleapis.com/v1/uploads'
        headers = {
            'Authorization': f'Bearer {self.creds.token}',
            'Content-type': 'application/octet-stream',
            'X-Goog-Upload-File-Name': os.path.basename(local_file),
            'X-Goog-Upload-Protocol': 'raw'
        }

        try:
            with open(local_file, 'rb') as f:
                response = requests.post(upload_url, headers=headers, data=f)
                
            if response.status_code == 200:
                # 成功返回 uploadToken 纯文本
                return response.text
            else:
                print(f"❌ (Google Photos) 获取 uploadToken 失败: HTTP {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"❌ (Google Photos) 上传字节流异常: {e}")
            return None

    def upload_file(self, local_file: str, album_name: str = "Twitter_Archive") -> bool:
        """
        上传文件到相册。
        :param local_file: 待上传文件本地路径
        :param album_name: 所属相册标题 (API将查找或创建这个相册)
        """
        filename = os.path.basename(local_file)
        
        # 1. 获取或创建相册 ID
        album_id = self._get_or_create_album(album_name)
        if not album_id:
            return False

        # 2. 上传二进制文件并获取 token
        upload_token = self._upload_bytes(local_file)
        if not upload_token:
            return False

        # 3. 将 uploadToken 与相册关联 (BatchCreateMediaItems)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                body = {
                    "albumId": album_id,
                    "newMediaItems": [
                        {
                            "description": f"Archived from {album_name} automatically.",
                            "simpleMediaItem": {
                                "fileName": filename,
                                "uploadToken": upload_token
                            }
                        }
                    ]
                }
                
                result = self.service.mediaItems().batchCreate(body=body).execute()
                # 检查是否有错误返回
                new_media_item_results = result.get('newMediaItemResults', [])
                if new_media_item_results:
                    status = new_media_item_results[0].get('status', {})
                    if status.get('message') == 'Success':
                        print(f"  ✅ {filename} 成功加入 Google Photos ({album_name})")
                        return True
                    else:
                        print(f"  ❌ 加入 Google Photos 失败: {status}")
                        return False
                else:
                    print(f"  ❌ 加入 Google Photos 响应异常: {result}")
                    return False
                    
            except HttpError as e:
                if e.resp.status == 429:
                    wait_time = 60
                    print(f"⚠️  (Google Photos) 触发请求速率限制 (429)，等待 {wait_time} 秒后重试 ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ (Google Photos) batchCreate调用异常 (HTTP {e.resp.status}): {e}")
                    return False
            except Exception as e:
                print(f"❌ (Google Photos) batchCreate调用异常: {e}")
                return False
                
        print(f"❌ (Google Photos) {filename} 上传失败，已达到最大重试次数。")
        return False

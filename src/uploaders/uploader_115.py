import os
import glob
from p115client import P115Client

from core.utils.cookie_utils import parse_cookies_to_string

class Uploader115:
    def __init__(self, cookies_raw: str):
        self.cookies_raw = cookies_raw
        self.client = self._login()

    def _login(self):
        cookie_str = parse_cookies_to_string(self.cookies_raw)
        if not cookie_str:
            print("❌ 无法解析 115 Cookie")
            return None
        
        try:
            client = P115Client(cookie_str)
            resp = client.fs_files({'cid': 0, 'limit': 1})
            if resp.get('state'):
                return client
            else:
                print(f"⚠️ 115 登录验证返回异常: {resp}")
        except Exception as e:
            print(f"❌ 初始化 115 失败: {e}")
            return None
            
    def get_or_create_cid(self, parent_cid, dir_name):
        try:
            resp = self.client.fs_files({'cid': parent_cid, 'limit': 1000})
            if resp['state']:
                for item in resp['data']:
                    if item['n'] == dir_name and 'cid' in item:
                        return item['cid']
            
            resp_add = self.client.fs_mkdir({'pid': parent_cid, 'cname': dir_name})
            if resp_add['state']:
                data = resp_add.get('data')
                if not data:
                    if 'cid' in resp_add: return resp_add['cid']
                    if 'id' in resp_add: return resp_add['id']
                    if 'file_id' in resp_add: return resp_add['file_id']
                    raise Exception(f"响应缺少 data 字段: {resp_add}")
                if 'cid' in data: return data['cid']
                if 'id' in data: return data['id']
                if 'file_id' in data: return data['file_id']
            raise Exception(f"创建目录失败: {resp_add}")
        except Exception as e:
            raise e

    def _upload_file(self, local_file, pid):
        import hashlib
        # 1: tool module
        try:
            from p115client.tool import upload_file as tool_upload
            tool_upload(self.client, local_file, pid)
            return
        except ImportError:
            pass
        except Exception as e:
            if "errno': 99" in str(e) or "请重新登录" in str(e): raise
            
        # 2: upload_file_sample
        try:
            if hasattr(self.client, 'upload_file_sample'):
                self.client.upload_file_sample(local_file, pid)
                return
        except Exception as e:
            if "errno': 99" in str(e) or "请重新登录" in str(e): raise
            
        # 3: Web API fallback
        try:
            import requests
            filename = os.path.basename(local_file)
            filesize = os.path.getsize(local_file)
            
            sha1 = hashlib.sha1()
            with open(local_file, 'rb') as f:
                while chunk := f.read(8192):
                    sha1.update(chunk)
            file_sha1 = sha1.hexdigest().upper()
            
            cookie_str = parse_cookies_to_string(self.cookies_raw)
            headers = {'Cookie': cookie_str, 'User-Agent': 'Mozilla/5.0'}
            
            init_url = 'https://uplb.115.com/3.0/sampleinitupload.php'
            init_data = {'filename': filename, 'filesize': str(filesize), 'target': f'U_1_{pid}', 'fileid': file_sha1}
            resp = requests.post(init_url, data=init_data, headers=headers)
            result = resp.json()
            
            if result.get('status') == 2: return
            if result.get('status') == 1 and result.get('host'):
                upload_url = result['host']
                upload_data = {'target': f'U_1_{pid}', 'fileid': file_sha1, 'filename': filename, 'filesize': str(filesize)}
                if result.get('object'): upload_data['object'] = result['object']
                if result.get('callback'): upload_data['callback'] = result['callback']
                
                with open(local_file, 'rb') as f:
                    upload_resp = requests.post(upload_url, data=upload_data, files={'file': (filename, f)}, headers=headers)
                    upload_result = upload_resp.json()
                if upload_result.get('state'): return
                else: raise Exception(f"Web 上传失败: {upload_result}")
            else:
                raise Exception(f"初始化上传失败: {result}")
        except ImportError:
            raise Exception("需要安装 requests 库")

    def upload_files(self, files: list, remote_root: str, user_name: str, today_str: str):
        if not self.client: return
        if not files: return
        
        print(f"☁️ 准备上传 {len(files)} 个文件到 115...")
        try:
            archive_cid = self.get_or_create_cid(0, remote_root)
            user_cid = self.get_or_create_cid(archive_cid, user_name)
            date_cid = self.get_or_create_cid(user_cid, today_str)
            
            for local_file in files:
                filename = os.path.basename(local_file)
                try:
                    self._upload_file(local_file, date_cid)
                    print(f"  ✅ {filename} 上传成功")
                except Exception as ue:
                    print(f"  ❌ {filename} 上传失败: {ue}")
        except Exception as e:
            err_str = str(e)
            if "errno': 99" in err_str or "请重新登录" in err_str:
                print(f"❌ 115 上传失败: Cookie 已过期！({e})")
            else:
                print(f"❌ 115 上传出错: {e}")

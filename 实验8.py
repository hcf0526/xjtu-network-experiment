import socket
import ssl
import re
import os
import zlib
import time
from urllib.parse import urlparse, unquote, quote
from base64 import b64encode
from email.parser import Parser
from collections import defaultdict


class HTTPClient:
    def __init__(self, user_agent="MyHTTPClient", timeout=10, max_redirects=5, cache_dir=".http_cache"):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.cookies = {}
        self.cache_dir = cache_dir
        self.cache = {}
        self.connection_pool = {}  # 连接池用于Keep-Alive

        # 创建缓存目录
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        # 加载现有缓存
        self._load_cache()

    def _load_cache(self):
        """加载磁盘上的缓存"""
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.cache'):
                    with open(os.path.join(self.cache_dir, filename), 'r', encoding='utf-8') as f:
                        url = filename[:-6]
                        headers = {}
                        content = []
                        is_header = True
                        for line in f:
                            if is_header:
                                if line.strip() == '':
                                    is_header = False
                                    continue
                                key, value = line.strip().split(': ', 1)
                                headers[key] = value
                            else:
                                content.append(line)
                        self.cache[url] = {
                            'headers': headers,
                            'content': ''.join(content),
                            'timestamp': os.path.getmtime(os.path.join(self.cache_dir, filename))
                        }
        except Exception as e:
            print(f"Warning: Failed to load cache: {e}")

    def _save_to_cache(self, url, headers, content):
        """将响应保存到缓存"""
        try:
            cache_file = os.path.join(self.cache_dir, quote(url, safe='') + '.cache')
            with open(cache_file, 'w', encoding='utf-8') as f:
                for key, value in headers.items():
                    f.write(f"{key}: {value}\n")
                f.write('\n')
                f.write(content)
            self.cache[url] = {
                'headers': headers,
                'content': content,
                'timestamp': time.time()
            }
        except Exception as e:
            print(f"Warning: Failed to save cache: {e}")

    def _get_from_cache(self, url):
        """从缓存获取响应"""
        cached = self.cache.get(url)
        if cached:
            # 检查缓存是否过期
            cache_control = cached['headers'].get('Cache-Control', '')
            max_age = 0
            if 'max-age=' in cache_control:
                max_age = int(cache_control.split('max-age=')[1].split(',')[0])

            expires = cached['headers'].get('Expires', '')
            expire_time = 0
            if expires:
                try:
                    expire_time = time.mktime(time.strptime(expires, '%a, %d %b %Y %H:%M:%S GMT'))
                except ValueError:
                    pass

            current_time = time.time()
            if (max_age > 0 and current_time - cached['timestamp'] < max_age) or \
                    (expire_time > 0 and current_time < expire_time):
                return cached['content'], cached['headers']

        return None, None

    def _parse_url(self, url):
        """解析URL，返回协议、主机、端口、路径"""
        parsed = urlparse(url)
        protocol = parsed.scheme
        host = parsed.hostname
        port = parsed.port or (443 if protocol == 'https' else 80)
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        return protocol, host, port, path

    def _create_socket(self, host, port, protocol):
        """创建socket连接"""
        key = f"{host}:{port}"

        # 检查连接池中是否有可用的Keep-Alive连接
        if key in self.connection_pool:
            sock, last_used = self.connection_pool[key]
            # 检查连接是否还活跃（简单检查：如果最近使用过则认为是活跃的）
            if time.time() - last_used < 5:  # 5秒内使用过
                return sock

        # 创建新连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)

        if protocol == 'https':
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)

        sock.connect((host, port))
        return sock

    def _release_socket(self, sock, host, port, connection_header):
        """根据Connection头决定是关闭连接还是放回连接池"""
        key = f"{host}:{port}"

        if connection_header.lower() == 'keep-alive':
            # 放回连接池
            self.connection_pool[key] = (sock, time.time())
        else:
            # 关闭连接
            try:
                sock.close()
            except:
                pass
            if key in self.connection_pool:
                del self.connection_pool[key]

    def _parse_headers(self, header_lines):
        """解析HTTP头"""
        headers = {}
        for line in header_lines:
            if ': ' in line:
                key, value = line.split(': ', 1)
                headers[key.lower()] = value.strip()
        return headers

    def _decode_content(self, content, headers):
        """根据内容编码解码内容"""
        encoding = headers.get('content-encoding', '').lower()

        if 'gzip' in encoding or 'x-gzip' in encoding:
            try:
                content = zlib.decompress(content, 16 + zlib.MAX_WBITS)
            except:
                pass
        elif 'deflate' in encoding:
            try:
                content = zlib.decompress(content)
            except:
                try:
                    content = zlib.decompress(content, -zlib.MAX_WBITS)
                except:
                    pass

        transfer_encoding = headers.get('transfer-encoding', '').lower()
        if 'chunked' in transfer_encoding:
            content = self._decode_chunked(content)

        return content

    def _decode_chunked(self, data):
        """解码分块传输编码"""
        result = bytearray()
        while True:
            # 查找块大小行
            pos = data.find(b'\r\n')
            if pos == -1:
                break
            chunk_size_line = data[:pos]
            try:
                chunk_size = int(chunk_size_line, 16)
            except ValueError:
                break

            # 0大小的块表示结束
            if chunk_size == 0:
                break

            # 移动到块数据开始位置
            data = data[pos + 2:]
            if len(data) < chunk_size:
                break

            # 添加块数据到结果
            result.extend(data[:chunk_size])
            data = data[chunk_size + 2:]  # 跳过CRLF

        return bytes(result)

    def _handle_redirect(self, response_headers, method):
        """处理重定向"""
        location = response_headers.get('location')
        if not location:
            return None

        # 对于POST请求，301/302应该转换为GET（根据RFC 2616）
        new_method = 'GET' if method == 'POST' and response_headers.get('status') in ('301', '302') else method

        return location, new_method

    def _update_cookies(self, response_headers, url):
        """从响应头更新cookies"""
        parsed = urlparse(url)
        domain = parsed.hostname

        if 'set-cookie' in response_headers:
            cookie_lines = response_headers['set-cookie'].split('\n') if isinstance(response_headers['set-cookie'],
                                                                                    str) else response_headers[
                'set-cookie']

            for line in cookie_lines:
                if not line.strip():
                    continue

                # 解析cookie属性
                parts = [p.strip() for p in line.split(';')]
                name_value = parts[0].split('=', 1)
                if len(name_value) != 2:
                    continue

                name, value = name_value
                cookie = {'value': value, 'domain': domain}

                # 解析其他属性
                for part in parts[1:]:
                    if '=' in part:
                        attr, val = part.split('=', 1)
                    else:
                        attr, val = part, True

                    attr = attr.lower()
                    if attr == 'expires':
                        cookie['expires'] = val
                    elif attr == 'path':
                        cookie['path'] = val
                    elif attr == 'domain':
                        cookie['domain'] = val
                    elif attr == 'secure':
                        cookie['secure'] = True
                    elif attr == 'httponly':
                        cookie['httponly'] = True

                # 存储cookie
                self.cookies[name] = cookie

    def _get_cookie_header(self, url):
        """为请求生成Cookie头"""
        parsed = urlparse(url)
        domain = parsed.hostname
        path = parsed.path

        cookies = []
        for name, cookie in self.cookies.items():
            # 检查domain匹配
            cookie_domain = cookie.get('domain', domain)
            if not (domain.endswith(cookie_domain) or cookie_domain.endswith(domain)):
                continue

            # 检查path匹配
            cookie_path = cookie.get('path', '/')
            if not path.startswith(cookie_path):
                continue

            # 检查secure
            if cookie.get('secure') and parsed.scheme != 'https':
                continue

            # 检查过期时间
            if 'expires' in cookie:
                try:
                    expires = time.mktime(time.strptime(cookie['expires'], '%a, %d-%b-%Y %H:%M:%S GMT'))
                    if time.time() > expires:
                        del self.cookies[name]
                        continue
                except:
                    pass

            cookies.append(f"{name}={cookie['value']}")

        return '; '.join(cookies) if cookies else None

    def _build_request(self, method, url, headers=None, body=None):
        """构建HTTP请求"""
        protocol, host, port, path = self._parse_url(url)

        # 默认头
        request_headers = {
            'Host': host,
            'User-Agent': self.user_agent,
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'Keep-Alive'
        }

        # 添加自定义头
        if headers:
            for key, value in headers.items():
                request_headers[key] = value

        # 添加Cookie头
        cookie_header = self._get_cookie_header(url)
        if cookie_header:
            request_headers['Cookie'] = cookie_header

        # 构建请求行和头
        request_line = f"{method} {path} HTTP/1.1\r\n"
        header_lines = [f"{key}: {value}\r\n" for key, value in request_headers.items()]

        # 如果有请求体，添加Content-Length
        if body:
            if isinstance(body, str):
                body = body.encode('utf-8')
            request_headers['Content-Length'] = str(len(body))
            header_lines = [f"{key}: {value}\r\n" for key, value in request_headers.items()]

        # 组合请求
        request = request_line + ''.join(header_lines) + '\r\n'
        if body:
            if isinstance(request, str):
                request = request.encode('utf-8') + body
            else:
                request += body

        return protocol, host, port, request

    def _send_request(self, method, url, headers=None, body=None):
        """发送HTTP请求并返回响应"""
        redirect_count = 0
        while redirect_count < self.max_redirects:
            # 检查缓存
            cached_content, cached_headers = self._get_from_cache(url)
            if cached_content is not None and method == 'GET':
                if 'etag' in cached_headers:
                    headers = headers or {}
                    headers['If-None-Match'] = cached_headers['etag']
                if 'last-modified' in cached_headers:
                    headers = headers or {}
                    headers['If-Modified-Since'] = cached_headers['last-modified']

            # 构建请求
            protocol, host, port, request = self._build_request(method, url, headers, body)

            # 发送请求
            sock = self._create_socket(host, port, protocol)

            try:
                if isinstance(request, str):
                    sock.sendall(request.encode('utf-8'))
                else:
                    sock.sendall(request)

                # 接收响应
                response = bytearray()
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response.extend(chunk)

                # 解析响应
                response_str = response.decode('latin-1')  # 先用latin-1解码以保留原始字节
                header_end = response_str.find('\r\n\r\n')
                if header_end == -1:
                    raise ValueError("Invalid HTTP response: no header end")

                headers_part = response_str[:header_end]
                body_part = response[header_end + 4:]

                # 解析状态行和头
                header_lines = headers_part.split('\r\n')
                status_line = header_lines[0]
                response_headers = self._parse_headers(header_lines[1:])

                # 解码内容
                body_part = self._decode_content(body_part, response_headers)

                # 处理重定向
                redirect = self._handle_redirect(response_headers, method)
                if redirect:
                    redirect_url, new_method = redirect
                    url = redirect_url if urlparse(redirect_url).scheme else f"{protocol}://{host}{redirect_url}"
                    method = new_method
                    redirect_count += 1
                    continue

                # 更新cookies
                self._update_cookies(response_headers, url)

                # 处理缓存
                if method == 'GET' and 'status' in response_headers and response_headers['status'] == '200':
                    self._save_to_cache(url, response_headers, body_part.decode('utf-8', errors='ignore'))

                # 返回响应
                return {
                    'status': status_line.split(' ')[1] if ' ' in status_line else '',
                    'headers': response_headers,
                    'content': body_part
                }

            finally:
                connection_header = response_headers.get('connection',
                                                         'close').lower() if 'response_headers' in locals() else 'close'
                self._release_socket(sock, host, port, connection_header)

        raise ValueError(f"Too many redirects (>{self.max_redirects})")

    def get(self, url, headers=None, save_to=None):
        """发送GET请求"""
        response = self._send_request('GET', url, headers)

        if save_to:
            with open(save_to, 'wb') as f:
                f.write(response['content'])

        return response

    def head(self, url, headers=None):
        """发送HEAD请求"""
        return self._send_request('HEAD', url, headers)

    def post(self, url, data=None, headers=None, files=None, save_to=None):
        """发送POST请求"""
        if files:
            boundary = '----WebKitFormBoundary' + ''.join([str(i) for i in os.urandom(8)])
            body = bytearray()

            for name, file_info in files.items():
                if isinstance(file_info, tuple):
                    filename, fileobj = file_info
                else:
                    filename = os.path.basename(file_info)
                    fileobj = open(file_info, 'rb')

                body.extend(f'--{boundary}\r\n'.encode('utf-8'))
                body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode('utf-8'))
                body.extend(b'Content-Type: application/octet-stream\r\n\r\n')
                body.extend(fileobj.read())
                body.extend(b'\r\n')

                if not isinstance(file_info, tuple):
                    fileobj.close()

            if data:
                for key, value in data.items():
                    body.extend(f'--{boundary}\r\n'.encode('utf-8'))
                    body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode('utf-8'))
                    body.extend(str(value).encode('utf-8'))
                    body.extend(b'\r\n')

            body.extend(f'--{boundary}--\r\n'.encode('utf-8'))

            headers = headers or {}
            headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
            response = self._send_request('POST', url, headers, body)
        else:
            if data:
                if isinstance(data, dict):
                    body = '&'.join([f"{key}={quote(str(value))}" for key, value in data.items()])
                    headers = headers or {}
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                else:
                    body = data

                response = self._send_request('POST', url, headers, body)
            else:
                response = self._send_request('POST', url, headers)

        if save_to and response:
            with open(save_to, 'wb') as f:
                f.write(response['content'])

        return response

    def download_page(self, url, save_dir='.'):
        """下载网页及其所有嵌入资源"""
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # 下载主页面
        response = self.get(url)
        if response['status'] != '200':
            raise ValueError(f"Failed to download page: HTTP {response['status']}")

        # 保存主页面
        main_file = os.path.join(save_dir, 'index.html')
        with open(main_file, 'wb') as f:
            f.write(response['content'])

    # 解析HTML查找嵌入资源
        content_type = response['headers'].get('content-type', '').lower()
        if 'html' in content_type:
            html_content = response['content'].decode('utf-8', errors='ignore')

            # 查找所有可能的嵌入资源
            patterns = {
                'img': r'<img[^>]+src="([^"]+)"',
                'script': r'<script[^>]+src="([^"]+)"',
                'link': r'<link[^>]+href="([^"]+)"',
                'css_url': r'url$["\']?([^)"\']+)["\']?$'
            }

            resources = set()
            for pattern in patterns.values():
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                resources.update(matches)

            # 下载所有资源
            for resource_url in resources:
                try:
                    # 处理相对URL
                    if not urlparse(resource_url).scheme:
                        base_url = urlparse(url)
                        resource_url = f"{base_url.scheme}://{base_url.netloc}{resource_url if resource_url.startswith('/') else '/' + resource_url}"

                    # 下载资源
                    res_response = self.get(resource_url)
                    if res_response['status'] == '200':
                        # 创建资源保存路径
                        res_path = urlparse(resource_url).path
                        res_filename = os.path.basename(res_path) or 'resource.bin'
                        res_save_path = os.path.join(save_dir, res_filename)

                        # 确保目录存在
                        os.makedirs(os.path.dirname(res_save_path), exist_ok=True)

                        # 保存资源
                        with open(res_save_path, 'wb') as f:
                            f.write(res_response['content'])
                except Exception as e:
                    print(f"Warning: Failed to download resource {resource_url}: {e}")


    def download_resources(self, url, pattern='.pdf', save_dir='.'):
        """下载网页中特定类型的资源"""
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # 下载主页面
        response = self.get(url)
        if response['status'] != '200':
            raise ValueError(f"Failed to download page: HTTP {response['status']}")

        # 解析HTML查找特定资源
        html_content = response['content'].decode('utf-8', errors='ignore')
        resource_urls = re.findall(r'href="([^"]*' + re.escape(pattern) + r')"', html_content, re.IGNORECASE)
        resource_urls += re.findall(r'src="([^"]*' + re.escape(pattern) + r')"', html_content, re.IGNORECASE)

        # 下载所有匹配的资源
        downloaded_files = []
        for resource_url in set(resource_urls):
            try:
                # 处理相对URL
                if not urlparse(resource_url).scheme:
                    base_url = urlparse(url)
                    resource_url = f"{base_url.scheme}://{base_url.netloc}{resource_url if resource_url.startswith('/') else '/' + resource_url}"

                # 下载资源
                res_response = self.get(resource_url)
                if res_response['status'] == '200':
                    # 创建资源保存路径
                    res_path = urlparse(resource_url).path
                    res_filename = os.path.basename(res_path) or 'resource.bin'
                    res_save_path = os.path.join(save_dir, res_filename)

                    # 确保文件名唯一
                    counter = 1
                    while os.path.exists(res_save_path):
                        name, ext = os.path.splitext(res_filename)
                        res_save_path = os.path.join(save_dir, f"{name}_{counter}{ext}")
                        counter += 1

                    # 保存资源
                    with open(res_save_path, 'wb') as f:
                        f.write(res_response['content'])
                    downloaded_files.append(res_save_path)
            except Exception as e:
                print(f"Warning: Failed to download resource {resource_url}: {e}")

        return downloaded_files


    def login(self, login_url, username, password, username_field='username', password_field='password', extra_fields=None):
        """执行网站登录"""
        data = {
            username_field: username,
            password_field: password
        }

        if extra_fields:
            data.update(extra_fields)

        response = self.post(login_url, data=data)
        return response['status'] == '200' or response['status'] == '302'
if __name__ == '__main__':
    client = HTTPClient(user_agent="chen wen xuan")
    # 测试GET请求
    print("Testing GET request...")
    response = client.get("http://pksy.xjtu.edu.cn/")
    print(f"Status: {response['status']}")
    print(f"Headers: {response['headers']}")
    print(f"Content length: {len(response['content'])}")

    # 测试下载页面及其资源
    print("\nTesting page download...")
    client.download_page("http://10.172.72.235:12345/", save_dir="example_page1")
    print("Page and resources downloaded to 'example_page' directory")

    # 测试POST请求和登录
    print("\nTesting POST request and login...")
    login_success = client.login(
        "https://example.com/login",
        "testuser",
        "testpass",
        username_field="user",
        password_field="pass"
    )
    print(f"Login {'successful' if login_success else 'failed'}")

    # 测试下载特定资源
    # print("\nTesting resource download...")
    # pdfs = client.download_resources("https://example.com/documents", pattern=".pdf", save_dir="pdf_downloads")
    # print(f"Downloaded PDFs: {pdfs}")

    # 测试HTTPS
    print("\nTesting HTTPS...")
    https_response = client.get("https://www.xjtu.edu.cn")
    print(f"HTTPS Status: {https_response['status']}")

    # 测试文件上传
    print("\nTesting file upload...")
    upload_response = client.post(
        "https://example.com/upload",
        files={'file': ('test.txt', open('test.txt', 'rb'))},
        data={'description': 'Test file'}
    )
    print(f"Upload Status: {upload_response['status']}")

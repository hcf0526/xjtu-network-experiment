# server 127.0.0.1 12345 --virtual-path ./var/www/experiment/html
# server 10.172.73.218 12345 --virtual-path ./var/www/experiment/html
import os
import random
import re
import ssl
import gzip
import json
import time
import socket
import string
import sqlite3

from log import truncate, Log
from lang import Lang
import threading
from concurrent.futures import ThreadPoolExecutor
from myhttp import RED, RESET, MyHttp, MyHttpRequest, MyHttpResponse

LANG = Lang()

class Server:
  def __init__(self, host, port, https=False, virtual_path='./var/www/experiment/html'):
    self.flag = False
    self.host = host
    self.port = port
    self.https = https
    self.public_ip = self.get_public_ip()
    # 缓存
    self.cache = {}
    self.cache_expire_seconds = 60
    self.cache_update_seconds = 10
    # Cookie
    self.sessions = {}
    # 套接字
    self.server_socket = None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile='pem/cert.pem', keyfile='pem/key.pem')
    context.check_hostname = False  # 不检查主机名
    context.verify_mode = ssl.CERT_NONE  # 不进行证书验证
    self.context = context
    self.timeout_seconds = 5
    # 路径
    self.virtual_path = virtual_path
    self.move_path = {'/image': '/images'}
    self.db_path = 'db/user.db'
    self.log = Log(f'logs/server_{host}_{port}.log')
    # 线程池
    self.max_connections = 5
    self.thread_listening = threading.Thread(target=self.listening)
    self.thread_update_cache = threading.Thread(target=self.update_cache)
    self.thread_client_sockets = ThreadPoolExecutor(max_workers=self.max_connections)
    self.debug = True

  def __del__(self):
    self.stop()

  def start(self):
    self.flag = True
    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_socket.bind((self.host, self.port))
    raw_socket.listen(self.max_connections)
    raw_socket.setblocking(False)
    if not self.https:
      self.server_socket = raw_socket
    else:
      self.server_socket = self.context.wrap_socket(raw_socket, server_side=True)

    self.thread_listening.start()
    self.thread_update_cache.start()
    self.debug_info(LANG.SERVER["start"].format(host=self.host, port=self.port))
    self.log.info(LANG.SERVER["start"].format(host=self.host, port=self.port))

  def stop(self):
    self.debug_info(LANG.SERVER["stop"])
    self.log.info(LANG.SERVER["stop"])

    self.flag = False
    self.thread_client_sockets.shutdown(wait=True)

    self.debug_info(LANG.SERVER["stopped"])
    self.log.info(LANG.SERVER["stopped"])

  def listening(self):
    while self.flag:
      try:
        client_socket, client_address = self.server_socket.accept()
      except BlockingIOError:
        continue
      except ssl.SSLError as e:
        if 'HTTP_REQUEST' in str(e):
          self.debug_info(LANG.SERVER["http_error"])
          self.log.info(LANG.SERVER["http_error"])
        if 'ALERT_CERTIFICATE_UNKNOWN' in str(e):
          self.debug_info(LANG.SERVER["certificate_error"])
          self.log.info(LANG.SERVER["certificate_error"])
        continue

      client_socket.settimeout(30)
      client_socket.setblocking(False)
      self.thread_client_sockets.submit(self.execute, client_socket)
      self.debug_info(LANG.SERVER["connect"].format(addr=client_address))
      self.log.info(LANG.SERVER["connect"].format(addr=client_address))

  def execute(self, client_socket):
    result = True
    while result and self.flag:
      result = self.handle_request(client_socket)

    self.debug_info(LANG.SERVER["disconnect"].format(addr=client_socket.getpeername()))
    self.log.info(LANG.SERVER["disconnect"].format(addr=client_socket.getpeername()))
    client_socket.close()

  def update_cache(self):
    while self.flag:
      time.sleep(self.cache_update_seconds)
      for key in list(self.cache.keys()):
        if time.time() - self.cache[key][2] > self.cache_expire_seconds:
          del self.cache[key]
          self.debug_info(f"{RED}Cache expired for {key}{RESET}")
          self.log.info(f"Cache expired for {key}")

  def handle_request(self, client_socket):
    request = MyHttpRequest()
    request_data = self.recv_no_blocking(client_socket)
    if request_data is None:
      response = MyHttpResponse(MyHttp.REQUEST_TIMEOUT)
      client_socket.send(response.generate())
      self.debug_info(LANG.SERVER["timeout"].format(addr=client_socket.getpeername()))
      self.log.info(LANG.SERVER["timeout"].format(addr=client_socket.getpeername()))
      return False
    self.log.info(LANG.SERVER["request"].format(addr=client_socket.getpeername()) + '\n' +
             truncate(request_data).decode('utf-8', errors='backslashreplace'))
    result = request.parse(request_data)
    if result != MyHttp.OK:
      response = MyHttpResponse(result)
      client_socket.send(response.generate())
      return True
    while not request.completeness:
      request_data = self.recv_no_blocking(client_socket)
      self.debug_info(f"Receive {len(request_data)} bytes, total {len(request.body)} bytes")
      self.log.info(LANG.SERVER["request"].format(addr=client_socket.getpeername()) + '\n' +
               truncate(request_data).decode('utf-8', errors='backslashreplace'))
      request.extend(request_data)
    self.debug_info(request)
    # 检查请求字段
    result = self.check_fields(request)
    if result != MyHttp.OK:
      response = MyHttpResponse(result)
      self.debug_info(response)
      client_socket.send(response.generate())
      return True
    # 虚拟路径映射
    result = self.mapping_virtual_path(request)
    if result != MyHttp.OK:
      if request == MyHttp.MOVE_PERMANENTLY or result == MyHttp.TEMPORARY_REDIRECT :
        response = MyHttpResponse(result)
        slash = request.path.find('/', 1)
        folder = request.path[:slash]
        filename = request.path[slash:]
        path = self.move_path[folder] + filename
        response.fields['Location'] = path
        client_socket.send(response.generate())
        self.debug_info(f"Redirect to {path}")
        self.log.info(f"Redirect to {path}")
        return True
      response = MyHttpResponse(result)
      client_socket.send(response.generate())
      return True

    match request.method:
      case "GET":
        response = self.handle_get_request(request)
      case "HEAD":
        response, _ = self.handle_head_request(request)
      case "POST":
        response = self.handle_post_request(client_socket, request)
      case _:
        response = MyHttpResponse(MyHttp.METHOD_NOT_ALLOWED)

    self.debug_info(response)
    if response.fields.get('Transfer-Encoding') and response.fields['Transfer-Encoding'] == 'chunked':
      client_socket.send(response.generate(head=True))
      self.send_chunked_body(client_socket, response.body)
    else:
      client_socket.send(response.generate())

    if request.connection and request.connection.lower() == 'close':
      return False

    return True

  def handle_get_request(self, request: MyHttpRequest):
    try:
      response, content = self.handle_head_request(request)
      if request.path.startswith('/check_login'):
        return response

      response.body = content
      return response
    except Exception as e:
      print(f"get:{e}")

  def handle_head_request(self, request: MyHttpRequest):
    if request.path.startswith('/check_login'):
      return self.post_check_login(request), None
    if not os.path.isfile(request.actual_path):
      return MyHttpResponse(MyHttp.NOT_FOUND), None

    response = MyHttpResponse(MyHttp.OK)
    # 内容类型
    suffix = request.actual_path[request.actual_path.rfind('.'):]
    content_type = LANG.TYPE['type'][suffix]
    response.fields['Content-Type'] = content_type
    # 缓存
    cache_key = request.actual_path
    if cache_key in self.cache:
      if request.accept_encoding and 'gzip' in request.accept_encoding and self.cache[cache_key][3] == 'gzip':
        response.fields['Content-Encoding'] = 'gzip'
        content, _, _, _ = self.cache[cache_key]
      elif (not request.accept_encoding) or (request.accept_encoding and 'gzip' not in request.accept_encoding and self.cache[cache_key][3] is None):
        content, _, _, _ = self.cache[cache_key]
      else:
        with open(request.actual_path, 'rb') as f:
          content = f.read()
          # gzip 压缩
          if request.accept_encoding and 'gzip' in request.accept_encoding:
            content = gzip.compress(content)
            response.fields['Content-Encoding'] = 'gzip'
          if response.fields.get('Content-Encoding') and 'gzip' in response.fields['Content-Encoding']:
            self.cache[cache_key] = (content, response.fields['Content-Type'], time.time(), 'gzip')
          else:
            self.cache[cache_key] = (content, response.fields['Content-Type'], time.time(), None)
      self.debug_info(f"{RED}Cache hit for {cache_key}{RESET}")
      self.log.info(f"Cache hit for {cache_key}")
    else:
      with open(request.actual_path, 'rb') as f:
        content = f.read()
        # gzip 压缩
        if request.accept_encoding and 'gzip' in request.accept_encoding:
          content = gzip.compress(content)
          response.fields['Content-Encoding'] = 'gzip'
      if response.fields.get('Content-Encoding') and 'gzip' in response.fields['Content-Encoding']:
        self.cache[cache_key] = (content, response.fields['Content-Type'], time.time(), 'gzip')
      else:
        self.cache[cache_key] = (content, response.fields['Content-Type'], time.time(), None)

    response.fields['Cache-Control'] = f'max-age={self.cache_expire_seconds}'

    # 内容长度
    response.fields['Content-Length'] = len(content)
    # 分段传输
    if len(content) >= 256 * 1024:
      response.fields['Transfer-Encoding'] = 'chunked'

    return response, content

  def handle_post_request(self, client_socket, request: MyHttpRequest):
    if request.path.count('/') > 2:
      return MyHttpResponse(MyHttp.FORBIDDEN)
    if request.path.startswith('/upload'):
      return self.post_upload(client_socket, request)
    elif request.path.startswith('/login'):
      return self.post_login(request)
    elif request.path.startswith('/logout'):
      return self.post_logout(request)

  def post_upload(self, client_socket, request: MyHttpRequest):
    cookie = request.cookie
    username = client_socket.getpeername()[0]
    if cookie:
      session_id_match = re.search(r'session_id=([^;]+)', cookie)
      session_id = session_id_match.group(1)
      if session_id in self.sessions:
        username = self.sessions[session_id]

    if not os.path.exists(request.actual_path + '/' + username):
      os.makedirs(request.actual_path + '/' + username)
    # gzip 解压缩
    if request.content_encoding and request.content_encoding.contains('gzip'):
      request.body = gzip.decompress(request.body)
    # 文件类型解析
    content_type = self.parse_content_type(request)
    if content_type is None:
      return MyHttpResponse(MyHttp.BAD_REQUEST)
    elif content_type == 'form':
      self.parse_form_data(request, f'{request.actual_path}/{username}')
    elif content_type == 'form-data':
      self.parse_multipart_form_data(request, f'{request.actual_path}/{username}')
    elif request.x_filename:
      file_path = os.path.join(request.actual_path, username, request.x_filename)
      self.save_file(file_path, request.body)
    else:
      file_path = os.path.join(request.actual_path, username, f'{username}.{content_type}')
      self.save_file(file_path, request.body)
    return MyHttpResponse(MyHttp.OK)

  def post_login(self, request: MyHttpRequest):
    if request.cookie:
      session_id_match = re.search(r'session_id=([^;]+)', request.cookie)
      session_id = session_id_match.group(1)
      if session_id in self.sessions:
        return MyHttpResponse(MyHttp.OK)

    content_type = self.parse_content_type(request)
    if content_type is None:
      return MyHttpResponse(MyHttp.BAD_REQUEST)
    elif content_type == 'form':
      return self.parse_login_form_data(request)
    else:
      return MyHttpResponse(MyHttp.BAD_REQUEST)

  def post_logout(self, request: MyHttpRequest):
    if not request.cookie:
      return MyHttpResponse(MyHttp.UNAUTHORIZED)

    cookie_header = request.cookie
    session_id_match = re.search(r'session_id=([^;]+)', cookie_header)
    session_id = session_id_match.group(1)
    if session_id and session_id in self.sessions:
      del self.sessions[session_id]

    response = MyHttpResponse(MyHttp.OK)
    option_http = 'HttpOnly' if self.https else 'HttpsOnly'
    response.fields['Set-Cookie'] = f'session_id=; Max-Age=0; {option_http}'
    return response

  def post_check_login(self, request: MyHttpRequest):
    response = MyHttpResponse(MyHttp.OK)
    response.fields['Content-Type'] = 'application/json; charset=utf-8'
    if not request.cookie:
      response.body = json.dumps({"logged_in": False}).encode('utf-8')
      response.fields['Content-Length'] = len(response.body)
      return response
    try:
      cookie_header = request.cookie
      session_id = None
      if cookie_header:
        match = re.search(r'session_id=([^;]+)', cookie_header)
        session_id = match.group(1) if match else None

      username = self.sessions.get(session_id)
      http_option = 'HttpOnly' if self.https else 'HttpsOnly'
      response.fields['Set-Cookie'] = f'session_id={session_id}; {http_option}; Path=/'

      if username:
        response.body = json.dumps({"logged_in": True, "username": username}).encode('utf-8')
      else:
        response.body = json.dumps({"logged_in": False}).encode('utf-8')

      response.fields['Content-Length'] = len(response.body)
      return response
    except Exception as e:
      print(f"check{e}")

  def recv_no_blocking(self, client_socket):
    request_data = None
    start_time = time.time()
    while self.flag:
      if time.time() - start_time > self.timeout_seconds:
        return None
      try:
        request_data = client_socket.recv(32 * 1024)
      except BlockingIOError:
        continue
      except socket.timeout:
        response = MyHttpResponse(MyHttp.REQUEST_TIMEOUT)
        client_socket.send(response.generate())
        break
      break

    return request_data

  def get_between(self, text, start, end):
    i = text.find(start)
    if i == -1:
      return ''
    i += len(start)
    j = text.find(end, i)
    if j == -1:
      return text[i:]
    return text[i:j]

  def check_fields(self, request: MyHttpRequest):
    if request.host is None:
      # 缺少 Host 字段
      return MyHttp.BAD_REQUEST
    # if request.host not in (f'{self.host}', f'{self.host}:{self.port}'):
    #   # Host 字段不匹配
    #   return MyHttp.FORBIDDEN

    return MyHttp.OK

  def mapping_virtual_path(self, request):
    # 虚拟路径映射
    path = MyHttp.url_decode(request.path)
    if request.path in ('/login', '/logout', '/check_login'):
      return MyHttp.OK
    if request.path == '/':
      request.actual_path = self.virtual_path + '/index.html'
      return MyHttp.OK
    if request.path == '/favicon.ico':
      request.actual_path = self.virtual_path + '/ico/white128.ico'
      return MyHttp.OK
    norm_path = os.path.normpath(request.path)
    target_path = os.path.normpath("/image")
    if norm_path.startswith(target_path + os.sep):
      return MyHttp.TEMPORARY_REDIRECT
    actual_path = self.virtual_path + path
    if os.path.exists(actual_path):
      request.actual_path = actual_path
      return MyHttp.OK
    return MyHttp.FORBIDDEN

  def save_file(self, file_path, data):
    with open(file_path, 'wb') as file:
      file.write(data)

  def parse_content_type(self, request: MyHttpRequest):
    if request.content_type is None:
      return 'bin'
    if request.content_type.count('/') != 1:
      return None
    (prefix, suffix) = request.content_type.split('/')
    if 'multipart' in prefix and 'form-data' in suffix:
      return 'form-data'
    if prefix not in LANG.TYPE:
      return None
    if suffix not in LANG.TYPE[prefix]:
      return None
    return LANG.TYPE[prefix][suffix]

  def parse_form_data_headers(self, headers_raw):
    headers = {}
    for line in headers_raw.split("\r\n"):
      if ": " in line:
        key, value = line.split(": ", 1)
        headers[key.strip()] = value.strip()
    return headers

  def parse_form_data(self, request: MyHttpRequest, path):
    body_str = request.body.decode('utf-8')
    form_data = {}
    for pair in body_str.split('&'):
      if '=' in pair:
        key, value = pair.split('=', 1)
        form_data[key] = value

    json_path = os.path.join(path, 'form_data.json')
    with open(json_path, 'w', encoding='utf-8') as f:
      json.dump(form_data, f, ensure_ascii=False, indent=2)  # type: ignore

  def parse_multipart_form_data(self, request: MyHttpRequest, path):
    boundary = request.content_type.split('boundary=')[1]
    boundary_bytes = ('--' + boundary).encode()
    parts = request.body.split(boundary_bytes)

    form_data = {}

    for part in parts:
      if not part or part == b'--\r\n':
        continue
      part = part.strip(b'\r\n')

      header_end = part.find(b'\r\n\r\n')
      if header_end == -1:
        continue
      header_block = part[:header_end].decode()
      body = part[header_end + 4:]

      headers = self.parse_form_data_headers(header_block)

      disposition = headers.get('Content-Disposition', '')
      if 'filename=' in disposition:
        name = self.get_between(disposition, 'name="', '"')
        filename = self.get_between(disposition, 'filename="', '"')
        file_path = os.path.join(path, filename)
        self.save_file(file_path, body)
      else:
        name = self.get_between(disposition, 'name="', '"')
        form_data[name] = body.decode()

    if form_data:
      json_path = os.path.join(path, 'form_data.json')
      with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(form_data, f, ensure_ascii=False, indent=2)  # type: ignore

  def parse_login_form_data(self, request: MyHttpRequest):
    query = request.body.decode('utf-8')
    username_match = re.search(r'username=([^&]+)', query)
    password_match = re.search(r'password=([^&]+)', query)
    username = username_match.group(1) if username_match else None
    password = password_match.group(1) if password_match else None
    if not username or not password:
      return MyHttpResponse(MyHttp.UNAUTHORIZED)

    with sqlite3.connect(self.db_path) as conn:
      cursor = conn.cursor()
      cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
      user = cursor.fetchone()

      if not user:
        return MyHttpResponse(MyHttp.UNAUTHORIZED)

      stored_password = user[2]
      if password == stored_password:
        session_id = self.generate_session_id()
        self.sessions[session_id] = username
        response = MyHttpResponse(MyHttp.OK)
        option_https = 'HttpOnly' if self.https else 'HttpsOnly'
        response.fields['Set-Cookie'] = f'session_id={session_id}; {option_https}; Path=/'
        return response
      return MyHttpResponse(MyHttp.UNAUTHORIZED)

  def generate_session_id(self, length=32):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

  def send_chunked_body(self, client_socket, content):
    chunk_size = 64 * 1024
    try:
      for i in range(0, len(content), chunk_size):
        client_socket.setblocking(True)
        chunk = content[i:i + chunk_size]
        chunk_length = len(chunk)
        client_socket.sendall(f"{chunk_length:X}\r\n".encode())
        client_socket.sendall(chunk)
        client_socket.sendall(b"\r\n")

      client_socket.sendall(b"0\r\n\r\n")
    except Exception as e:
      print(e)

  def get_public_ip(self):
    try:
      host = 'ip-api.com'
      port = 80

      with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        request = "GET /json HTTP/1.1\r\n"
        request += f"Host: {host}\r\n"
        request += "Connection: close\r\n\r\n"
        s.sendall(request.encode())
        response = b""
        while True:
          data = s.recv(1024)
          if not data:
            break
          response += data
        response_str = response.decode()
        header, body = response_str.split("\r\n\r\n", 1)
        data = json.loads(body)
        if data.get('status') == 'success':
          return data['query']
    except Exception as e:
      print(f"Error: {e}")
    return None

  def debug_info(self, info):
    if isinstance(info, MyHttpRequest):
      if not info.success:
        return
    if self.debug:
      print(info)


servers = {}

def parse_and_run_command(command_line):
  if command_line == 'loopback':
    command_line = 'server 127.0.0.1 12345 --virtual-path ./var/www/experiment/html'
  elif command_line == 'localhost':
    command_line = 'server 0.0.0.0 12345 --virtual-path ./var/www/experiment/html'
  elif command_line == 'loopback https':
    command_line = 'server 127.0.0.1 443 -https --virtual-path ./var/www/experiment/html'
  elif command_line == 'local https':
    command_line = 'server 0.0.0.0 443 -https --virtual-path ./var/www/experiment/html'
  tokens = command_line.strip().split()
  if not tokens:
    return

  if tokens[0] != "server":
    print("Unknown command. Commands should start with 'server'.")
    return

  if len(tokens) >= 3 and tokens[1] != "--stop" and tokens[1] != "-list" and tokens[1] != "-exit":
    host = tokens[1]
    try:
      port = int(tokens[2])
    except ValueError:
      print("Port must be an integer.")
      return

    https = False
    virtual_path = None
    i = 3
    while i < len(tokens):
      if tokens[i] == "-https":
        https = True
        i += 1
      elif tokens[i] == "--virtual-path":
        if i + 1 < len(tokens):
          virtual_path = tokens[i + 1]
          i += 2
        else:
          print("Missing value for --virtual-path.")
          return
      else:
        print(f"Unknown argument: {tokens[i]}")
        return

    if port in servers:
      print(f"Port {port} is already running.")
      return

    server = Server(host, port, https, virtual_path)
    thread = threading.Thread(target=server.start, daemon=True)
    servers[port] = (server, thread)
    thread.start()
    print(f"Server started on port {port}")

  elif len(tokens) == 3 and tokens[1] == "--stop":
    try:
      port = int(tokens[2])
    except ValueError:
      print("Usage: server --stop port")
      return

    if port not in servers:
      print(f"No server running on port {port}")
      return

    server, thread = servers.pop(port)
    server.stop()
    print(f"Server on port {port} stopped.")

  # 列出所有已启动 server
  elif len(tokens) == 2 and tokens[1] == "-list":
    if not servers:
      print("No running servers.")
    else:
      print("Running servers on ports:")
      for port in servers:
        print(f"  - {port}")

  # 停止所有 server 并退出
  elif len(tokens) == 2 and tokens[1] == "-exit":
    print("Stopping all servers and exiting.")
    for port in list(servers.keys()):
      server, thread = servers.pop(port)
      server.stop()
      print(f"Server on port {port} stopped.")
    exit(0)

  else:
    print("Invalid command or arguments.")

if __name__ == "__main__":
  print("Server CLI. Type 'server -exit' to stop all servers and exit.")
  while True:
    try:
      command_line = input("> ")
      parse_and_run_command(command_line)
    except KeyboardInterrupt:
      print("\nUse 'server -exit' to stop all servers and exit.")

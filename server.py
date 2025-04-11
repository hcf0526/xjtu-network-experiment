import os
import json
import gzip
import socket
import ssl
import time

from sympy import expand

from log import truncate, Log
from lang import Lang
import threading
from concurrent.futures import ThreadPoolExecutor
from myhttp import RED, RESET, MyHttp, MyHttpRequest, MyHttpResponse

LANG = Lang()
log = Log('logs/server.log')

class Server:
  def __init__(self, host, port):
    self.flag = False
    self.host = host
    self.port = port
    self.cache = {}
    self.server_socket = None
    self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    self.context.load_cert_chain(certfile='pem/cert.pem', keyfile='pem/key.pem')
    self.virtual_path = './var/www/experiment/html'
    self.max_connections = 5
    self.thread_listening = threading.Thread(target=self.listening)
    self.thread_client_sockets = ThreadPoolExecutor(max_workers=self.max_connections)
    self.debug = True

  def start(self, https=False):
    self.flag = True
    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # raw_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    raw_socket.bind((self.host, self.port))
    raw_socket.listen(self.max_connections)
    raw_socket.setblocking(False)
    if not https:
      self.server_socket = raw_socket
    else:
      self.server_socket = self.context.wrap_socket(raw_socket, server_side=True)

    self.thread_listening.start()
    self.debug_info(LANG.SERVER["start"].format(host=self.host, port=self.port))
    log.info(LANG.SERVER["start"].format(host=self.host, port=self.port))

  def stop(self):
    self.debug_info(LANG.SERVER["stop"])
    log.info(LANG.SERVER["stop"])

    self.flag = False
    self.thread_client_sockets.shutdown(wait=True)

    self.debug_info(LANG.SERVER["stopped"])
    log.info(LANG.SERVER["stopped"])

  def listening(self):
    while self.flag:
      try:
        client_socket, client_address = self.server_socket.accept()
      except BlockingIOError:
        continue
      except ssl.SSLError as e:
        if 'HTTP_REQUEST' in str(e):
          self.debug_info(LANG.SERVER["http_error"])
          log.info(LANG.SERVER["http_error"])
        if 'ALERT_CERTIFICATE_UNKNOWN' in str(e):
          self.debug_info(LANG.SERVER["certificate_error"])
          log.info(LANG.SERVER["certificate_error"])
        continue

      client_socket.settimeout(30)
      client_socket.setblocking(False)
      self.thread_client_sockets.submit(self.execute, client_socket)
      self.debug_info(LANG.SERVER["connect"].format(addr=client_address))
      log.info(LANG.SERVER["connect"].format(addr=client_address))

  def execute(self, client_socket):
    result = True
    while result and self.flag:
      result = self.handle_request(client_socket)

    client_socket.close()

  def handle_request(self, client_socket):
    request = MyHttpRequest()
    request_data = self.recv_no_blocking(client_socket)
    if request_data is None:
      return False
    log.info(LANG.SERVER["request"].format(addr=client_socket.getpeername()) + '\n' +
             truncate(request_data).decode('utf-8', errors='backslashreplace'))
    result = request.parse(request_data)
    if result != MyHttp.OK:
      response = MyHttpResponse(result)
      client_socket.send(response.generate())
      return True
    while not request.completeness:
      request_data = self.recv_no_blocking(client_socket)
      log.info(LANG.SERVER["request"].format(addr=client_socket.getpeername()) + '\n' +
               truncate(request_data).decode('utf-8', errors='backslashreplace'))
      request.extend(request_data)
    self.debug_info(request)
    # 检查请求字段
    result = self.check_fields(request)
    if result != MyHttp.OK:
      response = MyHttpResponse(result)
      client_socket.send(response.generate())
      return True
    # 虚拟路径映射
    result = self.mapping_virtual_path(request)
    if result != MyHttp.OK:
      response = MyHttpResponse(result)
      client_socket.send(response.generate())
      return True
    # 解析 Cookie
    self.parse_cookie(request)

    match request.method:
      case "GET":
        response = self.handle_get_request(request)
      case "HEAD":
        response = self.handle_head_request(request)
      case "POST":
        response = self.handle_post_request(client_socket, request)
      case _:
        response = MyHttpResponse(MyHttp.METHOD_NOT_ALLOWED)

    self.debug_info(response)
    client_socket.send(response.generate())

    if request.connection and request.connection.lower() == 'close':
      return False

    return True

  def handle_get_request(self, request: MyHttpRequest):
    try:
      response = self.handle_head_request(request)
      cache_key = request.actual_path
      if cache_key in self.cache:
        content, _, _ = self.cache[cache_key]
        self.debug_info(f"{RED}Cache hit for {cache_key}{RESET}")
      else:
        with open(request.actual_path, 'rb') as f:
          content = f.read()
        self.cache[cache_key] = (content, response.fields['Content-Type'], time.time())

      if 'gzip' in request.accept_encoding:
        content = gzip.compress(content)
        response.fields['Content-Encoding'] = 'gzip'

      response.fields['Content-Length'] = len(content)
      response.fields['Cache-Control'] = 'max-age=60'
      response.body = content


      visit_count = int(request.cookies.get('visit', '0')) + 1
      response.fields['Set-Cookie'] = f'visit={visit_count}; Path=/'

      return response
    except Exception as e:
      print(e)

  def handle_head_request(self, request: MyHttpRequest):
    if not os.path.isfile(request.actual_path):
      return MyHttpResponse(MyHttp.NOT_FOUND)
    response = MyHttpResponse(MyHttp.OK)
    suffix = request.actual_path[request.actual_path.rfind('.'):]
    content_type = LANG.TYPE['type'][suffix]
    response.fields['Content-Length'] = os.path.getsize(request.actual_path)
    response.fields['Content-Type'] = content_type
    return response

  def handle_post_request(self, client_socket, request: MyHttpRequest):
    # 路径合法性检查
    if not request.path.startswith('/upload'):
      return MyHttpResponse(MyHttp.FORBIDDEN)
    if request.path.count('/') > 2:
      return MyHttpResponse(MyHttp.FORBIDDEN)
    # 路径创建
    address = client_socket.getpeername()[0]
    if not os.path.exists(request.actual_path + '/' + address):
      os.makedirs(request.actual_path +  '/' + address)
    # gzip 解压缩
    if request.content_encoding and request.content_encoding.contains('gzip'):
      request.body = gzip.decompress(request.body)
    # 文件类型解析
    content_type = self.parse_content_type(request)
    if content_type is None:
      return MyHttpResponse(MyHttp.BAD_REQUEST)
    elif content_type == 'x-www-form-urlencoded':
      self.parse_form_data(request, f'{request.actual_path}/{address}')
    elif content_type == 'form-data':
      self.parse_multipart_form_data(request, f'{request.actual_path}/{address}')
    elif request.x_filename:
      file_path = os.path.join(request.actual_path, address, request.x_filename)
      self.save_file(file_path, request.body)
    else:
      file_path = os.path.join(request.actual_path, address, f'{address}.{content_type}')
      self.save_file(file_path, request.body)
    return MyHttpResponse(MyHttp.OK)

  def recv_no_blocking(self, client_socket):
    request_data = None
    while self.flag:
      try:
        request_data = client_socket.recv(4096)
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
    if request.host not in (f'{self.host}', f'{self.host}:{self.port}'):
      # Host 字段不匹配
      return MyHttp.FORBIDDEN

    return MyHttp.OK

  def mapping_virtual_path(self, request):
    # 虚拟路径映射
    path = MyHttp.url_decode(request.path)
    if request.path == '/':
      request.actual_path = self.virtual_path + '/index.html'
      return MyHttp.OK
    if request.path == '/favicon.ico':
      request.actual_path = self.virtual_path + '/ico/white128.ico'
      return MyHttp.OK
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
    if 'application' in prefix and 'x-www-form-urlencoded' in suffix:
      return 'x-www-form-urlencoded'
    if prefix not in LANG.TYPE:
      return None
    if suffix not in LANG.TYPE[prefix]:
      return None
    return LANG.TYPE[prefix][suffix]

  def parse_cookie(self, request: MyHttpRequest):
    if not request.cookies:
      return
    cookie_header = request.cookies
    request.cookies = {}
    for pair in cookie_header.split(';'):
      if '=' in pair:
        key, value = pair.strip().split('=', 1)
        request.cookies[key] = value

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

  def decode_chunked(self, client_socket, request: MyHttpRequest):
    pass

  def debug_info(self, info):
    if isinstance(info, MyHttpRequest):
      if not info.success:
        return
    if self.debug:
      print(info)


def main():
  server = Server('127.0.0.1', 443)
  server.start(https=True)
  while True:
    pass

if __name__ == '__main__':
  main()
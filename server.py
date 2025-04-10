import os
import gzip
import socket

from log import truncate, Log
from lang import Lang
import threading
from concurrent.futures import ThreadPoolExecutor
from myhttp import MyHttp, MyHttpRequest, MyHttpResponse

LANG = Lang()
log = Log('logs/server.log')

class Server:
  def __init__(self, host, port):
    self.flag = False
    self.host = host
    self.port = port
    self.server_socket = None
    self.virtual_path = './var/www/experiment/html'
    self.max_connections = 5
    self.thread_listening = threading.Thread(target=self.listening)
    self.thread_client_sockets = ThreadPoolExecutor(max_workers=self.max_connections)
    self.debug = True

  def start(self):
    self.flag = True
    self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.server_socket.bind((self.host, self.port))
    self.server_socket.listen(self.max_connections)
    self.server_socket.setblocking(False)  # 非阻塞模式
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
    request_data = self.recv_no_blocking(client_socket)
    if request_data is None:
      return False

    message = LANG.SERVER["request"].format(addr=client_socket.getpeername())
    message += '\n'
    try:
      message += truncate(request_data).decode('utf-8', errors='backslashreplace')
    except Exception as e:
      print(e)
    log.info(message)

    request = MyHttpRequest()
    result = request.parse(request_data)
    self.debug_info(request)

    if result != MyHttp.OK:
      response = MyHttpResponse(result)
      client_socket.send(response.generate())
      return True
    # 检查请求字段
    result = self.fields_check(request)
    if result != MyHttp.OK:
      response = MyHttpResponse(result)
      client_socket.send(response.generate())
      return True
    # 虚拟路径映射
    result = self.virtual_path_mapping(request)
    if result != MyHttp.OK:
      response = MyHttpResponse(result)
      client_socket.send(response.generate())
      return True

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
    response = self.handle_head_request(request)
    with open(request.actual_path, 'rb') as file:
      file = file.read()
      # gzip 压缩
      # if 'gzip' in request.accept_encoding:
      #   file = gzip.compress(file)
      #   response.fields['Content-Length'] = len(file)
      #   response.fields['Content-Encoding'] = 'gzip'
      response.body = file
    return response

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
    if not os.path.exists(request.actual_path + address):
      os.makedirs(request.actual_path + address)
    # 文件类型解析
    suffix = self.content_type_parse(request)
    if suffix is None:
      return MyHttpResponse(MyHttp.BAD_REQUEST)
    # gzip 解压缩
    if request.content_encoding.contains('gzip'):
      request.body = gzip.decompress(request.body)
    with open(request.actual_path + address + f'/{address}{suffix}', 'wb') as file:
      file.write(request.body)
    return MyHttpResponse(MyHttp.OK)

  def recv_no_blocking(self, client_socket):
    request_data = None
    while self.flag:
      try:
        request_data = client_socket.recv(1024 * 1024)
      except BlockingIOError:
        continue
      except socket.timeout:
        response = MyHttpResponse(MyHttp.REQUEST_TIMEOUT)
        client_socket.send(response.generate())
        break
      break

    return request_data

  def fields_check(self, request: MyHttpRequest):
    if request.host is None:
      # 缺少 Host 字段
      return MyHttp.BAD_REQUEST
    if request.host not in (f'{self.host}', f'{self.host}:{self.port}'):
      # Host 字段不匹配
      return MyHttp.FORBIDDEN

    return MyHttp.OK

  def virtual_path_mapping(self, request):
    # 虚拟路径映射
    path = MyHttp.url_decode(request.path)
    if request.path == '/':
      request.actual_path = self.virtual_path + '/index.html'
      return MyHttp.OK
    if request.path == '/favicon.ico':
      request.actual_path = self.virtual_path + '/ico/white128.ico'
      return MyHttp.OK
    actual_path = self.virtual_path + path
    if os.path.exists(actual_path) and os.path.isfile(actual_path):
      request.actual_path = actual_path
      return MyHttp.OK
    return MyHttp.FORBIDDEN

  def content_type_parse(self, request: MyHttpRequest):
    if request.content_type is None:
      return '.bin'
    if request.content_type.count('/') != 1:
      return None
    (prefix, suffix) = request.content_type.split('/')
    if prefix not in LANG.TYPE:
      return None
    if suffix not in LANG.TYPE[prefix]:
      return None
    return LANG.TYPE[prefix][suffix]

  def debug_info(self, info):
    if isinstance(info, MyHttpRequest):
      if not info.success:
        return
    if self.debug:
      print(info)


def main():
  server = Server('10.172.72.235', 12345)
  server.start()
  while True:
    pass

if __name__ == '__main__':
  main()
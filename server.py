import os
import socket
from idlelib.rpc import request_queue

from lang import Lang
from log import Log
from concurrent.futures import ThreadPoolExecutor
from myhttp import MyHttp, MyHttpRequest, MyHttpResponse

LANG = Lang()
log = Log('var/www/logs/server.log')

class Server:
  def __init__(self, host, port):
    self.host = host
    self.port = port
    self.server_socket = None
    self.virtual_path = {
      '/': './var/www/experiment/html/index.html',
      '/images/': './var/www/experiment/html/images/',
      '/upload/': './var/www/experiment/upload/',
    }
    self.max_connections = 5
    self.thread_pool = ThreadPoolExecutor(max_workers=self.max_connections)

  def start(self):
    self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.server_socket.bind((self.host, self.port))
    self.server_socket.listen(self.max_connections)
    log.info(LANG.SERVER["start"].format(host=self.host, port=self.port))

    try:
      while True:
        client_socket, client_address = self.server_socket.accept()
        log.info(LANG.SERVER["connect"].format(addr=client_address))
        self.thread_pool.submit(self.thread_execute, client_socket)
    except KeyboardInterrupt:
      log.info(LANG.SERVER["stop"])
    finally:
      self.server_socket.close()

  def thread_execute(self, client_socket):
    client_socket.settimeout(5)
    result = True
    while result:
      result = self.handle_request(client_socket)
    client_socket.close()

  def handle_request(self, client_socket):
    try:
      request_data = client_socket.recv(1024)
    except socket.timeout:
      response = MyHttpResponse(MyHttp.REQUEST_TIMEOUT)
      client_socket.send(response.generate())
      return False
    if not request_data:
      return True
    log.info(LANG.SERVER["receive"].format(addr=client_socket.getpeername())
             + '\r\n' + request_data.decode('utf-8', errors='backslashreplace'))

    request = MyHttpRequest()
    result = request.parse(request_data)
    print(request)
    if not result:
      response = MyHttpResponse(MyHttp.BAD_REQUEST)
      client_socket.send(response.generate())
      return True

    request = self.virtual_path_mapping(request)
    if not request:
      response = MyHttpResponse(MyHttp.FORBIDDEN)
      client_socket.send(response.generate())
      return True

    result = self.fields_check(request)
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

    print(response)
    client_socket.send(response.generate())

    if request.connection and request.connection.lower() == 'Close':
      return False

    return True

  def virtual_path_mapping(self, request):
    # 虚拟路径映射
    path = MyHttp.url_decode(request.path)
    slash = path.find('/', 1)
    if slash == -1:
      slash = len(path) - 1
    path_map = self.virtual_path.get(path[:slash + 1], '')
    if path_map == '':
      return None
    request.actual_path = path_map + path[slash + 1:]
    return request

  def fields_check(self, request: MyHttpRequest):
    if request.host is None:
      # 缺少 Host 字段
      return MyHttp.BAD_REQUEST
    if request.host not in (f'{self.host}', f'{self.host}:{self.port}'):
      # Host 字段不匹配
      return MyHttp.FORBIDDEN

    return MyHttp.OK

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

  def handle_get_request(self, request: MyHttpRequest):
    response = self.handle_head_request(request)
    with open(request.actual_path, 'rb') as file:
      file = file.read()
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
    if not request.path.startswith('/upload/'):
      return MyHttpResponse(MyHttp.FORBIDDEN)
    if request.path.count('/') > 2:
      return MyHttpResponse(MyHttp.FORBIDDEN)
    address = client_socket.getpeername()[0]
    if not os.path.exists(request.actual_path + address):
      os.makedirs(request.actual_path + address)
    suffix = self.content_type_parse(request)
    if suffix is None:
      return MyHttpResponse(MyHttp.BAD_REQUEST)
    with open(request.actual_path + address + f'/{address}{suffix}', 'wb') as file:
      file.write(request.body)
    return MyHttpResponse(MyHttp.OK)

def main():
  server = Server('127.0.0.1', 12345)
  server.start()

if __name__ == '__main__':
  main()
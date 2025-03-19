import os
import socket

from lang import Lang
from log import Log
from myhttp import MyHttp, MyHttpRequest, MyHttpResponse

LANG = Lang()
log = Log('var/www/logs/server.log')

class Server:
  def __init__(self, host, port):
    self.host = host
    self.port = port
    self.virtual_path = {
      '/': './var/www/experiment/html/index.html',
      '/images/': './var/www/experiment/html/images/',
      '/upload/': './var/www/experiment/upload/',
    }
    self.server_socket = None

  def start(self):
    self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.server_socket.bind((self.host, self.port))
    self.server_socket.listen(5)
    log.info(LANG.SERVER["start"].format(host=self.host, port=self.port))

    while True:
      client_socket, client_address = self.server_socket.accept()
      log.info(LANG.SERVER["connect"].format(addr=client_address))
      self.handle_request(client_socket)

  def handle_request(self, client_socket):
    request_data = client_socket.recv(1024)
    log.info(LANG.SERVER["receive"].format(addr=client_socket.getpeername())
             + '\n' + request_data.decode('utf-8', errors='backslashreplace'))

    request = MyHttpRequest()
    result = request.parse(request_data)
    if not result:
      response = MyHttpResponse(MyHttp.BAD_REQUEST)
      client_socket.send(response.generate())
      client_socket.close()
      return False

    request = self.virtual_path_mapping(request)
    if not request:
      response = MyHttpResponse(MyHttp.FORBIDDEN)
      client_socket.send(response.generate())
      client_socket.close()
      return False

    match request.method:
      case "GET":
        response = self.handle_get_request(request)
      case "HEAD":
        response = self.handle_head_request(request)
      case "POST":
        response = self.handle_post_request(client_socket, request)
      case _:
        response = MyHttpResponse(MyHttp.METHOD_NOT_ALLOWED)

    client_socket.send(response.generate())
    client_socket.close()

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

  def handle_get_request(self, request: MyHttpRequest):
    response = self.handle_head_request(request)
    with open(request.actual_path, 'rb') as file:
      file = file.read()
      response.body = file
    return response

  def handle_head_request(self, request: MyHttpRequest):
    if not os.path.isfile(request.actual_path):
      return MyHttpResponse(MyHttp.NOT_FOUND)
    return MyHttpResponse(MyHttp.OK)

  def handle_post_request(self, client_socket, request: MyHttpRequest):
    if not request.path.startswith('/upload/'):
      return MyHttpResponse(MyHttp.FORBIDDEN)
    if request.path.count('/') > 2:
      return MyHttpResponse(MyHttp.FORBIDDEN)
    folder_name = client_socket.getpeername()[0]
    if not os.path.exists(request.actual_path + folder_name):
      os.makedirs(request.actual_path + folder_name)
    with open(request.actual_path + folder_name + '/index.html', 'wb') as file:
      file.write(request.body)
    return MyHttpResponse(MyHttp.OK)

def main():
  server = Server('127.0.0.1', 12345)
  server.start()

if __name__ == '__main__':
  main()
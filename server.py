import os
import socket
import json

from lang import Lang
from logger import Logger
from http_tools import HttpRequest, Http

LANG = Lang()
logger = Logger('var/www/logs/server.log')

class Server:
  def __init__(self, host, port):
    self.host = host
    self.port = port
    self.vir_path = {
      '/': './var/www/experiment/html/index.html',
      '/images/': './var/www/experiment/html/images/'
    }
    self.server_socket = None

  def start(self):
    self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.server_socket.bind((self.host, self.port))
    self.server_socket.listen(5)
    logger.info(LANG.SERVER["start"].format(host=self.host, port=self.port))

    while True:
      client_socket, client_address = self.server_socket.accept()
      logger.info(LANG.SERVER["connect"].format(addr=client_address))
      self.handle_request(client_socket)

  def handle_request(self, client_socket):
    request_data = client_socket.recv(1024).decode('utf-8')
    client_address, _ = client_socket.getpeername()
    log_info = LANG.SERVER["receive"].format(addr=client_address) + "\n" + request_data
    logger.info(log_info)

    request = HttpRequest()
    result = request.parse(request_data)
    if not result:
      response = LANG.HTTP[Http.BAD_REQUEST]
      client_socket.send(response.encode('utf-8'))
      client_socket.close()
      return

    # 路径处理
    path = Http.url_decode(request.path)
    slash = path.find('/', 1)
    if slash == -1:
      slash = len(path) - 1
    path_map = self.vir_path.get(path[:slash + 1], "")
    if path_map == "":
      response = LANG.HTTP[Http.NOT_FOUND]
      client_socket.send(response.encode('utf-8'))
      client_socket.close()
      return
    path = path_map + path[slash+1:]

    match request.method:
      case "GET":
        response = self.handle_get_request(path)
      case "HEAD":
        response = self.handle_head_request(path)
      case _:
        response = LANG.HTTP[Http.METHOD_NOT_ALLOWED]

    client_socket.send(response)
    client_socket.close()

  def handle_get_request(self, path):
    response = self.handle_head_request(path)
    response += b'\r\n'
    with open(path, 'rb') as file:
      file = file.read()
      response += file

    return response

  def handle_head_request(self, path):
    if not os.path.isfile(path):
      return LANG.HTTP[Http.NOT_FOUND]
    response = LANG.HTTP[Http.OK]

    return response.encode('utf-8')

def main():
  server = Server('127.0.0.1', 12345)
  server.start()

if __name__ == '__main__':
  main()
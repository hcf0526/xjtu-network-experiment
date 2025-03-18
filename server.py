import os
import socket
import json
from http.client import responses

from logger import Logger

class Server:
  def __init__(self, host, port):
    self.host = host
    self.port = port
    self.vir_path = {
      '/': './var/www/experiment/html/index.html',
      '/images/': './var/www/experiment/html/images/'
    }
    self.server_socket = None
    self.logger = Logger('var/www/logs/server.log')
    self.LANG_SERVER = None
    self.LANG_HTTP = None
    self.init_lang()

  def init_lang(self):
    with open('var/www/lang/server.json', 'r') as file:
      self.LANG_SERVER = json.load(file)
    with open('var/www/lang/http.json', 'r') as file:
      self.LANG_HTTP = json.load(file)

  def start(self):
    self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.server_socket.bind((self.host, self.port))
    self.server_socket.listen(5)
    self.logger.info(self.LANG_SERVER["start"].format(host=self.host, port=self.port))

    while True:
      client_socket, client_address = self.server_socket.accept()
      self.logger.info(self.LANG_SERVER["connect"].format(address=client_address))
      self.handle_request(client_socket)

  def handle_request(self, client_socket):
    request_data = client_socket.recv(1024).decode()
    client_address, _ = client_socket.getpeername()
    _log_info = self.LANG_SERVER["request"].format(address=client_address)
    _log_info += "\n"
    _log_info += request_data
    self.logger.info(_log_info)

    request_lines = request_data.splitlines()
    if not request_lines:
      return
    request_line = request_lines[0]
    method, path, _ = request_line.split()

    match method:
      case "GET":
        response = self.handle_get_request(path)
      case _:
        response = self.LANG_HTTP["405"]

    client_socket.send(response.encode())
    client_socket.close()

  def handle_get_request(self, path):
    file_path = self.parse_path(path)
    if not (os.path.exists(file_path) and os.path.isfile(file_path)):
      return self.LANG_HTTP["404"]
    response = self.LANG_HTTP["200"]
    response += "\r\n"
    with open(file_path, 'r') as file:
      file = file.read()
      response += file

    return response

  def parse_path(self, path: str):
    if not path.startswith('/'):
      return None
    if path == '/':
      return self.vir_path['/']
    slash = path.find('/', 1)
    path_map = self.vir_path.get(path[:slash+1], None)
    if path_map is None:
      return None
    return path_map + path[slash+1:]

def main():
  server = Server('127.0.0.1', 12345)
  server.start()

if __name__ == '__main__':
  main()
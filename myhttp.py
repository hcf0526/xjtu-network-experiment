import re
from log import truncate
from lang import Lang

LANG = Lang()
RED = '\033[31m'
YELLOW = '\033[33m'
BLUE = '\033[34m'
RESET = '\033[0m'

class MyHttp:
  OK = "200"
  MOVE_PERMANENTLY = "301"
  TEMPORARY_REDIRECT = "307"
  BAD_REQUEST = "400"
  UNAUTHORIZED = "401"
  FORBIDDEN = "403"
  NOT_FOUND = "404"
  METHOD_NOT_ALLOWED = "405"
  REQUEST_TIMEOUT = "408"

  METHODS = ('GET', 'HEAD', 'POST')
  FIELDS = ('Host', 'User-Agent', 'Connection', 'Content-Length', 'Content-Type',
            'Content-Encoding', 'Accept-Encoding', 'Transfer-Encoding', 'X-Filename', 'Cookie')

  @staticmethod
  def url_decode(url):
    i = 0
    decoded_url = []
    byte_sequence = []  # 用于存储一个多字节字符的字节序列

    while i < len(url):
      if url[i] == '%' and i + 2 < len(url):  # 找到 '%XX' 编码
        hex_value = url[i + 1:i + 3]  # 获取 XX 部分
        byte_sequence.append(int(hex_value, 16))  # 将十六进制转换为字节并存储
        i += 3  # 跳过已处理的 '%XX'
      else:
        # 如果有已存储的字节（多字节字符），就将它们一起解码
        if byte_sequence:
          decoded_url.append(bytes(byte_sequence).decode('utf-8'))
          byte_sequence = []  # 清空字节序列以处理下一个字符
        decoded_url.append(url[i])  # 普通字符直接添加
        i += 1

    # 如果最后还有未解码的字节（例如 URL 以编码字符结尾）
    if byte_sequence:
      decoded_url.append(bytes(byte_sequence).decode('utf-8'))

    return ''.join(decoded_url)

    # 将字节数组转换为字节串，并解码为 UTF-8 字符串
    byte_data = bytes(byte_array)
    return byte_data.decode('utf-8')


class MyHttpRequest(MyHttp):
  def __init__(self):

    self.success = False
    self.completeness = False
    self.method = None
    self.path = None
    self.actual_path = None
    self.version = None
    self.fields = None
    self.body = b''
    self.buffer = bytearray(b'')
    # 字段
    self.host = None
    self.user_agent = None
    self.connection = None
    self.content_length = None
    self.content_type = None
    self.content_encoding = None
    self.accept_encoding = None
    self.transfer_encoding = None
    self.x_filename = None
    self.cookie = None

  def __str__(self):
    info = f'{RED}Request: {RESET}\n'
    info += f"Method: {self.method}\n"
    info += f"Path: {self.path}\n"
    info += f"Version: {self.version}\n"
    info += f"Fields: {self.fields}\n"
    info += f"Body: {truncate(self.body, 256)}\n"
    return info

  def __repr__(self):
    return self.__str__()

  def parse(self, request: bytes):
    if not request:
      return MyHttp.BAD_REQUEST
    lines = request.splitlines(keepends=True)

    # 处理请求行
    try:
      header = lines[0].decode('utf-8')
    except UnicodeDecodeError:
      return MyHttp.BAD_REQUEST
    header = header.rstrip('\r\n').split()
    if len(header) != 3:
      return MyHttp.BAD_REQUEST
    method, path, version = header
    if not path.startswith('/'):
      return MyHttp.BAD_REQUEST
    if not version.startswith('HTTP/'):
      return MyHttp.BAD_REQUEST

    if method not in self.METHODS:
      return MyHttp.METHOD_NOT_ALLOWED

    # 处理请求头
    number = 0
    fields = { }
    for (number, line) in enumerate(lines[1:], start=1):
      if line == b'\r\n':
        break
      if number == len(lines) - 1:
        return MyHttp.BAD_REQUEST
      try:
        line = line.decode('utf-8')
      except UnicodeDecodeError:
        return MyHttp.BAD_REQUEST
      if ':' not in line:
        return MyHttp.BAD_REQUEST
      k, v = line.split(':', 1)
      (k, v) = (k.strip(), v.strip())
      fields[k] = v

    # 设置对象属性
    self.method = method
    self.path = path
    self.version = version
    self.fields = fields

    for field in self.FIELDS:
      if field in fields:
        setattr(self, field.replace('-', '_').lower(), fields[field])

    if self.method == 'GET' or self.method == 'HEAD':
      self.completeness = True

    if self.method == 'POST' and self.content_length is None:
      return MyHttp.BAD_REQUEST

    if self.content_length and self.content_length == '0':
      self.completeness = True

    if number != len(lines) - 1:
      self.extend(b''.join(lines[number + 1:]))

    self.success = True
    return MyHttp.OK

  def extend(self, extend_body: bytes):
    self.buffer.extend(extend_body)
    try:
      if not (self.transfer_encoding and self.transfer_encoding.lower() == 'chunked'):
        # 未设置Content
        if self.content_length is None:
          return True

        remaining = int(self.content_length) - len(self.body)
        if remaining <= 0:
          self.completeness = True
          return False

        chunk = self.buffer[:remaining]
        self.body += chunk
        self.buffer = self.buffer[remaining:]

        if len(self.body) >= int(self.content_length):
          self.completeness = True
          self.buffer.clear()
          return False

        return True

      data = self.buffer
      pos = 0
      total_length = len(data)

      while pos < total_length:
        line_end = data.find(b'\r\n', pos)
        if line_end == -1:
          self.buffer = data[pos:]
          return True

        size_line = data[pos:line_end]
        if b';' in size_line:
          size_part = size_line.split(b';')[0]
        else:
          size_part = size_line

        try:
          chunk_size = int(size_part, 16)
        except ValueError:
          return False

        if chunk_size == 0:
          if line_end + 4 > total_length or data[line_end:line_end + 4] != b'0\r\n\r\n':
            self.buffer = data[pos:]
            return True
          self.buffer.clear()
          self.completeness = True
          return False

        chunk_start = line_end + 2
        chunk_end = chunk_start + chunk_size
        if chunk_end + 2 > total_length:
          self.buffer = data[pos:]
          return True

        if data[chunk_end:chunk_end + 2] != b'\r\n':
          return False

        self.body += data[chunk_start:chunk_end]
        pos = chunk_end + 2

      self.buffer.clear()
      return True
    except Exception as e:
      print(f"Error: {e}")


class MyHttpResponse(MyHttp):
  version = None
  status = None
  fields = None
  body = None

  status_html = {}

  def __init__(self, status):
    self.version = 'HTTP/1.1'
    self.status = status
    self.fields = { 'Server': 'Chen Huang' }
    self.body = None
    with open('var/www/experiment/html/403.html', 'rb') as f:
      self.status_html[MyHttp.FORBIDDEN] = f.read()

  def __str__(self):
    info = f'{BLUE}Response: {RESET}\n'
    info += f"Version: {self.version}\n"
    info += f"Status: {self.status}\n"
    info += f"Fields: {self.fields}\n"
    info += f"Body: {truncate(self.body, 256)}\n"
    return info

  def __call__(self, *args, **kwargs):
    return self.generate()

  def generate(self, head=False) -> bytes:
    response = f'{self.version} {self.status} {LANG.HTTP[self.status]}\r\n'
    for field in self.fields:
      response += f'{field}: {self.fields[field]}\r\n'
    response += '\r\n'
    response = response.encode('utf-8')

    match self.status:
      case MyHttp.OK:
        pass
      case MyHttp.FORBIDDEN:
        self.body = self.status_html[MyHttp.FORBIDDEN]
        self.fields['Content-Type'] = 'text/html'
        self.fields['Content-Length'] = str(len(self.body))

    if self.body is None:
      return response
    if not head:
      response += self.body
    return response



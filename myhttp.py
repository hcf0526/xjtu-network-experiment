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
  BAD_REQUEST = "400"
  FORBIDDEN = "403"
  NOT_FOUND = "404"
  METHOD_NOT_ALLOWED = "405"
  REQUEST_TIMEOUT = "408"

  METHODS = ('GET', 'HEAD', 'POST')
  FIELDS = ('Host', 'User-Agent', 'Connection', 'Content-Type', 'Content-Encoding', 'Accept-Encoding')

  @staticmethod
  def url_decode(url):
    def repl(match):
      hex_value = match.group(1)
      return chr(int(hex_value, 16))

    return re.sub(r'%([0-9A-Fa-f]{2})', repl, url)


class MyHttpRequest(MyHttp):
  def __init__(self):
    self.success = False
    self.method = None
    self.path = None
    self.actual_path = None
    self.version = None
    self.fields = None
    self.body = None
    # 字段
    self.host = None
    self.user_agent = None
    self.connection = None
    self.content_type = None
    self.content_encoding = None
    self.accept_encoding = None

  def __str__(self):
    info = f'{RED}Request: {RESET}\n'
    info += f"Method: {self.method}\n"
    info += f"Path: {self.path}\n"
    info += f"Version: {self.version}\n"
    info += f"Fields: {self.fields}\n"
    info += f"Body: {truncate(self.body, 64)}\n"
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

    if number != len(lines) - 1:
      self.body = b''.join(lines[number + 1:])

    self.success = True
    return MyHttp.OK

class MyHttpResponse(MyHttp):
  version = None
  status = None
  fields = None
  body = None
  def __init__(self, status):
    self.version = 'HTTP/1.1'
    self.status = status
    self.fields = { 'Server': 'Chen Huang' }
    self.body = None

  def __str__(self):
    info = f'{BLUE}Response: {RESET}\n'
    info += f"Version: {self.version}\n"
    info += f"Status: {self.status}\n"
    info += f"Fields: {self.fields}\n"
    info += f"Body: {truncate(self.body, 64)}\n"
    return info

  def __call__(self, *args, **kwargs):
    return self.generate()

  def generate(self) -> bytes:
    response = f'{self.version} {self.status} {LANG.HTTP[self.status]}\r\n'
    for field in self.fields:
      response += f'{field}: {self.fields[field]}\r\n'
    response += '\r\n'
    response = response.encode('utf-8')
    if self.body is None:
      return response
    response += self.body
    return response


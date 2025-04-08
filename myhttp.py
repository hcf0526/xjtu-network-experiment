import re
from lang import Lang

LANG = Lang()

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
  def url_encode(url):
    """
    For Chen Wenxuan to do.
    """
    pass
  @staticmethod
  def url_decode(url):
    def repl(match):
      hex_value = match.group(1)
      return chr(int(hex_value, 16))

    return re.sub(r'%([0-9A-Fa-f]{2})', repl, url)


class MyHttpRequest(MyHttp):
  def __init__(self):
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
    info = f"Method: {self.method}\n"
    info += f"Path: {self.path}\n"
    info += f"Version: {self.version}\n"
    info += f"Fields: {self.fields}\n"
    info += f"Body: {self.body}\n"
    return info

  def __repr__(self):
    return self.__str__()

  def parse(self, request: bytes):
    if not request:
      return False
    lines = request.splitlines(keepends=True)

    # 处理请求行
    try:
      header = lines[0].decode('utf-8')
    except UnicodeDecodeError:
      return False
    header = header.rstrip('\r\n').split()
    if len(header) != 3:
      return False
    method, path, version = header
    if not path.startswith('/'):
      return False
    if not version.startswith('HTTP/'):
      return False

    # 处理请求头
    number = 0
    fields = { }
    for (number, line) in enumerate(lines[1:], start=1):
      if line == b'\r\n':
        break
      if number == len(lines) - 1:
        return False
      try:
        line = line.decode('utf-8')
      except UnicodeDecodeError:
        return False
      if ':' not in line:
        return False
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

    return True

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
    info = f"Version: {self.version}\n"
    info += f"Status: {self.status}\n"
    info += f"Fields: {self.fields}\n"
    if self.body:
      info += f"Body: {self.body[:256]}\n"
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


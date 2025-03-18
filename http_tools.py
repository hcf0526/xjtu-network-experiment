import os
import re


class Http:
  OK = "200"
  BAD_REQUEST = "400"
  NOT_FOUND = "404"
  METHOD_NOT_ALLOWED = "405"

  METHODS = ('GET', 'HEAD', 'POST')
  FIELDS = ('Host', )

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


class HttpRequest(Http):
  def __init__(self):
    self.method = None
    self.path = None
    self.version = None
    self.host = None
    self.fields = None

  def parse(self, request):
    lines = request.splitlines()
    if not lines:
      return False
    # 处理请求行
    header = lines[0]
    header = header.split()
    if len(header) != 3:
      return False
    method, path, version = header
    if method not in self.METHODS:
      return False
    if not path.startswith('/'):
      return False
    if not version.startswith('HTTP/'):
      return False

    # 处理请求头
    fields = { }
    for line in lines[1:]:
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
        setattr(self, field.lower(), fields[field])
    # print(f"{self.method=}, {self.path=}, {self.version=}, {self.host=}, {self.fields=}")

    return True

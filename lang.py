import json

class Lang:
  SERVER = None
  HTTP = None
  TYPE = None
  def __init__(self):
    with open('lang/server.json', 'r') as file:
      self.SERVER = json.load(file)
    with open('lang/http.json', 'r') as file:
      self.HTTP = json.load(file)
    with open('lang/type.json', 'r') as file:
      self.TYPE = json.load(file)
import json

class Lang:
  SERVER = None
  HTTP = None
  def __init__(self):
    with open('./var/www/lang/server.json', 'r') as file:
      self.SERVER = json.load(file)
    with open('./var/www/lang/http.json', 'r') as file:
      self.HTTP = json.load(file)
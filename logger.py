import datetime


class Logger:
  def __init__(self, log_file='log.log'):
    self.log_file = log_file
    self.file = open(self.log_file, 'w')

  def __del__(self):
    if hasattr(self, 'file') and self.file:
      self.file.close()

  def write(self, message, log_type):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp} {log_type}] {message}\n"
    self.file.write(log_entry)
    self.file.flush()

  def info(self, message):
    self.write(message, 'INFO')

  def warning(self, message):
    self.write(message, 'WARNING')

  def error(self, message):
    self.write(message, 'ERROR')
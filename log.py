import datetime

def truncate(text, max_len=1024):
  if not isinstance(text, bytes):
    return None
  byte_size = len(text)
  if len(text) <= max_len:
    return text

  truncated = text[:max_len] + f"\n[...{byte_size} Bytes Total]".encode('utf-8')
  return truncated

class Log:
  def __init__(self, log_file='log.log'):
    self.log_file = log_file
    self.file = open(self.log_file, 'w', encoding='utf-8', newline='\n')

  def __del__(self):
    if hasattr(self, 'file') and self.file:
      self.file.close()

  def write(self, message, log_type):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp} {log_type}] {message}\r\n"
    self.file.write(log_entry)
    self.file.flush()

  def info(self, message):
    self.write(message, 'INFO')

  def warning(self, message):
    self.write(message, 'WARNING')

  def error(self, message):
    self.write(message, 'ERROR')
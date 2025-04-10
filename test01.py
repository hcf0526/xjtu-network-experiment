import socket


def send_hello(ip, port):
  try:
    # 创建TCP socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
      # 设置超时（秒）
      s.settimeout(5)

      # 连接目标服务器
      s.connect((ip, port))

      # 发送消息（自动转换为bytes）
      s.sendall(b"hello" * 64)

      # 可选：接收响应（最多1024字节）
      response = s.recv(1024)
      print(f"Received: {response.decode('utf-8')}")

    print("Message sent successfully!")
  except Exception as e:
    print(f"Error: {e}")


if __name__ == "__main__":
  target_ip = input("Enter IP address: ")
  target_port = int(input("Enter port: "))
  send_hello(target_ip, target_port)
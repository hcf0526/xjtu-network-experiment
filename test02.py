# 文件：server.py
import socket

# 1. 创建TCP套接字
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# 2. 绑定IP和端口
server_address = ('10.172.72.235', 1234)  # 0.0.0.0表示监听所有网络接口
server_socket.bind(server_address)

# 3. 开始监听连接
server_socket.listen(1)
print("服务器已启动，等待客户端连接...")


# 4. 接受客户端连接
client_socket, client_address = server_socket.accept()
print(f"客户端 {client_address} 已连接")

# 5. 接收数据并回显
while True:
    data = client_socket.recv(1024)  # 接收最多1024字节
    if not data:
        break  # 客户端断开连接
    print(f"收到消息：{data.decode('utf-8')}")
    client_socket.send(data)  # 原样返回数据

# 6. 关闭连接
client_socket.close()
server_socket.close()
# 西安交通大学计算机网络实验

## 实现基于 HTTP 协议的客户端程序

基于标准的 HTTP/1.1 协议，实现一个简单的 Web 客户端程序。

### 基本要求

1. 支持 GET、HEAD 和 POST 三种请求方法；
2. 支持 URI 的 "%HEXHEX" 编码；
3. 支持 Connection: Keep-Alive 和 Connection: Close 两种连接模式；
4. 能够把一个网页中所有的内嵌对象一次全部获取；
5. 支持 Cookie 的基本机制，实现典型的网站登录；
6. 能够正确处理几种典型的应答，并支持重定向请求；
7. 支持基本的缓存处理。

### 进阶要求

1. 支持 HTTPS；
2. 支持分块传输编码、gzip 等内容编码；
3. 支持基于 POST 方法的文件上传；
4. 支持把一个网页中特定对象一次全部获取。

### 测试要求

1. 在本人的电脑运行 HTTP 客户端程序，测试网络中某个可用的 WWW 服务器；
2. 在云服务器上搭建典型 WWW 服务器（如 Apache2），在本人电脑上运行客户端程序，测试各项功能。
3. 测试中，要求在 HTTP 请求头中 User-Agent 域设置为作者的英文名字。

## 实现基于 HTTP 协议的服务器程序

基于标准的 HTTP/1.1 协议，实现一个简单的 Web 服务器程序。

### 基本要求

1. 支持 GET、HEAD 和 POST 三种请求方法；
2. 支持 URI 的 "%HEXHEX" 编码；
3. 正确给出应答；
4. 支持 Connection: Keep-Alive 和 Connection: Close 两种连接模式。
5. 可配置 Web 服务器的监听地址、监听端口和虚拟路径；
6. 能够多线程处理并发的请求，或采取其他方法正确处理多个并发连接；
7. 对于无法成功定位文件的请求，根据错误原因，作相应错误提示。支持一定的异常情况处理能力；
8. 服务可以启动和关闭；
9. 在服务器端的日志中记录每一个请求。

### 进阶要求

1. 支持 HTTPS；
2. 支持分块传输编码；
3. 支持 gzip 等内容编码；
4. 支持 Cookie 基本机制，实现典型的网站登录；
5. 支持基本的缓存处理；
6. 支持基于 POST 方法的文件上传。
7. 支持 CGI。

### 测试要求

1. 在云服务器上搭建你的 WWW 服务器，在本人的电脑运行浏览器，测试你的 WWW 服务器的各项功能。
2. 测试中，要求在 HTTP 应答头中 Server 域设置为作者的英文名字。

# RFC 2396 标准

https://www.ietf.org/rfc/rfc2396.txt

# socket 模块

## 创建 socket 对象

```python
self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
```

参数：

- `socket.AF_INET`：使用 IPv4 协议。
- `socket.SOCK_STREAM`：使用 TCP 协议。

# HTTP 协议

## 请求方法

### GET 方法

GET 用于请求服务器发送某个资源, 资源在请求行的资源路径中指定.

GET 请求行的资源路径, 开头必须为 `/`, 且遵顼 URI 编码规则. 若资源路径不存在, 则返回 `404 Not Found`. 协议版本支持识别 HTTP/1.0, HTTP/1.1, HTTP/2, HTTP/3 等. 请求头的每一行必须以 `\r\n` 结尾. 整个请求头必须再以一个 `\r\n` 结尾.

在本实验中, 允许请求的资源有 `var/www/experiment/html/index.html`, `var/www/experiment/html/images/*.jpg` 等.

### HEAD 方法

HEAD 仅返回响应头, 不返回响应体(即资源).

### POST 方法

POST 指向服务器发送数据, 数据在请求体中.

在本实验中, 客户端仅允许向 `var/www/experiment/upload` 文件夹内提交文件.

### 未支持方法

若服务器接受到了未支持的请求方法, 则返回 `405 Method Not Allowed`.

## URI 编码

URI 指请求行的资源路径, 遵守 %HEXHEX 编码方式.

RFC 2396 中规定了 URI 中保留的字符:

> 2.2. Reserved Characters
> Many URI include components consisting of or delimited by, certain special characters.  These characters are called "reserved", since their usage within the URI component is limited to their reserved purpose.  If the data for a URI component would conflict with the reserved purpose, then the conflicting data must be escaped before forming the URI. 
> reserved = ";" | "/" | "?" | ":" | "@" | "&" | "=" | "+" | "$" | ","
> The "reserved" syntax class above refers to those characters that are allowed within a URI, but which may not be allowed within a particular component of the generic URI syntax; they are used as delimiters of the components described in Section 3.
> Characters in the "reserved" set are not reserved in all contexts. The set of characters actually reserved within any given URI component is defined by that component. In general, a character is reserved if the semantics of the URI changes if the character is replaced with its escaped US-ASCII encoding.
> 2.3. Unreserved Characters 
> Data characters that are allowed in a URI but do not have a reserved purpose are called unreserved. These include upper and lower case letters, decimal digits, and a limited set of punctuation marks and symbols.
> Data characters that are allowed in a URI but do not have a reserved purpose are called unreserved. These include upper and lower case letters, decimal digits, and a limited set of punctuation marks and symbols. 
> unreserved  = alphanum | mark 
> mark = "-" | "_" | "." | "!" | "~" | "*" | "'" | "(" | ")"
> Unreserved characters can be escaped without changing the semantics of the URI, but this should not be done unless the URI is being used in a context that does not allow the unescaped character to appear.
> 2.4. Escape Sequences
> Data must be escaped if it does not have a representation using an unreserved character; this includes data that does not correspond to a printable character of the US-ASCII coded character set, or that corresponds to any US-ASCII character that is disallowed, as explained below. 
> 2.4.1. Escaped Encoding 
> An escaped octet is encoded as a character triplet, consisting of the percent character `%` followed by the two hexadecimal digits representing the octet code. For example, `%20` is the escaped encoding for the US-ASCII space character.
> escaped = "%" hex hex 
> hex = digit | "A" | "B" | "C" | "D" | "E" | "F" | "a" | "b" | "c" | "d" | "e" | "f"
> This encoding ensures that characters outside the unreserved set or disallowed characters are safely represented in a URI.

import os


def create_text_file(filename, size_kb=60):
  text = "这是一行测试文本。" * 20 + "\n"  # 约100字节/行
  lines_needed = int(size_kb * 1024 / len(text.encode('utf-8')))

  with open(filename, 'w', encoding='utf-8') as f:
    for _ in range(lines_needed):
      f.write(text)

  print(f"已生成 {os.path.getsize(filename) / 1024:.1f}KB 的文本文件: {filename}")


create_text_file('text05.txt', 30 * 1024)
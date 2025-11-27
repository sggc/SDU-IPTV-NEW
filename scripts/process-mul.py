import os
import hashlib
import urllib.request

# 配置
SOURCE_URL = "https://raw.githubusercontent.com/plsy1/iptv/refs/heads/main/multicast/multicast-weifang.m3u"
OUTPUT_FILE = "multicast-rtp.m3u"
HASH_FILE = os.path.join('.github', '.source_hash_mul.txt')

def calculate_hash(content):
    """计算内容哈希"""
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def has_source_changed(content):
    """检查源文件是否变化"""
    current_hash = calculate_hash(content)
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, 'r', encoding='utf-8') as f:
            old_hash = f.read().strip()
        return old_hash != current_hash
    return True  # 首次或没有文件都认为有变化

def save_current_hash(content):
    """保存当前源文件哈希"""
    current_hash = calculate_hash(content)
    os.makedirs(os.path.dirname(HASH_FILE), exist_ok=True)
    with open(HASH_FILE, 'w', encoding='utf-8') as f:
        f.write(current_hash)

def download_file():
    """下载源文件"""
    try:
        with urllib.request.urlopen(SOURCE_URL) as response:
            content = response.read().decode('utf-8')
        return content
    except Exception as e:
        print(f"下载文件失败: {e}")
        return None

def parse_m3u(content):
    """解析 M3U 文件内容，返回频道列表"""
    channels = []
    lines = content.strip().split('\n')
    channel = {}
    for line in lines:
        line = line.strip()
        if line.startswith('#EXTINF:'):
            if 'channel' in locals() and channel:
                channels.append(channel)
            channel = {'info': line}
        elif line.startswith('rtp://'):
            if 'channel' in locals():
                channel['url'] = line
        else:
            # 忽略其他内容
            pass
    if 'channel' in locals() and channel:
        channels.append(channel)
    return channels

def process_channels(channels):
    """处理频道，提取地区等信息"""
    for channel in channels:
        info = channel['info']
        # 提取地区（假设格式为 #EXTINF:...,地区 频道名）
        pos = info.rfind(',')
        if pos > 0:
            name = info[pos+1:].strip()
            # 分离地区和频道名（假设地区在最前面，用空格分隔）
            parts = name.split(' ', 1)
            if len(parts) == 2:
                channel['region'] = parts[0]
                channel['name'] = parts[1]
            else:
                channel['region'] = '未知'
                channel['name'] = name
        else:
            channel['region'] = '未知'
            channel['name'] = '未知'
    return channels

def modify_urls(channels):
    """修改 URL，把 rtp:// 换成 rtp://@"""
    for channel in channels:
        if 'url' in channel:
            url = channel['url']
            if url.startswith('rtp://') and not url.startswith('rtp://@'):
                channel['url'] = url.replace('rtp://', 'rtp://@', 1)
    return channels

def generate_m3u_content(channels):
    """生成新的 M3U 文件内容"""
    content = "#EXTM3U\n"
    # 按地区分组
    regions = {}
    for channel in channels:
        region = channel['region']
        if region not in regions:
            regions[region] = []
        regions[region].append(channel)
    # 排序地区
    sorted_regions = sorted(regions.keys())
    for region in sorted_regions:
        # 排序频道名
        sorted_channels = sorted(regions[region], key=lambda x: x['name'])
        for channel in sorted_channels:
            content += f"{channel['info']}\n"
            content += f"{channel['url']}\n"
    return content

def main():
    content = download_file()
    if not content:
        print("下载失败，退出")
        return False

    if not has_source_changed(content):
        print("源文件未变化，跳过处理")
        return True

    channels = parse_m3u(content)
    print(f"解析完成，共 {len(channels)} 个频道")

    channels = process_channels(channels)
    channels = modify_urls(channels)

    new_content = generate_m3u_content(channels)

    # 检查输出文件内容是否变化
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            old_content = f.read()
        if old_content == new_content:
            print("输出文件内容未发生变化，跳过写入。")
            save_current_hash(content)
            return True

    # 写入新文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"已生成新文件：{OUTPUT_FILE}")

    save_current_hash(content)
    return True

if __name__ == '__main__':
    main()

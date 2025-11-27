#!/usr/bin/env python3
import requests
import re
import hashlib
import os
from datetime import datetime

# ==================== 配置 ====================
SOURCE_M3U_URL = "https://raw.githubusercontent.com/plsy1/iptv/refs/heads/main/multicast/multicast-weifang.m3u"
OUTPUT_FILENAME = "multicast-rtp.m3u"
HASH_FILE = "scripts/.mul_hash.txt"  # 隐藏哈希记录文件
# ==============================================

class M3UProcessor:
    def __init__(self, source_url, output_file, hash_file):
        self.source_url = source_url
        self.output_file = output_file
        self.hash_file = hash_file
        self.channels = []
    
    def get_content_hash(self, content):
        """计算内容的MD5哈希值"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def get_previous_hash(self):
        """获取之前保存的源文件哈希值"""
        if os.path.exists(self.hash_file):
            with open(self.hash_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return None
    
    def save_current_hash(self, content):
        """保存当前源文件的哈希值"""
        current_hash = self.get_content_hash(content)
        os.makedirs(os.path.dirname(self.hash_file), exist_ok=True)
        with open(self.hash_file, 'w', encoding='utf-8') as f:
            f.write(current_hash)
        return current_hash
    
    def has_source_changed(self, content):
        """检查源文件是否发生变化"""
        current_hash = self.get_content_hash(content)
        previous_hash = self.get_previous_hash()
        
        if previous_hash is None:
            print("首次运行，没有之前的哈希记录")
            return True
        
        if current_hash == previous_hash:
            print("源文件没有变化，跳过处理")
            return False
        else:
            print(f"源文件发生变化: 旧哈希 {previous_hash[:8]}... -> 新哈希 {current_hash[:8]}...")
            return True
    
    def download_file(self):
        """下载M3U文件"""
        print(f"下载M3U文件从: {self.source_url}")
        response = requests.get(self.source_url)
        response.raise_for_status()
        return response.text
    
    def parse_m3u(self, content):
        """解析M3U文件内容"""
        self.channels = []
        lines = content.split('\n')
        current_channel = {}
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('#EXTM3U'):
                continue
                
            if line.startswith('#EXTINF:'):
                if current_channel and current_channel.get('url'):
                    self.channels.append(current_channel)
                
                current_channel = {
                    'extinf': line,
                    'url': None,
                    'name': self.extract_channel_name(line),
                    'tvg_name': self.extract_tvg_attribute(line, 'tvg-name'),
                    'group_title': self.extract_tvg_attribute(line, 'group-title'),
                    'original_index': len(self.channels)
                }
            elif not line.startswith('#') and current_channel:
                current_channel['url'] = line
                self.channels.append(current_channel)
                current_channel = {}
        
        if current_channel and current_channel.get('url'):
            self.channels.append(current_channel)
    
    def extract_channel_name(self, extinf_line):
        """从EXTINF行提取频道名称"""
        match = re.search(r',([^,]+)$', extinf_line)
        if match:
            return match.group(1).strip()
        return ""
    
    def extract_tvg_attribute(self, extinf_line, attribute_name):
        """提取tvg属性值"""
        pattern = f'{attribute_name}="([^"]*)"'
        match = re.search(pattern, extinf_line)
        if match:
            return match.group(1)
        return ""
    
    def update_group_title(self, channel, new_group_title):
        """更新频道的group-title属性"""
        old_extinf = channel['extinf']
        
        # 更新group-title属性
        if 'group-title=' in old_extinf:
            # 替换现有的group-title
            new_extinf = re.sub(
                r'group-title="[^"]*"',
                f'group-title="{new_group_title}"',
                old_extinf
            )
        else:
            # 添加group-title属性
            new_extinf = old_extinf.replace(
                '#EXTINF:-1 ',
                f'#EXTINF:-1 group-title="{new_group_title}" '
            )
        
        channel['extinf'] = new_extinf
        channel['group_title'] = new_group_title
        return new_extinf
    
    def find_channel_index(self, name_patterns, exact_match=False):
        """查找匹配的频道索引"""
        for i, channel in enumerate(self.channels):
            if exact_match:
                if any(pattern == channel['name'] for pattern in name_patterns):
                    return i
            else:
                if any(pattern in channel['name'] for pattern in name_patterns):
                    return i
        return -1
    
    def find_all_channel_indices(self, name_patterns, exact_match=False):
        """查找所有匹配的频道索引"""
        indices = []
        for i, channel in enumerate(self.channels):
            if exact_match:
                if any(pattern == channel['name'] for pattern in name_patterns):
                    indices.append(i)
            else:
                if any(pattern in channel['name'] for pattern in name_patterns):
                    indices.append(i)
        return indices
    
    def move_channels_after_target(self, source_patterns, target_pattern, exact_match=False):
        """将源频道移动到目标频道之后"""
        target_idx = self.find_channel_index([target_pattern], exact_match=exact_match)
        if target_idx == -1:
            print(f"警告: 未找到目标频道 '{target_pattern}'")
            return False
        
        source_indices = self.find_all_channel_indices(source_patterns, exact_match=exact_match)
        if not source_indices:
            print(f"警告: 未找到源频道 {source_patterns}")
            return False
        
        print(f"找到目标频道 '{target_pattern}' 在位置 {target_idx}")
        print(f"找到源频道 {source_patterns} 在位置 {source_indices}")
        
        channels_to_move = []
        for idx in sorted(source_indices, reverse=True):
            channel = self.channels.pop(idx)
            channels_to_move.insert(0, channel)
        
        insert_position = target_idx + 1
        for channel in channels_to_move:
            self.channels.insert(insert_position, channel)
            print(f"已将 {channel['name']} 移动到 {target_pattern} 后面 (位置: {insert_position})")
            insert_position += 1
        
        return True
    
    def process_channels(self):
        """主处理逻辑"""
        print("开始处理频道排序和分类...")

        # 1. CGTN → "其他频道"
        cgtn_indices = self.find_all_channel_indices(['CGTN'])
        for idx in cgtn_indices:
            old_group = self.channels[idx]['group_title'] or '未知分组'
            self.update_group_title(self.channels[idx], "其他频道")
            print(f"将 {self.channels[idx]['name']} 从 '{old_group}' 改为 '其他频道'")

        # 2. 复制山东卫视到CCTV1下面，改为"央视频道"
        shandong_idx = self.find_channel_index(['山东卫视'], exact_match=True)
        cctv1_idx = self.find_channel_index(['CCTV1', 'CCTV-1'])
        
        if shandong_idx != -1 and cctv1_idx != -1:
            original_shandong = self.channels[shandong_idx]
            copied_shandong = original_shandong.copy()
            self.update_group_title(copied_shandong, "央视频道")
            insert_position = cctv1_idx + 1
            self.channels.insert(insert_position, copied_shandong)
            print(f"已复制山东卫视并插入到CCTV1后面，分组改为央视频道")

        # 3. CCTV4欧洲/美洲 → 移动到山东少儿之后
        self.move_channels_after_target(
            source_patterns=['CCTV4欧洲', 'CCTV4美洲'],
            target_pattern='山东少儿'
        )

        # 4. 山东经济广播 → 改为广播频道，移到末尾
        shandong_radio_idx = self.find_channel_index(['山东经济广播'], exact_match=True)
        if shandong_radio_idx != -1:
            radio_channel = self.channels.pop(shandong_radio_idx)
            self.update_group_title(radio_channel, "广播频道")
            self.channels.append(radio_channel)
            print(f"已将山东经济广播移到末尾，分组改为广播频道")

        print("频道处理完成")
    
    def modify_urls(self):
        """修改 catchup-source 和直播 URL 中的 IP 地址"""
        print("正在修改 URL 中的 IP 地址...")
        for channel in self.channels:
            # 修改 catchup-source
            if 'catchup-source=' in channel['extinf']:
                channel['extinf'] = re.sub(
                    r'catchup-source="rtsp://([^/]+)',
                    r'catchup-source="http://192.168.100.1:5140/rtsp/\1',
                    channel['extinf']
                )
            
            # 修改直播 URL
            if channel['url']:
                channel['url'] = channel['url'].replace(
                    'http://192.168.0.1:5140',
                    'http://192.168.100.1:5140'
                )
    
    def generate_m3u_content(self):
        """生成新的M3U内容"""
        header = f"""#EXTM3U
# Source: {self.source_url}
# Modified at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# 处理规则:
# 1. CGTN频道 → 其他频道
# 2. 复制山东卫视到CCTV1下 → 央视频道
# 3. CCTV4欧洲/美洲 → 移至山东少儿后
# 4. 山东经济广播 → 广播频道 + 移至末尾
# 5. 修改 catchup-source 和直播 URL 的 IP 为 192.168.100.1

"""
        
        content = header
        for channel in self.channels:
            content += channel['extinf'] + '\n'
            content += channel['url'] + '\n'
        
        return content
    
    def process(self):
        """主处理流程"""
        try:
            content = self.download_file()
            
            if not self.has_source_changed(content):
                print("源文件未变化，跳过处理")
                if not os.path.exists(self.output_file):
                    with open(self.output_file, 'w', encoding='utf-8') as f:
                        f.write("# 源文件未变化，保持原样\n")
                return True

            self.parse_m3u(content)
            print(f"解析完成，共 {len(self.channels)} 个频道")
            
            self.process_channels()
            self.modify_urls()  # 修改 URL
            
            new_content = self.generate_m3u_content()
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            self.save_current_hash(content)
            print(f"处理完成，已保存到 {self.output_file}")
            return True
            
        except Exception as e:
            print(f"处理过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    processor = M3UProcessor(SOURCE_M3U_URL, OUTPUT_FILENAME, HASH_FILE)
    success = processor.process()
    
    if not success:
        print("处理失败")
        exit(1)

if __name__ == "__main__":
    main()

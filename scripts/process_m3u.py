#!/usr/bin/env python3
import requests
import re
import hashlib
import os
from datetime import datetime

# ==================== 需要您修改的配置 ====================
SOURCE_M3U_URL = "https://raw.githubusercontent.com/plsy1/iptv/refs/heads/main/unicast.m3u"
OUTPUT_FILENAME = "playlist.m3u"
HASH_FILE = "source_hash.txt"
# =======================================================

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
    
    def find_channel_indices(self, name_patterns, group_patterns=None, exclude_patterns=None):
        """查找匹配的频道索引"""
        indices = []
        for i, channel in enumerate(self.channels):
            name_match = any(pattern in channel['name'] for pattern in name_patterns)
            
            group_match = True
            if group_patterns:
                group_match = any(pattern in (channel['group_title'] or '') for pattern in group_patterns)
            
            exclude_match = False
            if exclude_patterns:
                exclude_match = any(pattern in channel['name'] for pattern in exclude_patterns)
            
            if name_match and group_match and not exclude_match:
                indices.append(i)
        
        return indices
    
    def process_channels(self):
        """主处理逻辑"""
        print("开始处理频道排序和分类...")
        
        # 1. 将CGTN相关频道改为"其他频道"
        cgtn_indices = self.find_channel_indices(
            name_patterns=['CGTN'],
            group_patterns=None  # 不限制原分组
        )
        
        for idx in cgtn_indices:
            old_group = self.channels[idx]['group_title'] or '未知分组'
            self.update_group_title(self.channels[idx], "其他频道")
            print(f"将 {self.channels[idx]['name']} 从 '{old_group}' 改为 '其他频道'")
        
        # 2. 移动山东卫视到CCTV4K后面
        shandong_indices = self.find_channel_indices(
            name_patterns=['山东卫视'],
            exclude_patterns=['山东卫视高清']  # 排除可能的高清频道
        )
        
        cctv4k_indices = self.find_channel_indices(
            name_patterns=['CCTV4K', 'CCTV-4K']
        )
        
        if shandong_indices and cctv4k_indices:
            shandong_idx = shandong_indices[0]
            cctv4k_idx = cctv4k_indices[0]
            
            if shandong_idx != cctv4k_idx + 1:
                shandong_channel = self.channels.pop(shandong_idx)
                
                if shandong_idx < cctv4k_idx:
                    cctv4k_idx -= 1
                
                insert_position = cctv4k_idx + 1
                self.channels.insert(insert_position, shandong_channel)
                print(f"已将山东卫视移动到CCTV4K后面 (位置: {insert_position})")
        
        # 3. 将CCTV4欧洲和美洲置于山东卫视之后
        cctv4_overseas_indices = self.find_channel_indices(
            name_patterns=['CCTV4欧洲', 'CCTV4美洲', 'CCTV4欧', 'CCTV4美'],
            exclude_patterns=['CCTV4', 'CCTV-4']  # 排除普通的CCTV4
        )
        
        # 重新查找山东卫视的新位置
        shandong_new_indices = self.find_channel_indices(['山东卫视'])
        
        if shandong_new_indices and cctv4_overseas_indices:
            shandong_idx = shandong_new_indices[0]
            
            # 将海外CCTV4频道移动到山东卫视后面
            moved_count = 0
            for overseas_idx in sorted(cctv4_overseas_indices, reverse=True):
                if overseas_idx > shandong_idx:
                    # 如果已经在山东卫视后面，跳过
                    continue
                
                overseas_channel = self.channels.pop(overseas_idx)
                insert_position = shandong_idx + 1 + moved_count
                self.channels.insert(insert_position, overseas_channel)
                print(f"已将 {overseas_channel['name']} 移动到山东卫视后面 (位置: {insert_position})")
                moved_count += 1
        
        # 4. 处理广播频道
        radio_indices = self.find_channel_indices(
            name_patterns=['山东经济广播', '山东交通广播', '山东广播'],
            group_patterns=None
        )
        
        # 将广播频道移到末尾并更改分组
        radio_channels = []
        for idx in sorted(radio_indices, reverse=True):
            radio_channel = self.channels.pop(idx)
            self.update_group_title(radio_channel, "广播频道")
            radio_channels.insert(0, radio_channel)  # 保持原有顺序
        
        # 将广播频道添加到列表末尾
        self.channels.extend(radio_channels)
        
        for channel in radio_channels:
            print(f"已将 {channel['name']} 移动到末尾并改为'广播频道'")
        
        print("频道处理完成")
    
    def generate_m3u_content(self):
        """生成新的M3U内容"""
        header = f"""#EXTM3U
# Generated by GitHub Actions
# Source: {self.source_url}
# Processed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# 处理规则:
# 1. CGTN频道改为"其他频道"
# 2. 山东卫视移动到CCTV4K后面
# 3. CCTV4欧洲/美洲移动到山东卫视后面
# 4. 广播频道移到末尾并改为"广播频道"

"""
        
        content = header
        for channel in self.channels:
            content += channel['extinf'] + '\n'
            content += channel['url'] + '\n'
        
        return content
    
    def process(self):
        """主处理流程"""
        try:
            # 下载源文件
            content = self.download_file()
            
            # 检查源文件是否发生变化
            if not self.has_source_changed(content):
                print("源文件没有变化，跳过处理")
                if not os.path.exists(self.output_file):
                    with open(self.output_file, 'w', encoding='utf-8') as f:
                        f.write("# 源文件没有变化，保持原样\n")
                return True
            
            # 解析和处理内容
            self.parse_m3u(content)
            print(f"解析完成，共 {len(self.channels)} 个频道")
            
            # 执行所有处理规则
            self.process_channels()
            
            # 生成新内容并保存
            new_content = self.generate_m3u_content()
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            # 保存当前哈希值
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

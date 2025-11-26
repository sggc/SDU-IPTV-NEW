name: Update Playlist Files

on:
  schedule:
    - cron: '*/15 * * * *'  # 每15分钟运行一次
  workflow_dispatch:  # 手动触发

jobs:
  update-playlists:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      
    - name: Download source files
      run: |
        echo "下载源播放列表文件..."
        curl -s -o source.m3u "https://raw.githubusercontent.com/sggc/SDU-IPTV-NEW/refs/heads/main/playlist.m3u"
        curl -s -o multicast-source.m3u "https://raw.githubusercontent.com/plsy1/iptv/refs/heads/main/multicast/multicast-weifang.m3u"
        echo "下载完成，主文件大小: $(wc -l < source.m3u) 行"
        echo "多播文件大小: $(wc -l < multicast-source.m3u) 行"
        
    - name: Process files
      run: |
        echo "开始处理文件..."
        
        # 创建处理脚本
        cat > process.py << 'EOF'
        import re
        import hashlib
        import os
        from datetime import datetime
        
        class M3UProcessor:
            def __init__(self, content, source_url=""):
                self.content = content
                self.source_url = source_url
                self.channels = []
            
            def parse_m3u(self):
                """解析M3U文件内容"""
                self.channels = []
                lines = self.content.split('\n')
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
                        # 精确匹配
                        if any(pattern == channel['name'] for pattern in name_patterns):
                            return i
                    else:
                        # 模糊匹配
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
                # 查找目标频道（山东少儿）
                target_idx = self.find_channel_index([target_pattern], exact_match=exact_match)
                if target_idx == -1:
                    print(f"警告: 未找到目标频道 '{target_pattern}'")
                    return False
                
                # 查找源频道（CCTV4欧洲、CCTV4美洲）
                source_indices = self.find_all_channel_indices(source_patterns, exact_match=exact_match)
                if not source_indices:
                    print(f"警告: 未找到源频道 {source_patterns}")
                    return False
                
                print(f"找到目标频道 '{target_pattern}' 在位置 {target_idx}")
                print(f"找到源频道 {source_patterns} 在位置 {source_indices}")
                
                # 收集要移动的频道
                channels_to_move = []
                for idx in sorted(source_indices, reverse=True):
                    channel = self.channels.pop(idx)
                    channels_to_move.insert(0, channel)  # 保持原有顺序
                
                # 在目标频道后面插入
                insert_position = target_idx + 1
                for channel in channels_to_move:
                    self.channels.insert(insert_position, channel)
                    print(f"已将 {channel['name']} 移动到 {target_pattern} 后面 (位置: {insert_position})")
                    insert_position += 1
                
                return True
            
            def process_channels(self):
                """主处理逻辑"""
                print("开始处理频道排序和分类...")
                
                # 1. 将CGTN相关频道改为"其他频道"
                cgtn_indices = self.find_all_channel_indices(['CGTN'])
                for idx in cgtn_indices:
                    old_group = self.channels[idx]['group_title'] or '未知分组'
                    self.update_group_title(self.channels[idx], "其他频道")
                    print(f"将 {self.channels[idx]['name']} 从 '{old_group}' 改为 '其他频道'")
                
                # 2. 复制山东卫视（不包括4K版本）到CCTV1下面，并改为"央视频道"
                shandong_idx = self.find_channel_index(['山东卫视'], exact_match=True)
                cctv1_idx = self.find_channel_index(['CCTV1', 'CCTV-1'])
                
                if shandong_idx != -1 and cctv1_idx != -1:
                    # 复制山东卫视频道
                    original_shandong = self.channels[shandong_idx].copy()
                    copied_shandong = {
                        'extinf': original_shandong['extinf'],
                        'url': original_shandong['url'],
                        'name': original_shandong['name'],
                        'tvg_name': original_shandong['tvg_name'],
                        'group_title': original_shandong['group_title'],
                        'original_index': original_shandong['original_index']
                    }
                    
                    # 修改复制频道的分组为"央视频道"
                    self.update_group_title(copied_shandong, "央视频道")
                    
                    # 在CCTV1后面插入复制的频道
                    insert_position = cctv1_idx + 1
                    self.channels.insert(insert_position, copied_shandong)
                    print(f"已复制山东卫视并插入到CCTV1后面 (位置: {insert_position})，分组改为央视频道")
                
                # 3. 将CCTV4欧洲和美洲移动到山东少儿之后
                self.move_channels_after_target(
                    source_patterns=['CCTV4欧洲', 'CCTV4美洲'],
                    target_pattern='山东少儿',
                    exact_match=False
                )
                
                # 4. 处理山东经济广播（只处理这一个广播频道）
                shandong_economic_radio_idx = self.find_channel_index(['山东经济广播'], exact_match=True)
                
                if shandong_economic_radio_idx != -1:
                    # 更改分组为"广播频道"
                    radio_channel = self.channels[shandong_economic_radio_idx]
                    old_group = radio_channel['group_title'] or '未知分组'
                    self.update_group_title(radio_channel, "广播频道")
                    print(f"将 {radio_channel['name']} 从 '{old_group}' 改为 '广播频道'")
                    
                    # 移动到列表末尾
                    radio_channel = self.channels.pop(shandong_economic_radio_idx)
                    self.channels.append(radio_channel)
                    print(f"已将 {radio_channel['name']} 移动到列表末尾")
                
                print("频道处理完成")
            
            def generate_m3u_content(self, add_epg=True):
                """生成新的M3U内容"""
                header = f"""#EXTM3U"""
                if add_epg:
                    header += """ url-tvg="https://raw.githubusercontent.com/plsy1/epg/main/e/seven-days.xml.gz"\n"""
                else:
                    header += "\n"
                
                header += f"""# Generated by GitHub Actions
# Source: {self.source_url}
# Processed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# 处理规则:
# 1. CGTN频道改为"其他频道"
# 2. 复制山东卫视到CCTV1下面并改为"央视频道"
# 3. CCTV4欧洲/美洲移动到山东少儿之后
# 4. 山东经济广播移到末尾并改为"广播频道"

"""
                
                content = header
                for channel in self.channels:
                    content += channel['extinf'] + '\n'
                    content += channel['url'] + '\n'
                
                return content
        
        print("处理单播文件...")
        
        # 处理 unicast-catchup.m3u
        with open('source.m3u', 'r', encoding='utf-8') as f:
            content = f.read()
        
        print("处理 catchup 参数...")
        # 处理 catchup-source 参数 - 只修改格式，不添加 catchup="default"
        content = re.sub(
            r'catchup-source="([^"]+?)\?tvdr=\{utc:YmdHMS\}GMT-\{utcend:YmdHMS\}GMT"',
            r'catchup-source="\1?tvdr=${(b)yyyyMMddHHmmss}GMT-${(e)yyyyMMddHHmmss}GMT&r2h-seek-offset=-28800"',
            content
        )
        
        # 在文件开头添加 EPG 信息
        content = content.replace('#EXTM3U', '#EXTM3U url-tvg="https://raw.githubusercontent.com/plsy1/epg/main/e/seven-days.xml.gz"')
        
        with open('unicast-catchup.m3u', 'w', encoding='utf-8') as f:
            f.write(content)
        print("✓ unicast-catchup.m3u 生成完成")
        
        print("处理 RTP 转换...")
        # 处理 RTP 转换
        content = re.sub(
            r'rtsp://([^"\s\r\n]+)',
            r'http://192.168.100.1:5140/rtsp/\1',
            content
        )
        
        # 在文件开头添加 EPG 信息
        content = content.replace('#EXTM3U', '#EXTM3U url-tvg="https://raw.githubusercontent.com/plsy1/epg/main/e/seven-days.xml.gz"')
        
        with open('unicast-rtp.m3u', 'w', encoding='utf-8') as f:
            f.write(content)
        print("✓ unicast-rtp.m3u 生成完成")
        
        print("处理多播文件...")
        # 读取多播文件
        with open('multicast-source.m3u', 'r', encoding='utf-8') as f:
            multicast_content = f.read()
        
        # 处理回看源 - 只修改格式，不添加 catchup="default"
        multicast_content = re.sub(
            r'catchup-source="rtsp://([^"]+?)\?tvdr=\{utc:YmdHMS\}GMT-\{utcend:YmdHMS\}GMT"',
            r'catchup-source="http://192.168.100.1:5140/rtsp/\1?tvdr=${(b)yyyyMMddHHmmss}GMT-${(e)yyyyMMddHHmmss}GMT&r2h-seek-offset=-28800"',
            multicast_content
        )
        
        # 处理直播源头部
        multicast_content = re.sub(
            r'http://192\.168\.0\.1:5140/',
            r'http://192.168.100.1:5140/',
            multicast_content
        )
        
        # 使用M3UProcessor进行频道排序
        processor = M3UProcessor(multicast_content, "https://raw.githubusercontent.com/plsy1/iptv/refs/heads/main/multicast/multicast-weifang.m3u")
        processor.parse_m3u()
        print(f"解析完成，共 {len(processor.channels)} 个频道")
        
        # 执行所有处理规则
        processor.process_channels()
        
        # 生成新内容并保存
        new_content = processor.generate_m3u_content()
        
        with open('multicast-rtp.m3u', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("✓ multicast-rtp.m3u 生成完成")
        
        EOF
        
        python3 process.py
        
    - name: Commit changes
      run: |
        git config --local user.name "github-actions[bot]"
        git config --local user.email "github-actions[bot]@users.noreply.github.com"
        git add unicast-catchup.m3u unicast-rtp.m3u multicast-rtp.m3u
        git commit -m "Update playlist files" || exit 0
        git push

# 录屏教学视频智能生产

将一段带自然讲解的手机或电脑录屏，通过本地语音识别、关键帧分析、结构化内容重构、重新配音和音画时间线重建，整理为带字幕和操作指引的标准化教学视频。

本项目面向产品培训、系统操作教程、内部流程演示和软件使用说明等场景。它处理的不是简单的视频裁剪，而是原讲解、页面状态、操作动作和业务结果之间的对应关系。

## 核心流程

```text
原始录屏
  ↓
本地语音识别与时间戳对齐
  ↓
关键帧抽取与页面变化取证
  ↓
原讲解—页面—操作—结果证据链
  ↓
口语清理、错误录制剔除与教学步骤重构
  ↓
本地配音或导入本地语音模型生成的分段音频
  ↓
根据新旁白时长重建画面时间线
  ↓
字幕、点击提示、重点聚焦、隐私遮挡和背景音乐
  ↓
FFmpeg 合成、媒体校验与成片抽帧检查
  ↓
人工对最终成片进行整体优化
```

## 已实现能力

- 使用 `FFprobe` 读取视频时长、分辨率、帧率和音轨信息；
- 使用本地 `Whisper` 模型完成中文语音识别与分段时间戳生成；
- 按时间抽取关键帧，建立画面索引；
- 使用结构化数据保存课程步骤、证据、置信度和待处理风险；
- 校验课程步骤是否越界、是否缺少证据；
- 根据分段配音的实际时长自动重建视频时间线；
- 支持点击提示、重点聚焦、隐私遮挡和步骤转场；
- 自动生成字幕、混合旁白和背景音乐；
- 输出竖屏 `1080×1920` 的 H.264/AAC 视频并验证最终媒体信息。

## 当前边界

这不是面向普通用户的图形化一键软件。目前完整流程由两部分组成：

1. 本项目的命令行程序负责素材预处理、结构校验、音画合成和结果验证；
2. 根目录的 `SKILL.md` 及 `references/` 中的 Agent 工作规范负责结合转写和关键帧，形成课程结构与渲染配置。

内容取舍、业务含义、复杂点击坐标、隐私区域和最终质量仍需要 Agent 或人工基于真实画面判断。详见 [能力边界](docs/能力边界.md)。

## 运行环境

- macOS，推荐 Apple Silicon；
- Python 3.9 或以上版本；
- FFmpeg 与 FFprobe；
- 本地语音识别默认使用 MLX Whisper；
- 默认配音使用 macOS `say`，也可导入其他本地语音模型生成的分段音频。

当前默认 ASR 模型为 `mlx-community/whisper-large-v3-turbo`。首次运行需要自行下载模型，因此严格离线使用前应先完成模型准备。

## 安装

```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[local-asr]"
```

开发与测试：

```bash
pip install -e ".[local-asr,dev]"
pytest
```

## 基本使用

### 1. 分析原始录屏

```bash
tutorial-video prepare source.mp4 --output outputs/demo
```

生成：

- `media.json`：媒体信息；
- `audio.wav`：供本地识别使用的音轨；
- `transcript.raw.json`：带时间戳的原始转写；
- `frames/`：关键帧；
- `frame-index.json`：关键帧与原视频时间的对应关系。

### 2. 生成并校验课程结构

Agent 按照根目录的 `SKILL.md` 读取全部转写和关键帧，生成 `course-draft.json`。可使用下面的命令检查时间范围和证据完整性：

```bash
tutorial-video validate-draft course-draft.json --media outputs/demo/media.json
```

### 3. 生成视频

根据课程结构形成 `render-project.json`，格式参考 [脱敏示例](examples/render-project.example.json)：

```bash
tutorial-video render render-project.json
```

默认使用 macOS 本地系统语音。若要使用其他本地 TTS，将片头和每个步骤的音频按顺序写入 `voice_files`，并设置：

```json
{
  "voice_provider": "files",
  "voice_files": [
    "voice/00-intro.wav",
    "voice/01-step.wav"
  ]
}
```

## 文档

- [工作原理](docs/工作原理.md)
- [技术架构](docs/技术架构.md)
- [完整使用教程](docs/使用教程.md)
- [能力边界](docs/能力边界.md)
- [隐私与安全](docs/隐私与安全.md)

## 发布说明

仓库不包含真实业务录屏、实际课程成片、人物信息、业务页面、模型权重、配音文件或背景音乐。使用者应确保自己拥有输入素材和音频资源的使用权。

## 许可证

项目代码采用 [MIT License](LICENSE)。模型、音色、字体、音乐和示例素材可能适用各自的许可证，使用者需要分别确认。

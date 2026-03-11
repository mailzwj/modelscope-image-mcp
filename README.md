# ModelScope Image Generation MCP

调用魔搭(ModelScope)平台图像生成API的MCP服务器。

## 功能

- 根据用户输入的鉴权token、图像尺寸和提示词生成图像
- 支持多种图像尺寸：1024x1024, 1024x1536, 1536x1024, 1344x768, 768x1344，2048x2048以内任意组合
- 使用异步任务机制，轮询等待图像生成完成

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

### 运行服务器

```bash
python server.py --stdio
```

### 测试服务器

```bash
mcp dev server.py
```

### 工具调用示例

使用 `modelscope_generate_image` 工具：

```python
{
    "token": "your_modelcope_token",
    "prompt": "A cute orange cat sitting on a sofa",
    "size": "1024x1024"
}
```

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| token | string | 是 | ModelScope API 鉴权Token |
| prompt | string | 是 | 图像内容描述（英文） |
| size | string | 否 | 图像尺寸，默认 1024x1024 |
| model | string | 否 | 使用的模型，默认 Qwen/Qwen-Image-2512 |

## 支持的图像尺寸

- `1024x1024` - 正方形 (默认)
- `1024x1536` - 竖版
- `1536x1024` - 横版
- `1344x768` - 宽屏
- `768x1344` - 竖屏

## 服务配置
```json
{
  "mcpServers": {
    "modelscope-image": {
      "command": "python3",
      "args": ["server.py"]
    }
  }
}
```

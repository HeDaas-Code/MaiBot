# 本地 Embedding 插件设计文档

## 概述

本地 Embedding 插件是一个内嵌的 GPU 推理模块，用于在本地运行 Embedding 模型，替代远程 API 调用。这降低了 API 成本，提升了隐私性，并减少了网络延迟。

## 设计目标

1. **降低成本**: 避免频繁的 Embedding API 调用
2. **提升隐私**: 敏感文本不离开本地环境
3. **减少延迟**: 本地推理响应更快
4. **GPU 加速**: 充分利用本地 GPU 资源
5. **透明集成**: 无需修改现有代码，自动替换远程 API

## 技术架构

### 核心组件

```
src/llm_models/model_client/
├── local_embedding_client.py    # 本地 Embedding 客户端
└── client_registry.py           # 客户端注册表（需注册新客户端）

plugins/maibot_local_embedding/  # 插件目录
├── __init__.py
├── plugin.json                  # 插件元数据
├── inference_server.py          # 推理服务器
├── model_manager.py             # 模型加载和管理
└── requirements.txt             # 插件依赖
```

### 工作流程

```
1. 插件启动时加载模型到 GPU
   ↓
2. 注册 LocalEmbeddingClient 到客户端注册表
   ↓
3. utils_model.py 选择模型时识别到 local-bge-m3
   ↓
4. 路由到 LocalEmbeddingClient
   ↓
5. 调用插件的推理接口
   ↓
6. 返回 Embedding 向量
```

## 实现细节

### 1. 客户端注册

**`local_embedding_client.py`**:

```python
from src.llm_models.model_client.base_client import BaseClient, ClientRegistry

class LocalEmbeddingClient(BaseClient):
    client_type = "maibot_local_embedding"
    
    async def embed_text(self, text: str, model: str, **kwargs):
        # 调用插件的推理接口
        result = await self._call_plugin_inference(text, model)
        return result
    
    async def _call_plugin_inference(self, text: str, model: str):
        # 通过插件系统调用推理服务
        pass

# 在模块加载时自动注册
ClientRegistry.register_client_class(LocalEmbeddingClient)
```

### 2. 插件实现

**`plugins/maibot_local_embedding/inference_server.py`**:

```python
import torch
from sentence_transformers import SentenceTransformer

class InferenceServer:
    def __init__(self):
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
    
    async def load_model(self, model_name: str):
        """加载模型到 GPU"""
        self.model = SentenceTransformer(model_name)
        self.model = self.model.to(self.device)
        self.model.eval()
    
    async def encode(self, texts: list[str]) -> list[list[float]]:
        """批量编码文本"""
        with torch.no_grad():
            embeddings = self.model.encode(
                texts,
                batch_size=32,
                show_progress_bar=False,
                convert_to_numpy=True
            )
        return embeddings.tolist()
```

**`plugins/maibot_local_embedding/__init__.py`**:

```python
from maibot_plugin_sdk import Plugin, PluginMetadata

class LocalEmbeddingPlugin(Plugin):
    metadata = PluginMetadata(
        name="maibot_local_embedding",
        version="1.0.0",
        author="HeDaas",
        description="本地 GPU Embedding 推理插件"
    )
    
    async def on_load(self):
        """插件加载时初始化推理服务"""
        self.inference_server = InferenceServer()
        await self.inference_server.load_model("BAAI/bge-m3")
        
        # 注册客户端
        from src.llm_models.model_client.local_embedding_client import LocalEmbeddingClient
        LocalEmbeddingClient.set_inference_server(self.inference_server)
    
    @plugin_tool()
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """对外提供的 Embedding 接口"""
        return await self.inference_server.encode(texts)
```

### 3. 模型配置

**`config/model_config.toml`**:

```toml
[models.local-bge-m3]
api_provider = "maibot_local_embedding"
model_name = "BAAI/bge-m3"
dimension = 1024
description = "本地 BGE-M3 Embedding 模型"

[tasks.utils]
embedding_model = "local-bge-m3"  # 使用本地模型
```

### 4. 集成现有系统

**无需修改的组件**:
- `src/services/embedding_service.py`: 自动使用注册的客户端
- `src/A_memorix/`: 通过 EmbeddingService 透明调用
- `src/chat/replyer/expression_vector_index.py`: 无感知使用本地模型

**唯一修改点**:
- 在应用启动时确保插件已加载
- 在 `ClientRegistry` 中注册 `LocalEmbeddingClient`

## 性能优化

### 批量处理

```python
async def encode_batch(self, texts: list[str], batch_size: int = 32):
    """批量编码以提升吞吐量"""
    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = await self.encode(batch)
        results.extend(embeddings)
    return results
```

### GPU 内存管理

```python
async def manage_memory(self):
    """监控和管理 GPU 内存"""
    if torch.cuda.is_available():
        memory_used = torch.cuda.memory_allocated() / 1024**3
        if memory_used > self.max_memory_gb:
            torch.cuda.empty_cache()
```

### 模型缓存

```python
class ModelManager:
    def __init__(self):
        self.models = {}  # 缓存多个模型
    
    async def get_model(self, model_name: str):
        if model_name not in self.models:
            self.models[model_name] = await self.load_model(model_name)
        return self.models[model_name]
```

## 部署配置

### 依赖安装

```bash
# 插件依赖
cd plugins/maibot_local_embedding
pip install -r requirements.txt

# requirements.txt 内容：
# torch>=2.0.0
# sentence-transformers>=2.2.0
# transformers>=4.30.0
```

### 模型下载

```python
# 首次运行时自动下载
from sentence_transformers import SentenceTransformer

# 下载到 ~/.cache/huggingface/
model = SentenceTransformer("BAAI/bge-m3")

# 或手动指定路径
model = SentenceTransformer("/path/to/local/model")
```

### GPU 要求

- **最低**: NVIDIA GPU with 4GB VRAM (GTX 1650+)
- **推荐**: NVIDIA GPU with 8GB+ VRAM (RTX 3060+)
- **支持**: CUDA 11.8+

## 监控和调试

### 性能指标

```python
class PerformanceMonitor:
    def __init__(self):
        self.total_requests = 0
        self.total_tokens = 0
        self.total_time = 0.0
    
    async def log_request(self, num_tokens: int, elapsed_time: float):
        self.total_requests += 1
        self.total_tokens += num_tokens
        self.total_time += elapsed_time
    
    def get_stats(self):
        return {
            "requests": self.total_requests,
            "tokens": self.total_tokens,
            "avg_time": self.total_time / max(self.total_requests, 1),
            "tokens_per_second": self.total_tokens / max(self.total_time, 0.001)
        }
```

### 日志记录

```python
import logging

logger = logging.getLogger("maibot.local_embedding")

async def encode_with_logging(self, texts: list[str]):
    logger.info(f"编码 {len(texts)} 个文本")
    start_time = time.time()
    
    try:
        result = await self.encode(texts)
        elapsed = time.time() - start_time
        logger.info(f"编码完成，耗时 {elapsed:.2f}s")
        return result
    except Exception as e:
        logger.error(f"编码失败: {e}")
        raise
```

## 故障处理

### 降级策略

```python
class EmbeddingService:
    async def embed_text(self, text: str):
        try:
            # 优先使用本地模型
            return await self.local_client.embed_text(text)
        except Exception as e:
            logger.warning(f"本地 Embedding 失败，降级到远程 API: {e}")
            # 降级到远程 API
            return await self.remote_client.embed_text(text)
```

### 常见错误

1. **CUDA Out of Memory**:
   - 减少 batch_size
   - 清理 GPU 缓存
   - 使用更小的模型

2. **模型加载失败**:
   - 检查模型路径
   - 验证模型文件完整性
   - 确认网络连接（首次下载）

3. **推理超时**:
   - 增加超时时间
   - 检查 GPU 利用率
   - 优化输入文本长度

## 测试

### 单元测试

```python
async def test_local_embedding():
    client = LocalEmbeddingClient()
    
    # 测试单个文本
    result = await client.embed_text("测试文本", model="local-bge-m3")
    assert len(result) == 1024  # BGE-M3 维度
    
    # 测试批量
    texts = ["文本1", "文本2", "文本3"]
    results = await client.embed_texts(texts)
    assert len(results) == 3
```

### 性能测试

```python
async def benchmark_local_vs_remote():
    texts = ["测试文本"] * 100
    
    # 本地推理
    start = time.time()
    local_results = await local_client.embed_texts(texts)
    local_time = time.time() - start
    
    # 远程 API
    start = time.time()
    remote_results = await remote_client.embed_texts(texts)
    remote_time = time.time() - start
    
    print(f"本地: {local_time:.2f}s")
    print(f"远程: {remote_time:.2f}s")
    print(f"加速比: {remote_time/local_time:.2f}x")
```

## 配置示例

### 完整配置

```toml
[local_embedding]
enabled = true
device = "cuda"  # 或 "cpu"
model_name = "BAAI/bge-m3"
model_path = ""  # 留空自动下载到默认路径
batch_size = 32
max_memory_gb = 6.0
timeout_seconds = 30.0

[models.local-bge-m3]
api_provider = "maibot_local_embedding"
model_name = "BAAI/bge-m3"
dimension = 1024

[tasks.utils]
embedding_model = "local-bge-m3"
```

### 环境变量

```bash
# GPU 设备选择
export CUDA_VISIBLE_DEVICES=0

# 模型缓存路径
export HF_HOME=/path/to/cache

# 禁用 tqdm 进度条
export TOKENIZERS_PARALLELISM=false
```

## 未来扩展

1. **多模型支持**:
   - 同时加载多个 Embedding 模型
   - 根据任务自动选择模型
   - 动态模型切换

2. **量化优化**:
   - INT8 量化减少内存占用
   - FP16 推理加速
   - 动态量化策略

3. **分布式推理**:
   - 多 GPU 并行推理
   - 跨机器负载均衡
   - 模型分片

4. **智能缓存**:
   - LRU 缓存常用 Embedding
   - 预计算热点文本
   - 增量更新索引

## 参考资源

- [Sentence-Transformers 文档](https://www.sbert.net/)
- [BGE-M3 模型](https://huggingface.co/BAAI/bge-m3)
- [PyTorch GPU 优化](https://pytorch.org/tutorials/recipes/recipes/tuning_guide.html)
- [插件开发指南](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/main/docs/guide.md)

## 相关文档

- [项目架构分析](project-analysis.md)
- [群聊事件跟踪器](group-event-tracker.md)

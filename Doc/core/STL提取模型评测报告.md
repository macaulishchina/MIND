# STL 提取模型评测报告

## 1. 评测概要

| 项目 | 内容 |
|------|------|
| 评测目标 | 评估不同 LLM 在 STL v2 语义提取任务上的速度、可靠性和质量 |
| 评测时间 | 2025-07 |
| 提示词版本 | STL v2 extraction prompt（90 行 / ~4600 字符，经过 8 轮迭代优化） |
| LLM 提供商 | 全部通过 leihuo（ai.leihuo.netease.com）OpenAI 兼容协议 |
| 超时限制 | 10 秒硬超时 |
| 质量评估 | LLM-as-judge（评判模型: gpt-5.4-nano） |
| 测试用例 | 20 个（含 golden_stl 标准答案） |

### 1.1 参评模型

| 模型 | 类型 |
|------|------|
| claude-opus-4-6 | 旗舰 |
| gpt-5.4 | 旗舰 |
| gpt-5.4-mini | 中等 |
| gpt-5.4-nano | 轻量 |
| mimo-v2-flash | 轻量 |
| mimo-v2-pro | 中等 |
| deepseek-v3.2 | 旗舰 |
| MiniMax-M2.7-highspeed | 中等 |

### 1.2 测试用例分布

20 个用例覆盖以下场景类别：

| 类别 | 用例 | 说明 |
|------|------|------|
| 基础 | basic | 简单偏好提取 |
| 多值 | multi-value | 多个属性值 |
| 修正 | correction | 用户修正旧事实 |
| 多事件 | multi-event | 多个独立事件 |
| 不确定 | uncertainty | 主观猜测/不确定 |
| 撤回 | retract | 用户否认事实 |
| 综合 | comprehensive | 多种语义混合 |
| 否定 | negation | 负面事实（不喜欢/不会） |
| 别名 | alias | 人名别名处理 |
| 时间 | temporal | 时间修饰语 |
| 长对话-简单 | long-simple | 50 轮简单对话 |
| 长对话-复杂 | long-complex | 10 轮复杂对话 |
| 编程 | vibecoding | 技术偏好 |
| 健康 | health | 健康与运动 |
| 问答 | qa | 用户提问（少量可提取） |
| 宠物 | pet | 宠物与关系 |
| 旅行 | travel | 旅行事件 |
| 家庭 | family | 家庭关系 |
| 职业 | career | 职业变动 |
| 美食 | food | 饮食偏好 |

## 2. 提取性能（Phase 1）

### 2.1 总览

| 模型 | 成功 | 超时 | 错误 | 成功率 | 平均耗时(ms) | 中位耗时(ms) | 平均语句数 | 总语句数 |
|------|------|------|------|--------|-------------|-------------|-----------|---------|
| gpt-5.4-mini | 20 | 0 | 0 | **100%** | **2594** | 2152 | 22.7 | 454 |
| mimo-v2-flash | 20 | 0 | 0 | **100%** | 3090 | 2948 | 21.4 | 428 |
| gpt-5.4-nano | 18 | 2 | 0 | 90% | 3808 | 3804 | 21.0 | 378 |
| gpt-5.4 | 16 | 4 | 0 | 80% | 3756 | 2927 | 15.9 | 254 |
| claude-opus-4-6 | 15 | 5 | 0 | 75% | 4732 | 5344 | 14.5 | 217 |
| deepseek-v3.2 | 10 | 10 | 0 | 50% | 4639 | 4421 | 7.4 | 74 |
| MiniMax-M2.7-highspeed | 9 | 11 | 0 | 45% | 7798 | 8657 | 8.2 | 74 |
| mimo-v2-pro | 0 | 20 | 0 | 0% | — | — | — | 0 |

### 2.2 超时用例分析

长对话用例（long-simple / long-complex）是主要超时来源，所有非 100% 成功率的模型均在这两个用例上超时。

| 模型 | 超时用例 |
|------|---------|
| gpt-5.4-nano | long-complex, long-simple |
| gpt-5.4 | family, long-complex, long-simple, travel |
| claude-opus-4-6 | family, food, long-complex, long-simple, travel |
| deepseek-v3.2 | career, family, food, health, long-complex, long-simple, pet, qa, travel, vibecoding |
| MiniMax-M2.7-highspeed | career, family, food, health, long-complex, long-simple, multi-event, pet, retract, travel, vibecoding |
| mimo-v2-pro | 全部 20 个用例 |

## 3. 质量评估（Phase 2 — LLM-as-judge）

### 3.1 评估维度

| 维度 | 权重 | 说明 |
|------|------|------|
| completeness（完整性） | 20% | 对话中所有事实是否都被提取 |
| predicate_choice（谓词选择） | 15% | 是否使用了正确的谓词 |
| argument_correctness（参数正确性） | 15% | 参数是否关联到正确的谓词和顺序 |
| correction_handling（修正处理） | 15% | correct_intent / retract_intent 是否正确使用 |
| modifier_attachment（修饰语挂载） | 10% | 时间/程度等修饰语是否挂到正确的语句 |
| no_hallucination（无幻觉） | 15% | 是否不包含对话中未提及的事实 |
| format_compliance（格式合规） | 10% | 输出是否严格符合 STL v2 语法 |

### 3.2 总体质量评分

| 模型 | 加权均分 | 最低分 | 最高分 | 评估样本数 |
|------|---------|-------|-------|-----------|
| **claude-opus-4-6** | **7.18** | 0.0 | 10.0 | 15 |
| gpt-5.4 | 6.68 | 0.0 | 9.85 | 16 |
| deepseek-v3.2 | 6.47 | 0.0 | 9.85 | 10 |
| MiniMax-M2.7-highspeed | 6.39 | 0.0 | 9.70 | 9 |
| gpt-5.4-nano | 6.18 | 2.5 | 8.70 | 18 |
| mimo-v2-flash | 6.12 | 0.0 | 9.80 | 20 |
| gpt-5.4-mini | 6.09 | 2.5 | 9.90 | 20 |

> mimo-v2-pro 全部超时，无质量评分。

### 3.3 各维度对比

| 维度 | claude-opus-4-6 | gpt-5.4 | deepseek-v3.2 | MiniMax | gpt-5.4-nano | mimo-v2-flash | gpt-5.4-mini |
|------|----------|---------|------------|---------|------------|------------|------------|
| completeness | **7.0** | 6.2 | 6.2 | 5.7 | 5.8 | 5.7 | 5.7 |
| predicate_choice | **6.4** | 6.1 | 6.0 | 5.2 | 4.9 | 5.2 | 5.3 |
| argument_correctness | **6.7** | 5.9 | 5.0 | 5.4 | 4.6 | 5.2 | 4.4 |
| correction_handling | 8.3 | 7.6 | 7.1 | 7.9 | **8.4** | 7.7 | 8.2 |
| modifier_attachment | 7.0 | 6.5 | 6.4 | **7.2** | 5.8 | 5.7 | 5.1 |
| no_hallucination | 7.5 | 7.3 | **7.9** | 7.6 | 6.9 | 6.7 | 7.4 |
| format_compliance | 7.4 | **7.6** | 6.9 | 6.2 | 7.0 | 7.0 | 6.7 |

**关键发现**：
- claude-opus-4-6 在 completeness、predicate_choice、argument_correctness 三个核心维度上均领先
- correction_handling 各模型表现接近，gpt-5.4-nano 和 claude-opus-4-6 略优
- deepseek-v3.2 的 no_hallucination 最佳（7.9），说明虽然慢但输出保守、较少编造

## 4. 综合排名

### 4.1 综合评分公式

```
composite = speed × 30% + quality × 40% + reliability × 20% + throughput × 10%
```

各维度在参评模型之间做 min-max 归一化。

### 4.2 排名结果

| 排名 | 模型 | 综合分 | 速度 | 质量 | 可靠性 | 吞吐量 |
|------|------|-------|------|------|--------|--------|
| 1 | **claude-opus-4-6** | **0.753** | 0.59 | 1.00 | 0.75 | 0.26 |
| 2 | gpt-5.4 | 0.650 | 0.78 | 0.54 | 0.80 | 0.41 |
| 3 | gpt-5.4-mini | 0.600 | 1.00 | 0.00 | 1.00 | 1.00 |
| 4 | mimo-v2-flash | 0.560 | 0.91 | 0.03 | 1.00 | 0.76 |
| 5 | gpt-5.4-nano | 0.504 | 0.77 | 0.09 | 0.90 | 0.58 |
| 6 | deepseek-v3.2 | 0.430 | 0.61 | 0.35 | 0.50 | 0.07 |
| 7 | MiniMax-M2.7-highspeed | 0.203 | 0.00 | 0.28 | 0.45 | 0.00 |
| — | mimo-v2-pro | N/A | — | — | 0% | — |

### 4.3 关键洞察

- **质量 (40%) 在综合排名中权重最高**，claude-opus-4-6 凭借质量优势拿到第一
- gpt-5.4-mini 的质量归一化为 0（因为它在质量维度上得分最低），但速度和可靠性满分
- gpt-5.4 是质量和速度最均衡的模型
- mimo-v2-pro 在 leihuo 10 秒限制下完全不可用

## 5. 模型推荐

### 推荐分层

| 层级 | 模型 | 推荐场景 |
|------|------|---------|
| **S — 生产首选** | gpt-5.4-mini | 100% 成功率 + 最快速度 + 最大吞吐。对质量要求非顶级场景的最佳选择 |
| **A — 质量首选** | claude-opus-4-6 | 综合第一、质量第一。适合对提取质量要求严格的离线评测或低频高质量场景 |
| **A — 平衡之选** | gpt-5.4 | 质量第二 + 速度尚可。兼顾质量与效率的全能型选手 |
| **B — 速度备选** | mimo-v2-flash | 100% 成功率，速度仅次于 gpt-5.4-mini，质量一般 |
| **C — 受限使用** | deepseek-v3.2 / MiniMax | 超时率高、吞吐量低。仅在特定场景备用 |
| **D — 不推荐** | mimo-v2-pro | leihuo 10s 限制下完全不可用 |

### 选型建议

- **线上实时提取**：gpt-5.4-mini（速度快、成功率高、成本低）
- **离线批量 + 高质量**：claude-opus-4-6（质量最优，但速度慢需放宽超时）
- **均衡方案**：gpt-5.4（质量与速度折中）

## 6. 评测方法论

### 6.1 提取测试

每个模型对 20 个测试用例执行 STL 提取。使用 `ThreadPoolExecutor` 内部线程池实现 10 秒硬超时（`fut.result(timeout=10)`）。记录：成功/超时/错误数、响应时间、提取语句数。

### 6.2 质量评估

使用 LLM-as-judge 方法，以 gpt-5.4-nano 为评判模型。Judge 接收三个输入：
1. 原始对话文本
2. golden_stl 标准答案
3. 模型实际提取输出

对 7 个维度分别打 0–10 分，按权重计算加权总分。

### 6.3 综合排名

四个维度在所有有效参评模型间 min-max 归一化后加权求和：
- 速度 30%（基于平均响应时间，越低越好）
- 质量 40%（基于 judge 加权均分，越高越好）
- 可靠性 20%（= 成功数 / 20）
- 吞吐量 10%（= 语句数 / 秒，越高越好）

### 6.4 工具与数据

| 文件 | 说明 |
|------|------|
| `tests/eval/prompt_opt/run_round2.py` | Round 2 评测主脚本 |
| `tests/eval/prompt_opt/judge.py` | LLM-as-judge 评估器 |
| `tests/eval/prompt_opt/cases/` | 20 个测试用例（含 golden_stl） |
| `tests/eval/prompt_opt/results_r2/` | Round 2 完整结果数据 |
| `mind/stl/prompt.py` | STL v2 提取提示词 |

## 7. 后续改进方向

1. **扩大用例规模**：当前 20 个用例可能不足以完全反映模型差异，建议扩展到 50+
2. **放宽长对话超时**：长对话场景高超时率是共性问题，可考虑对 long-* 用例单独设置更长超时
3. **多轮评判**：LLM-as-judge 可能存在偏差，可引入多评判模型交叉验证
4. **成本维度**：不同模型在 leihuo 上的 token 计价不同，加入成本效益比分析
5. **提示词版本跟踪**：随着 prompt 迭代，定期重新评测以观测趋势

# tiny-corpus-workbench

[English](README.md) | 简体中文

学习如何为语料库准备文档——证据不藏，历史不丢。

`tiny-corpus-workbench` 是一个以学习为先的项目，关注分块、嵌入、检索、
生成之前的文档准备工作。它把文档准备呈现为一条可检查的生命周期。
你可以读原理，在本地可视化 Workbench 里练，也可以通过 CLI 直接跑
同一套机制。

[项目网站](https://lifeplayer.space/tiny-corpus-workbench/) ·
[学习指南](https://lifeplayer.space/tiny-corpus-workbench/learn/) ·
[版本发布](https://github.com/jameswei/tiny-corpus-workbench/releases)

![Corpus Workbench 观察阶段](site/assets/workbench-observe.png)

## 为什么需要这个项目

原始文档不会自动变成可信的语料素材。提取可能暴露版面噪声、结构陷阱、
歧义文本，以及不同工具之间的差异。静默清理让人没法学习，也没法审计。

本项目让准备过程全程可见：

```text
原始来源
    -> 独立提取视图
    -> 规范 DoclingDocument
    -> 基于证据的诊断
    -> 受支持的提议 + 明确的决策
    -> 不可变的已准备修订版
    -> 语料库层面的检查
```

学习者可以回答四个具体问题：

1. 每个提取器产出了什么？
2. 哪些条件需要注意，证据是什么？
3. 提出了什么变更，由谁决定做不做？
4. 创建了哪个修订版，保留了哪些历史？

## 为什么适合学习

- **证据始终可查。** 来源、提取视图、发现项、提议、决策、转换、哈希、
  修订版——全程看得见。
- **诊断归诊断，决策归决策。** 发现项能识别问题，但不能批准修改。
- **变更是明确的、可逆的。** 批准的修订会创建新修订版，记录精确操作，
  不覆盖原始来源。
- **所有界面共享同一核心。** 学习指南、Workbench 和 CLI 用的都是
  同一套项目自有的应用和领域服务。
- **边界始终清晰。** 项目止于已准备修订版。下游 RAG 工作不在
  本项目范围内。

## 三种学习方式

| 界面 | 最适合 | 提供什么 |
| --- | --- | --- |
| [学习指南](https://lifeplayer.space/tiny-corpus-workbench/learn/) | 理解原理 | 双语课程，解释生命周期的每个阶段，并连接到可操作的 Workbench 练习 |
| 本地 Workbench | 观察和实践生命周期 | 面向学习者的浏览器界面，提供文档与语料库导航、准备轮次、可读对比、明确决策和聚焦证据 |
| `corpus` CLI | 重复和验证机制 | 完整生命周期、产出记录的命令，以及独立的只读验证命令 |

Workbench 和 CLI 可以共用一个本地工作区。它们是同一套准备机制的两种
界面，不是两套独立的演示实现。

## 从本地 Workbench 开始

项目需要 CPython 3.12。克隆仓库，创建虚拟环境，安装项目：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

启动 Workbench：

```bash
corpus workbench
```

命令会打印本地地址，通常自动在浏览器中打开。按 `Ctrl-C` 停止服务。

选**添加文档**，然后选引导示例 `whitespace-cleanup.md`。按顺序走完：

1. **观察**来源元数据和两个提取视图。
2. **诊断**规范文档，检查发现项 D009。
3. **修订**受支持的 R001 提议。
4. 选**批准**或**拒绝**，记录决定。
5. **修订版**阶段显示版本历史及可能产生的已准备文档。
6. 有语料库记录时，**语料库**区域显示聚合证据。

这是最短的完整练习，不需要模型，也不用碰 JSON。

Workbench 还可以观察单个本地 `.docx`、`.md`、`.pdf` 或 `.txt` 文件
（不超过 32 MiB）。上传的原始文件记录在本地，不会在浏览器中渲染或
提供下载。

## 用 CLI 跑同一条生命周期

想检查原始命令输出、或想亲手重复每一步时，用 CLI：

```bash
corpus observe fixtures/refinement/whitespace-cleanup.md
corpus verify OBSERVATION_DIRECTORY

corpus diagnose OBSERVATION_DIRECTORY
corpus verify-diagnosis DIAGNOSIS_DIRECTORY \
  --subject OBSERVATION_DIRECTORY

corpus draft-refinement DIAGNOSIS_DIRECTORY \
  --finding FINDING_ID \
  --base OBSERVATION_DIRECTORY \
  --output proposal.json

corpus resolve-refinement proposal.json \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base OBSERVATION_DIRECTORY \
  --approve

corpus verify-refinement REFINEMENT_DIRECTORY \
  --diagnosis DIAGNOSIS_DIRECTORY \
  --base OBSERVATION_DIRECTORY
```

检查 `proposal.json`，但不要编辑它。必须也只提供一个决定选项：
`--approve` 或 `--reject`。

检查一个显式语料库并验证其已发布记录：

```bash
corpus inspect fixtures/corpus/golden-matrix.json
corpus verify-corpus CORPUS_DIRECTORY \
  --spec fixtures/corpus/golden-matrix.json
```

用 `corpus --help` 或子命令的 `--help` 查看完整选项。

## 项目产出什么

产出记录的命令会发布新目录，不覆盖以前的记录。

| 记录 | 主要内容 | 学习目的 |
| --- | --- | --- |
| 观察 | 来源身份、提取结果、规范内容和对比证据 | 看提取产出了什么，独立视图之间有何差异 |
| 诊断 | 发现项、受影响项、严重程度和可读报告 | 把质量问题连接到具体证据 |
| 修订 | 提议、明确决定、报告，以及批准的转换历史 | 把建议的变更和执行变更的授权分开 |
| 已准备修订版 | 规范内容、派生 Markdown、哈希和谱系 | 检查新修订版，不丢来源和历史 |
| 语料库 | 显式成员、聚合证据、摘要和离线报告 | 在小型语料库中对比已准备文档的证据 |

无损的 `DoclingDocument` JSON 是规范文档表示。Markdown 和 HTML 是给
人看的派生视图。静态语料库报告可离线使用，不包含任意来源原文段落。

## 可选的 PDF 模型

引导式 Markdown 练习不需要下载模型。PDF 提取需要本地 Docling 模型。
有网络时下载一次即可：

```bash
docling-tools models download layout tableformer \
  --output-dir .cache/docling/models
```

观察过程不会自动下载模型。如果缺少必要模型，提取失败本身也会记录
为证据。

## 信任模型与边界

Workbench 绑定 `127.0.0.1`。它信任本地用户和本地进程，不是托管服务、
公开 API 或多用户系统。

原始来源和原始提取产物不可变。诊断不授权变更。只有你明确做出决定
之后，修订才会真的修改文档。本地哈希和验证能检测普通损坏，但不能
证明作者身份、真实性或可信时间戳。

项目有意止于已准备修订版。分块、嵌入、索引、检索、生成和 RAG 评测
属于下游。

## 继续学习

双语[学习指南](https://lifeplayer.space/tiny-corpus-workbench/learn/)
遵循与 Workbench 相同的生命周期：

1. 在下游使用前准备文档；
2. 捕获来源，检查提取；
3. 用证据诊断；
4. 做出决定，创建不可变修订版；
5. 检查语料库；
6. 亲手走完完整生命周期。

实现细节见 [docs/](docs/)。未来方向见[路线图](docs/roadmap.md)。
已发布版本见
[GitHub Releases](https://github.com/jameswei/tiny-corpus-workbench/releases)。

## 许可证

[MIT](LICENSE)

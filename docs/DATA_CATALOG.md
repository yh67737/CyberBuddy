# CyberBuddy RAG 数据目录

> 最后更新: 2026-07-14

---

## 数据集总览

| 数据集 | 文件 | 条数 | 时间范围 | 语言 | 领域 |
|--------|------|------|----------|------|------|
| IBM TechQA | `techqa_answerable.json` | 621 | 2019 | EN | IBM 产品/服务器/Linux |
| IEEE IT Support | `ieee_it_support.json` | 11,027 | 2023-2024 | EN | 网络安全/IT支持/云计算 |
| StackExchange - Super User | `stackexchange_superuser_qa.json` | 1,929 | 2022-2026 | EN | 个人PC/软件/硬件 |
| StackExchange - Server Fault | `stackexchange_serverfault_qa.json` | 1,858 | 2022-2026 | EN | 服务器/网络运维 |
| StackExchange - Ask Ubuntu | `stackexchange_askubuntu_qa.json` | 1,959 | 2022-2026 | EN | Ubuntu Linux |
| StackExchange - Unix & Linux | `stackexchange_unix_qa.json` | 1,918 | 2022-2026 | EN | Unix/Linux/Shell |
| StackExchange - 合并 | `stackexchange_it_qa.json` | 7,664 | 2022-2026 | EN | IT支持（以上4站合并） |
| **合计** | | **19,312** | 2019-2026 | | |

---

## 一、IBM TechQA

### 来源
- **官方仓库**: [github.com/IBM/techqa](https://github.com/IBM/techqa)
- **论文**: Castelli et al., "The TechQA Dataset", ACL 2020, arXiv:1911.02984
- **许可**: CDLA-Permissive v1.0

### 数据构成
- Train: 600 条（450 条可回答 + 150 条不可回答）
- Dev: 310 条（158 条可回答 + 152 条不可回答）
- Val: 20 条（10 条可回答 + 10 条不可回答）
- **本次仅使用可回答的 621 条**

### 数据特点
- 问题来自 **IBM Developer Forums** 真实用户提问
- 答案来自 **IBM Technotes**（官方技术支持文档）
- **人工标注**：6 名标注员 + 双盲审核，F1=76.3%
- 包含 `is_impossible` 标记，约 25% 问题无法从文档中回答
- 附带 80 万篇 Technote 文档库（本次未导入 RAG）

### 数据字段
| 字段 | 说明 |
|------|------|
| `id` | 唯一标识，如 `TRAIN_Q000` |
| `question` | 标题 + 正文合并 |
| `answer` | 从 Technote 中提取的答案 |
| `answerable` | 是否可回答（true/false） |
| `document_id` | 答案来源的 Technote ID |
| `source` | `IBM_TechQA` |
| `date` | `2019-04`（数据集采集时间） |

### 示例
> **Q**: User environment variables no longer getting picked up after upgrade to 4.1.1.1 or 4.1.1.2?
> **A**: To work around the issue, set environment variables that are needed by the application directly in the instance with: streamtool setproperty -d \<domain\> -i \<instance\> --application-ev \<VARIABLE NAME\>=\<VARIABLE VALUE\>

---

## 二、IEEE IT Support

### 来源
- **平台**: IEEE DataPort
- **DOI**: `10.21227/3gnj-b288`
- **原始格式**: Excel (`.xlsx`)，两列 `Question` / `Answer`

### 数据构成
- **11,027 条**问答对
- 来源混合：真实 IT 工单 + GPT-4o 合成 + Microsoft/HPE/Cisco 文档
- 无数据集内部分集划分

### 数据特点
- 覆盖三大领域：**网络安全、IT 支持、云计算**
- 人工校验过的真实工单数据
- 答案详细，通常包含步骤说明和原因解释
- 内容偏重概念解释和安全实践

### 数据字段
| 字段 | 说明 |
|------|------|
| `id` | 唯一标识，如 `IEEE_00000` |
| `question` | 完整问句 |
| `answer` | 详细答案 |
| `source` | `IEEE_IT_Support` |
| `source_type` | `real_tickets+synthetic` |

### 示例
> **Q**: What is the importance of incident documentation and reporting in a Security Operations Center (SOC) during data breach management?
> **A**: Incident documentation and reporting are critical components of data breach management... [包含合规性、问责制、事后分析、培训等多个维度的详细说明]

---

## 三、StackExchange IT 问答

### 来源
- **数据平台**: StackExchange API v2.3
- **采集脚本**: `scripts/fetch_stackexchange_qa.py`
- **采集日期**: 2026-07-13
- **许可**: CC BY-SA 3.0 / 4.0（遵循各站点用户贡献许可）

### 采集参数
| 参数 | 值 |
|------|-----|
| 排序方式 | `votes`（得票数从高到低） |
| 时间范围 | 2022-01-01 至今 |
| 每页条数 | 100 |
| 答案策略 | 优先采纳答案（accepted），否则取最高票答案 |

### 四个站点

#### Super User — 个人电脑/软件/硬件
- 网址: [superuser.com](https://superuser.com)
- 规模: ~47.8 万问题，118 万用户
- 典型内容: Windows 故障、WiFi 配置、硬盘分区、浏览器问题、外设驱动

#### Server Fault — 服务器/网络运维
- 网址: [serverfault.com](https://serverfault.com)
- 规模: ~29 万问题，77.5 万用户
- 典型内容: DNS 配置、Nginx/Apache 调优、防火墙规则、虚拟化、云服务

#### Ask Ubuntu — Ubuntu Linux
- 网址: [askubuntu.com](https://askubuntu.com)
- 规模: ~39.8 万问题，82.5 万用户
- 典型内容: apt 包管理、驱动安装、系统升级、Snap/Flatpak、桌面环境配置

#### Unix & Linux — Unix/Linux 系统级
- 网址: [unix.stackexchange.com](https://unix.stackexchange.com)
- 规模: ~24 万问题
- 典型内容: Shell 脚本、内核参数、文件系统、进程管理、管道/重定向

### 数据字段
| 字段 | 说明 |
|------|------|
| `id` | 唯一标识，如 `SE_superuser_1776464` |
| `question` | 标题 + 正文（已去除 HTML 标签） |
| `answer` | 采纳或最高票答案（已去除 HTML 标签） |
| `score` | 问题得票数 |
| `answer_score` | 答案得票数 |
| `is_accepted` | 是否为提问者采纳的答案 |
| `tags` | 标签列表，如 `["windows", "ubuntu", "wsl"]` |
| `date` | 问题创建日期（YYYY-MM-DD） |
| `site` | 来源站点 |
| `source` | `StackExchange` |
| `url` | 原始问题链接 |

### 质量统计
| 指标 | 值 |
|------|-----|
| 问题得票范围 | 2 - 382 |
| 问题得票中位数 | 6 |
| 采纳答案占比 | 60% |
| 最高票答案占比 | 40% |

### 示例
> **Site**: Super User | **Score**: 147 | **Tags**: `windows`, `ubuntu`, `wsl`
> **Q**: Ubuntu crashes on windows: 0x80040326 Wsl error
> **A**: Update your wsl system: `wsl --update`

---

## 四、数据格式规范

所有数据文件统一使用以下 JSON 格式，可直接导入 Milvus：

```json
{
  "id": "唯一标识",
  "question": "完整问题文本",
  "answer": "完整答案文本",
  "tags": ["标签", "列表"],
  "date": "YYYY-MM-DD",
  "source": "数据来源",
  "score": 0,
  "answer_score": 0,
  "is_accepted": true,
  "site": "站点标识",
  "url": "原始链接"
}
```

注：TechQA 和 IEEE 数据集部分字段可能为空（如 `tags`、`url`）。

---

## 五、后续数据扩充方向

| 来源 | 预估量 | 方式 | 优先级 |
|------|--------|------|--------|
| 企业 IT 手册/制度文档 | 500-1,000 条 | 文档分块导入 | 高 |
| 自建 FAQ（历史工单） | 500-2,000 条 | 人工整理 | 高 |
| StackExchange API（注册 key） | +5,000-10,000 条 | 扩大页数 | 中 |
| 中文 IT 社区（CSDN/知乎） | 待评估 | 爬虫 | 低 |

---

> **文件位置**: `data/` 目录
> **采集脚本**: `scripts/fetch_stackexchange_qa.py`

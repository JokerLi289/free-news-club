# Free News Club

免费资讯聚合站：从 10 个免费 RSS 源（华尔街见闻、Stratechery、Not Boring、A Wealth of Common Sense、Lil'Log、Import AI、Latent Space、Data Engineering Weekly、arXiv cs.LG / cs.DB）抓取候选，按关键词重要性打分精选、跨源去重后发布。

- 🌐 站点：https://jokerli289.github.io/free-news-club/
- 🗂 分组：快讯 / 财经深度 / AI与数据 / 学术（10 个源各为子模块）
- ⭐ 每期顶部「本期重点」5 条；每条带原文摘要，arXiv 附可展开的全文摘要
- ⏱ GitHub Actions 每小时自动更新一期（内容无变化时不产生新提交）
- 📚 历史存档：`archive.html` 索引；每日页面快照在 `archive/`，结构化数据在 `data/<日期>.json`

生成器：`scripts/fetch.py`（抓取 → 打分 → 配额 → 去重 → 渲染）。本站为静态页面，标题链接指向各源原文，内容以原文为准。

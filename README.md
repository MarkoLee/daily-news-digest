# Daily News Digest

每日科技新闻简报。流程：

1. 拉取 RSS / feed
2. 过滤、去重、排序
3. 生成中文摘要
4. 发布公开摘要页
5. 推送到飞书 webhook

## Run

```bash
python3 src/main.py --dry-run
python3 src/main.py --dry-run --force
python3 src/main.py
```

## Env

- `FEISHU_WEBHOOK_URL`
- `PUBLIC_BASE_URL`
- `GITHUB_PAGES_BASE_URL`

`PUBLIC_BASE_URL` 示例：

- `https://<your-user>.github.io/<repo-name>`

`GITHUB_PAGES_BASE_URL` 和 `PUBLIC_BASE_URL` 二选一即可。

推荐直接用 GitHub Pages：

1. 把项目放进 GitHub 仓库
2. 启用 Pages
3. 设置仓库变量或环境变量：
   - `GITHUB_PAGES_BASE_URL=https://<your-user>.github.io/<repo-name>`
   - `FEISHU_WEBHOOK_URL=<your webhook>`
4. 运行：

```bash
python3 src/main.py
```

生成后的公开地址形如：

- `https://<your-user>.github.io/<repo-name>/daily-news/2026-04-28.html`

## GitHub Pages

仓库里已附带 Pages workflow：

- [.github/workflows/deploy-pages.yml](/Users/lihang/Documents/Codex/2026-04-27/plan-users-lihang-agents-skills-software/.github/workflows/deploy-pages.yml)

它会把 `public/` 目录发布到 GitHub Pages。

## Repo Prep

建议提交到仓库的内容：

- `src/`
- `config/`
- `public/`
- `.github/workflows/`
- `README.md`
- `.env.example`
- `.gitignore`

建议不要提交：

- `data/state.json`
- `.mempalace-checkpoint.txt`
- `.DS_Store`

## Output

- 状态：[data/state.json](/Users/lihang/Documents/Codex/2026-04-27/plan-users-lihang-agents-skills-software/data/state.json)
- 公开页目录：[public/daily-news](/Users/lihang/Documents/Codex/2026-04-27/plan-users-lihang-agents-skills-software/public/daily-news)

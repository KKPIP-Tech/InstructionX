# 依赖安全管理

> 依赖漏洞发现、升级、验证与自动化策略

## 1. 版本来源

- 直接运行依赖的唯一来源是 `pyproject.toml` 的 `[project].dependencies`；
- `requirements.txt` 必须同步直接依赖的安全最低版本；
- `uv.lock` 锁定所有直接与传递依赖，Dependabot 和 CI 都以该文件为审计对象；
- 不直接导入、但必须保持安全版本的传递依赖，通过
  `[tool.uv].constraint-dependencies` 设置下限，不提升为公开运行依赖。

## 2. CI 审计

`.github/workflows/test.yml` 在 Windows + Python 3.14 环境执行：

1. `uv lock --check`，拒绝锁文件与 `pyproject.toml` 不同步；
2. `uv sync --locked --extra test`，使用锁文件安装测试环境；
3. 导出运行依赖，并使用固定版本的 pip-audit 查询 OSV；
4. 使用锁文件环境运行完整 pytest。

审计发现任何已知漏洞时 CI 失败，不允许通过忽略参数静默放行。

## 3. 升级流程

1. 先确认漏洞属于直接依赖还是传递依赖；
2. 查询 PyPI 最新稳定版本、Python 3.14 兼容性和上游修复版本；
3. 使用 `uv lock --upgrade-package <包名>` 做定向升级，避免无关依赖漂移；
4. 在独立临时环境执行 `uv sync --locked --extra test`；
5. 运行全量 pytest 及 MCP、LLM、GitHub、插件管理等相关冒烟脚本；
6. 合并到 `main` 后等待 Dependabot 重新扫描并确认告警关闭。

## 4. Dependabot

`.github/dependabot.yml` 每周检查 Python 与 GitHub Actions 依赖。安全更新按
分组创建 PR，避免同一漏洞族生成大量独立 PR；是否合并仍以完整测试和安全
扫描结果为准。

## 5. Rust / Setup 依赖

原生 Setup 的 Rust 依赖目前采用人工审查与定向升级，不宣称 `.github/dependabot.yml` 已配置 Cargo 自动更新 PR。GitHub 安全告警仍需逐项核对 `setup/Cargo.lock` 中的实际版本与上游公告范围。

升级流程：

1. 以 `setup/Cargo.toml` 声明直接依赖，以 `setup/Cargo.lock` 核对直接与传递依赖；不得只改清单而忽略锁文件。
2. 在 `setup/` 目录使用 `cargo update -p <crate>` 定向升级；若需解除旧传递依赖，可同时升级其上层依赖并记录原因。
3. 运行 `cargo fmt --check`、`cargo clippy --locked --all-targets -- -D warnings`、`cargo test --locked`，并在 `test` 分支运行全部 Rust 集成测试。
4. 运行 `scripts/smoke_setup_wizard.py`，覆盖随包二进制、薄启动器、CLI、Activity 与 dry-run 安全。
5. 使用 `setup/build_windows.ps1` 重建 Windows x64 / ARM64 资产，验证 PE 架构并更新 `tools/setup/SHA256SUMS`；不得用旧二进制冒充新依赖已生效。
6. 合并默认分支后等待 GitHub 重新扫描。未实际完成 `cargo audit` 等自动扫描时，只能声明依据公告、依赖树和测试结果完成修复，不得写成“全部漏洞已自动审计通过”。

## 6. 例外处理

不得仅为了制造“0 告警”而设置忽略列表。确需临时例外时，必须在 PR 中记录：

- 漏洞编号和影响路径；
- 为何当前代码不可利用或无法立即升级；
- 临时缓解措施；
- 负责人和移除期限。

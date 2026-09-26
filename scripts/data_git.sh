#!/usr/bin/env bash
# 私有数据仓库（GitHub: math2-textbook-map-data）的 git 入口：git 目录为 .git-data，工作区为 output/。
# 用法与 git 相同，例如：scripts/data_git.sh status；scripts/data_git.sh add -A && scripts/data_git.sh commit -m "…" && scripts/data_git.sh push
# 排除规则在 .git-data/info/exclude（大压缩包、真题原始 PDF 等）。
root="$(cd "$(dirname "$0")/.." && pwd)"
exec git --git-dir="$root/.git-data" --work-tree="$root/output" "$@"

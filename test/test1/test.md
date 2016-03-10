# 测试

## 第一章

只是个测试

## 第二章



| 概念 | 意义 |
| ---- | ---- |
| `HEAD` | 当前版本 |
| `HEAD^` | 上一个版本 |
| `HEAD~N` | 往上第 ***N*** 个版本 |
| `origin` | 远程仓库的默认名称 |
| `master` | 默认主干分支名 |



| 指令 | 意义 |
| ----- | ------ |
| `git init` | 创建仓库 |
| `git clone` | 克隆远程仓库 |
| `git status` | 当前状态 |
| `git diff` | 查看更改 |
| `git checkout file ` | 撤销工作区 ***file*** 文件的修改 |
| `git reset HEAD file` | 将暂存区文件 ***file*** 的修改撤销到工作区 |
| `git add` | 将文件修改添加到暂存区 |
| `git commit` | 提交修改(将暂存区提交到当前分支) |
| `git push` | 将本地分支提交到远程分支(设置了upstream) |
| `git push origin master` | 将本地的 ***master*** 分支推送到远程 ***origin*** 分支 |
| `git pull` | 从远程分支获取更改 |
| `git reset --hard commit_id` | 版本回退，将HEAD指向 ***commit_id*** |
| `git log` | 查看提交记录 |
| `git log --graph` | 查看分支合并图 |
| `git reflog` | 查看用户的每一次命令记录 |
| `git merge - -no-ff branch_name` | 合并 ***branch_name*** 分支到当前分支(不使用Fast Forward模式)|
| `git branch` | 查看分支 |
| `git branch branch_name` | 创建分支 ***branch_name*** |
| `git checkout branch_name` | 切换到分支 ***branch_name*** |
| `git branch -d branch_name` | 删除分支 ***branch_name*** |
| `git remote` | 查看远程仓库信息 |
| `git checkout -b local_branch_name origin/remote_branch_name` | 克隆远程分支 ***remote_branch_name*** 到本地分支 ***local_branch_name*** |
| `git branch --set-upstream local_branch_name origin/remote_branch_name` | 设置本地分支 ***local_branch_name*** 的upstream为远程分支 ***remote_branch_name*** |
| `git tag tag_name commit_id` | 在 ***commit_id*** 上设置标签 ***tag_name*** ,如果省略 ***commit_id*** 则在最后的commit上打标签 |
| `git push origin --tags` | 将tag更新到远程仓库 |

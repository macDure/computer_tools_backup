# 初始化文件夹为 Git 仓库并配置 SSH 远程地址

本文档适用于：本地已经有一个普通文件夹，希望把它初始化为 Git 仓库，并关联到 GitHub、GitLab、Gitee 或其他代码托管平台的 SSH 远程仓库。

---

## 前置条件

1. 本机已安装 Git：
   ```bash
   git --version
   ```

2. 已经配置好 SSH 公钥，并添加到远程代码平台账号中。

   如果还没有配置，可以参考当前目录中的 [github_ssh_key_guide.md](github_ssh_key_guide.md)。

3. 远程平台上已经创建好一个空仓库，并拿到 SSH 地址，例如：
   ```text
   git@github.com:username/repo.git
   git@gitlab.com:username/repo.git
   git@gitee.com:username/repo.git
   ```

---

## 快速流程

进入目标文件夹：

```bash
cd /path/to/your/project
```

初始化 Git 仓库，并使用 `main` 作为默认分支：

```bash
git init -b main
```

如果当前 Git 版本不支持 `git init -b main`，可以改用：

```bash
git init
git branch -M main
```

查看仓库状态：

```bash
git status
```

添加需要纳入版本管理的文件：

```bash
git add .
```

提交第一次提交：

```bash
git commit -m "Initial commit"
```

配置远程 SSH 仓库地址：

```bash
git remote add origin git@github.com:username/repo.git
```

确认远程地址配置正确：

```bash
git remote -v
```

推送到远程仓库，并建立本地分支和远程分支的跟踪关系：

```bash
git push -u origin main
```

---

## 完整命令示例

把 `/home/mac/my_project` 初始化为 Git 仓库，并推送到 GitHub：

```bash
cd /home/mac/my_project
git init -b main
git status
git add .
git commit -m "Initial commit"
git remote add origin git@github.com:username/my_project.git
git remote -v
git push -u origin main
```

请把下面两处替换成你自己的实际信息：

- `/home/mac/my_project`：本地项目目录
- `git@github.com:username/my_project.git`：远程仓库 SSH 地址

---

## 可选：配置提交用户名和邮箱

如果 Git 提示没有配置用户名或邮箱，可以设置全局配置：

```bash
git config --global user.name "Your Name"
git config --global user.email "your_email@example.com"
```

如果只想对当前仓库生效，去掉 `--global`：

```bash
git config user.name "Your Name"
git config user.email "your_email@example.com"
```

查看配置：

```bash
git config --list
```

---

## 可选：添加 `.gitignore`

如果项目里有不希望提交的文件，例如日志、缓存、构建产物、密钥文件，可以创建 `.gitignore`。

示例：

```gitignore
# Logs
*.log

# Cache
.cache/
__pycache__/
node_modules/

# Build output
dist/
build/

# Local env
.env
.env.*
```

创建或修改 `.gitignore` 后重新提交：

```bash
git add .gitignore
git commit -m "Add gitignore"
```

---

## 已经存在远程 origin 时如何修改

如果执行 `git remote add origin ...` 时提示：

```text
error: remote origin already exists.
```

说明当前仓库已经配置过名为 `origin` 的远程地址。

查看现有远程地址：

```bash
git remote -v
```

把 `origin` 改成新的 SSH 地址：

```bash
git remote set-url origin git@github.com:username/repo.git
```

再次确认：

```bash
git remote -v
```

---

## 远程仓库不是空仓库时

如果远程仓库已经有 README、LICENSE 或其他提交，首次推送可能出现类似错误：

```text
rejected because the remote contains work that you do not have locally
```

推荐先拉取远程内容并 rebase：

```bash
git pull --rebase origin main
git push -u origin main
```

如果远程默认分支叫 `master`，把命令中的 `main` 改为 `master`，或先统一改成本地使用的分支名。

只有在确认远程内容可以被本地覆盖时，才考虑：

```bash
git push --force-with-lease origin main
```

`--force-with-lease` 会改写远程分支历史，团队协作仓库中需要谨慎使用。

---

## 测试 SSH 连接

GitHub：

```bash
ssh -T git@github.com
```

GitLab：

```bash
ssh -T git@gitlab.com
```

Gitee：

```bash
ssh -T git@gitee.com
```

首次连接时，终端可能询问是否信任远程主机，确认域名无误后输入：

```text
yes
```

SSH 配置成功后，通常会看到类似“认证成功，但不提供 shell 登录”的提示。

---

## 常见问题

### 1. `fatal: not a git repository`

当前目录还不是 Git 仓库，或没有进入正确目录。

处理方式：

```bash
cd /path/to/your/project
git init -b main
```

### 2. `src refspec main does not match any`

通常是本地还没有任何提交，或者当前分支不叫 `main`。

处理方式：

```bash
git status
git branch
git add .
git commit -m "Initial commit"
git branch -M main
git push -u origin main
```

### 3. `Permission denied (publickey)`

SSH 公钥没有配置好，或远程地址不是 SSH 格式。

检查远程地址：

```bash
git remote -v
```

SSH 地址应该类似：

```text
git@github.com:username/repo.git
```

而不是：

```text
https://github.com/username/repo.git
```

### 4. `remote origin already exists`

当前仓库已经有 `origin`。

处理方式：

```bash
git remote set-url origin git@github.com:username/repo.git
```

### 5. 推送时提示没有权限

通常有以下原因：

- 当前 SSH key 没有添加到远程平台账号。
- 远程仓库地址写错了用户名或组织名。
- 当前账号没有该仓库的写权限。
- 使用了 HTTPS 地址而不是 SSH 地址。

可以先运行：

```bash
ssh -T git@github.com
git remote -v
```

根据输出继续排查。

---

## 推荐检查清单

推送前建议确认：

- `git status` 没有误提交不该提交的文件。
- `.gitignore` 已排除日志、缓存、构建产物、密钥和本地环境文件。
- `git remote -v` 显示的是正确 SSH 地址。
- `git branch` 当前分支是准备推送的分支，例如 `main`。
- `ssh -T git@github.com` 可以通过认证。


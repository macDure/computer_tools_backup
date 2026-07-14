# GitHub SSH 公钥配置指南

本指南将引导您生成 SSH 密钥对，并将其配置到 GitHub，以便您能够通过 SSH 协议安全、免密地拉取和推送代码。

---

## 目录
1. [第一步：生成新的 SSH 密钥](#第一步生成新的-ssh-密钥)
2. [第二步：将 SSH 密钥添加到 ssh-agent](#第二步将-ssh-密钥添加到-ssh-agent)
3. [第三步：获取 SSH 公钥内容](#第三步获取-ssh-公钥内容)
4. [第四步：在 GitHub 中配置公钥](#第四步在-github-中配置公钥)
5. [第五步：测试 SSH 连接](#第五步测试-ssh-连接)
6. [常见问题与排查](#常见问题与排查)

---

## 第一步：生成新的 SSH 密钥

打开终端，根据您的偏好选择以下任一算法生成密钥对（推荐使用更安全高效的 **Ed25519** 算法）：

### 选项 A：使用 Ed25519 算法（推荐）
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

### 选项 B：使用 RSA 算法（传统）
```bash
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
```
> **说明**：请将 `"your_email@example.com"` 替换为您在 GitHub 注册的邮箱地址。

在执行命令后，终端会提示：
1. **Enter file in which to save the key**：按 **回车 (Enter)** 接受默认保存路径（通常为 `~/.ssh/id_ed25519` 或 `~/.ssh/id_rsa`）。
2. **Enter passphrase (empty for no passphrase)**：输入密钥密码（可选）。如果不想每次拉取代码时都输入密码，可以直接按 **回车 (Enter)** 留空；如需更高安全性，可输入密码并确认。

---

## 第二步：将 SSH 密钥添加到 ssh-agent

为了让系统能够自动管理您的密钥，建议将其加入到 SSH 代理（ssh-agent）中。

1. **在后台启动 ssh-agent**：
   ```bash
   eval "$(ssh-agent -s)"
   ```
   *输出类似于 `Agent pid 12345` 即表示启动成功。*

2. **将生成的 SSH 私钥添加到 ssh-agent**：
   - 如果您使用的是 **Ed25519**：
     ```bash
     ssh-add ~/.ssh/id_ed25519
     ```
   - 如果您使用的是 **RSA**：
     ```bash
     ssh-add ~/.ssh/id_rsa
     ```

---

## 第三步：获取 SSH 公钥内容

您需要复制公钥的内容，以便将其配置到 GitHub。

使用以下命令打印公钥的内容：

- 如果是 **Ed25519**：
  ```bash
  cat ~/.ssh/id_ed25519.pub
  ```
- 如果是 **RSA**：
  ```bash
  cat ~/.ssh/id_rsa.pub
  ```

**命令输出样例：**
```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKg... your_email@example.com
```
请**完整复制**输出的整行内容（包括开头的 `ssh-ed25519` 或 `ssh-rsa`，以及结尾的邮箱地址）。

---

## 第四步：在 GitHub 中配置公钥

1. 登录您的 [GitHub 账号](https://github.com)。
2. 点击页面右上角的个人头像，选择 **Settings**（设置）。
3. 在左侧边栏中，点击 **SSH and GPG keys**。
4. 点击右上角的 **New SSH key**（新建 SSH 密钥）按钮。
5. 在弹出的页面中进行配置：
   - **Title**：给这个密钥起一个容易识别的名称（例如：`My Linux Laptop`）。
   - **Key type**：保持默认的 `Authentication Key` 即可。
   - **Key**：将您在 **第三步** 中复制的公钥内容粘贴到这个输入框中。
6. 点击 **Add SSH key** 按钮。如果提示输入 GitHub 密码，请输入密码确认。

---

## 第五步：测试 SSH 连接

配置完成后，您可以在终端中测试是否可以成功连接到 GitHub。

在终端中运行以下命令：
```bash
ssh -T git@github.com
```

如果这是您第一次连接 GitHub，终端会显示类似如下的提示：
```text
The authenticity of host 'github.com (IP_ADDRESS)' can't be established.
ED25519 key fingerprint is SHA256:+DiY3wvvV6TuJJgbpBhkFEn1WooDfl3dkuZ0DYyGx1s.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```
输入 **`yes`** 并按 **回车 (Enter)**。

如果配置成功，您将看到类似于以下的欢迎信息：
```text
Hi username! You've successfully authenticated, but GitHub does not provide shell access.
```
这就表示配置已成功，现在您可以使用 SSH 地址（例如 `git@github.com:username/repo.git`）来拉取或推送代码了！

---

## 常见问题与排查

### 1. 报错 `Permission denied (publickey)`
- **原因 1**：公钥复制不完整或粘贴错误。请重新运行 `cat` 命令并确保复制了完整的字符串。
- **原因 2**：`ssh-agent` 中没有加载私钥。请重新运行：
  ```bash
  eval "$(ssh-agent -s)"
  ssh-add ~/.ssh/id_ed25519
  ```
- **原因 3**：连接的不是 `git` 用户。使用 SSH 克隆时，地址必须是 `git@github.com:...`，而不是您的 GitHub 用户名（如 `yourname@github.com`）。

### 2. 密钥文件权限过大（`Permissions are too open`）
SSH 要求私钥文件必须是私有的。如果权限设置过大，连接会被拒绝。
您可以通过以下命令修复权限：
```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
```

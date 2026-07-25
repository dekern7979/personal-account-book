# 轻账本部署说明

## 先说清楚

当前版本使用 SQLite 文件保存账本。它适合本机使用；部署到 Streamlit Community Cloud 后，服务重启或更新时，云端 SQLite 文件可能被重置。因此，线上版当前适合**密码保护的演示或体验**，不应作为唯一的长期账本数据存储。

本机数据仍保留在 `data/account_book.db`，不会提交到 GitHub，也不会自动上传到云端。

## 上线一个带密码的访问地址

1. 进入 <https://share.streamlit.io/>，使用 GitHub 账号登录。
2. 选择仓库 `dekern7979/personal-account-book`，分支选 `main`，主文件填 `app.py`。
3. 在部署页面的 **Advanced settings → Secrets** 中粘贴下面内容，并将密码替换成你自己的：

   ```toml
   app_password = "请换成一串只有你知道的密码"
   ```

4. 点击 **Deploy**。部署成功后，只有输入密码的人才能使用该网址。

## 做成真正可长期使用的线上账本

项目已支持 Supabase PostgreSQL。项目建好后，在 Supabase 项目首页点击 **Connect**，复制其中的 **Session pooler** 连接字符串。把它仅保存到 Streamlit 的 Secrets 中：

```toml
app_password = "请换成一串只有你知道的密码"
database_url = "postgresql://..."
```

不要把这两项写入代码、上传到 GitHub 或发到聊天中。应用检测到 `database_url` 后会自动建表并把新账目写入 Supabase；本地未配置时仍使用 SQLite。

不要把密码、数据库地址或账本数据库文件提交到 GitHub。

# TIME 动态磁贴 · 云端托管方案（方案 A）

把磁贴内容放到公网静态托管（GitHub + jsDelivr），**本机零组件**：不用跑 exe、不用守护进程、不用开机自启、不占端口、不依赖你的代理。

---

## 工作原理

```
┌─ GitHub Actions（云端，每 30 分钟）─┐
│  1. 抓 TIME RSS（墙外直连，不需要代理）│
│  2. 下载文章配图，合成 620×620        │
│  3. 生成 tile.xml（轮换显示下一篇）    │
│  4. commit & push                    │
└──────────────┬──────────────────────┘
               ↓
       jsDelivr CDN（国内可直连）
               ↓
┌─ 你电脑的磁贴 ────────────────────────┐
│  系统按 manifest 每 30 分钟拉一次      │
│  → 每次都是新的文章 + 配图             │
└──────────────────────────────────────┘
```

轮换顺序：`0 → 1 → 2 → 3 → 4 → 0 …`（5 篇最新文章循环），新文章出现时从第 0 篇重新开始。

---

## 文件清单

| 文件 | 说明 |
| --- | --- |
| `build-tile.py` | 构建脚本：抓 RSS → 下配图 → 合成 → 生成 tile.xml |
| `workflow-build.yml` | GitHub Actions 工作流（每 30 分钟自动跑一次） |
| `tile.xml` | 当前磁贴内容（自动生成，别手改） |
| `img/art-0..4.jpg` | 五篇文章的合成配图 |
| `articles.json` | 元数据 + 轮换游标 |

---

## 部署步骤

### 第 1 步：建仓库

在 GitHub 上新建一个**公开**仓库，比如 `time-tile`。

### 第 2 步：上传文件

把本目录里的东西传上去：

```
time-tile/
├── build-tile.py
├── img/                        （可以为空，Actions 会填）
└── .github/
    └── workflows/
        └── build.yml           （把 workflow-build.yml 改名成 build.yml 放这里）
```

### 第 3 步：开启 Actions 写权限

仓库 → **Settings → Actions → General** → 拉到最下面：

- Workflow permissions 选 **Read and write permissions**
- 勾上 **Allow GitHub Actions to create and approve pull requests**

（不设这个，Actions 跑完没法 push 回来，会报 403）

### 第 4 步：手动跑一次

仓库 → **Actions** → 左侧选 `Build TIME tile` → 右侧 **Run workflow**。

跑完（约 1~2 分钟）检查仓库根目录是否出现了 `tile.xml` 和 `img/art-*.jpg`。

### 第 5 步：验证 CDN 能访问

浏览器打开（把 `你的用户名`、`仓库名` 换成实际的）：

```
https://cdn.jsdelivr.net/gh/你的用户名/仓库名@main/tile.xml
```

应该能看到 XML 内容。这一步必须通，否则磁贴拉不到。

### 第 6 步：改包的 manifest

磁贴的 `UriTemplate` 换成上一步那个 URL，然后重新打包安装：

```xml
<uap:TileUpdate Recurrence="halfHour"
                UriTemplate="https://cdn.jsdelivr.net/gh/你的用户名/仓库名@main/tile.xml" />
```

---

## 本地预览（可选）

想在自己电脑上先看看效果：

```powershell
cd G:\dsh-workspace\time-tile\github
$env:TILE_CDN_BASE = "https://cdn.jsdelivr.net/gh/你的用户名/仓库名@main"
$env:TIME_PROXY = "http://127.0.0.1:65532"    # 你本机有代理时填这个
G:\dsh-home\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe build-tile.py
```

没有代理时会抓取失败（TIME 的源被墙），这很正常——云端跑不需要代理。

---

## 注意事项

**jsDelivr 缓存**：它有缓存，更新后可能要等一会儿。磁贴里图片地址带 `?v=` 参数能破除缓存，本脚本已处理。

**Actions 定时不准**：GitHub 的 cron 在高负载时会延迟，最坏可能拖到一小时。想要更准可以考虑加个外部 ping 服务，但一般够用。

**仓库是公开的**：配图会公开存放（TIME 的文章图本来就公开，问题不大）。

**免费额度**：公开仓库的 Actions 免费额度足够（30 分钟一次 = 每天 48 次，每次约 1 分钟）。

---

## 与本地方案对比

| | 本地（原方案） | 云端（本方案） |
| --- | --- | --- |
| 本机进程 | exe + 守护进程 | **零** |
| 开机自启 | 要配 | **不需要** |
| 依赖代理 | 要 | **不要** |
| 端口占用 | 8899 | 无 |
| 沙箱限制 | 受影响 | 无 |
| 需要账号 | 无 | GitHub |

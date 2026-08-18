"""证书下载与安装引导。

iOS Safari / Android Chrome 的规则：https 页面即使手动点了「继续访问」，
只要证书不被系统信任，浏览器就**不会把 navigator.mediaDevices 暴露给页面**——
地址栏是 https，但麦克风 API 整个不存在，录音无从谈起。

iPhone 上必须走 .mobileconfig（描述文件）：
  · 直接下发 .crt 时 iOS 识别不稳定，加了 Content-Disposition: attachment 更会被
    直接存进「文件」App，完全不触发安装流程；
  · .mobileconfig 用 application/x-apple-aspen-config 下发，Safari 才会弹
    「此网站正尝试下载一个配置描述文件」。
  · 必须用 Safari 打开，微信/Chrome 内置浏览器一律不触发。

证书是公开信息（不含私钥），所以这些接口不需要登录，否则手机装证书前就卡住了。
"""
from __future__ import annotations

import base64
import uuid
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from ..certs import CERT_FILE, ensure_cert, local_ips
from ..config import HTTPS_PORT

router = APIRouter(tags=["cert"])

PROFILE_ID = "com.shuhuashi.board.rootca"


def _cert_der() -> bytes:
    from cryptography import x509
    ensure_cert()
    if not CERT_FILE.exists():
        raise HTTPException(status_code=404, detail="证书尚未生成")
    from cryptography.hazmat.primitives.serialization import Encoding
    cert = x509.load_pem_x509_certificate(CERT_FILE.read_bytes())
    return cert.public_bytes(Encoding.DER)


def _stable_uuid(suffix: str) -> str:
    """同一张证书每次生成同样的 UUID，重装时是覆盖而不是堆叠一堆描述文件。"""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{PROFILE_ID}.{suffix}."
                          + base64.b16encode(_cert_der()[:32]).decode()))


@router.get("/cert")
def download_cert():
    """PEM 证书，给 Android / 电脑用。注意不能加 attachment，否则 iOS 只会存文件。"""
    ensure_cert()
    if not CERT_FILE.exists():
        raise HTTPException(status_code=404, detail="证书尚未生成")
    return Response(
        CERT_FILE.read_bytes(),
        media_type="application/x-x509-ca-cert",
        headers={"Content-Disposition": 'inline; filename="shuhuashi.crt"'},
    )


@router.get("/cert/ios")
@router.get("/cert.mobileconfig")
def ios_profile():
    """iPhone / iPad 专用描述文件。Safari 会弹出「下载配置描述文件」。"""
    payload = base64.b64encode(_cert_der()).decode("ascii")
    # 每 64 字符换行，纯粹为了 plist 好看
    wrapped = "\n".join(payload[i:i + 64] for i in range(0, len(payload), 64))

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>PayloadContent</key>
  <array>
    <dict>
      <key>PayloadCertificateFileName</key>
      <string>shuhuashi.cer</string>
      <key>PayloadContent</key>
      <data>
{wrapped}
      </data>
      <key>PayloadDescription</key>
      <string>书画室看板局域网服务器的根证书，装好后手机才能录音</string>
      <key>PayloadDisplayName</key>
      <string>书画室看板 根证书</string>
      <key>PayloadIdentifier</key>
      <string>{PROFILE_ID}.cert</string>
      <key>PayloadType</key>
      <string>com.apple.security.root</string>
      <key>PayloadUUID</key>
      <string>{_stable_uuid('cert')}</string>
      <key>PayloadVersion</key>
      <integer>1</integer>
    </dict>
  </array>
  <key>PayloadDescription</key>
  <string>安装后请到「设置 → 通用 → 关于本机 → 证书信任设置」打开开关</string>
  <key>PayloadDisplayName</key>
  <string>书画室看板</string>
  <key>PayloadIdentifier</key>
  <string>{PROFILE_ID}</string>
  <key>PayloadOrganization</key>
  <string>书画室</string>
  <key>PayloadRemovalDisallowed</key>
  <false/>
  <key>PayloadType</key>
  <string>Configuration</string>
  <key>PayloadUUID</key>
  <string>{_stable_uuid('profile')}</string>
  <key>PayloadVersion</key>
  <integer>1</integer>
</dict>
</plist>
"""
    return Response(
        plist.encode("utf-8"),
        media_type="application/x-apple-aspen-config",
        headers={"Content-Disposition": 'inline; filename="shuhuashi.mobileconfig"'},
    )


@router.get("/cert/help", response_class=HTMLResponse)
def cert_help(request: Request):
    """独立的安装说明页（不依赖前端，装证书前也能打开）。"""
    ua = request.headers.get("user-agent", "")
    is_ios = any(k in ua for k in ("iPhone", "iPad", "iPod"))
    is_safari = "Safari" in ua and "CriOS" not in ua and "FxiOS" not in ua
    in_wechat = "MicroMessenger" in ua

    ips = [ip for ip in local_ips() if ip != "127.0.0.1"] or ["127.0.0.1"]
    addr = f"https://{ips[0]}:{HTTPS_PORT}"
    help_url = f"{addr}/cert/help"

    warn = ""
    if in_wechat:
        warn = ("⚠️ 你现在用的是微信内置浏览器，<strong>装不了证书</strong>。"
                "请点右上角「···」→「在 Safari 中打开」，或手动在 Safari 里输入下面的地址：<br>"
                f"<code>{escape(help_url)}</code>")
    elif is_ios and not is_safari:
        warn = ("⚠️ iPhone 上<strong>必须用 Safari</strong> 才能安装描述文件。"
                "请复制下面的地址，在 Safari 里打开：<br>"
                f"<code>{escape(help_url)}</code>")

    warn_html = f'<div class="warn">{warn}</div>' if warn else ""
    ios_first = "" if not is_ios else " open"

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>手机录音设置</title>
<style>
 body{{margin:0;padding:20px;background:#f6f5f2;color:#2b2b2b;line-height:1.7;
   font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}
 .w{{max-width:640px;margin:0 auto}}
 h1{{font-size:21px;letter-spacing:1px}}
 .card{{background:#fff;border-radius:12px;padding:16px;margin:14px 0;
   box-shadow:0 1px 3px rgba(0,0,0,.07)}}
 summary{{font-size:16px;font-weight:600;cursor:pointer;padding:4px 0}}
 .btn{{display:block;text-align:center;background:#8a6d3b;color:#fff;padding:14px;
   border-radius:10px;text-decoration:none;font-weight:600;margin:12px 0}}
 .btn.alt{{background:#fff;color:#8a6d3b;border:1px solid #e8e4dd}}
 ol{{padding-left:20px;margin:8px 0}} li{{margin:8px 0}}
 code{{background:#f1efeb;padding:2px 6px;border-radius:4px;font-size:13px;
   word-break:break-all}}
 .tip{{background:#fef3c7;border-radius:8px;padding:10px 12px;font-size:14px;color:#92400e}}
 .warn{{background:#fee2e2;border:1px solid #fca5a5;border-radius:8px;padding:12px;
   font-size:14px;color:#991b1b;margin:14px 0}}
 .key{{background:#e0f2fe;border-radius:8px;padding:10px 12px;font-size:14px;color:#075985}}
</style></head><body><div class="w">
<h1>手机录音设置</h1>
{warn_html}
<div class="card">
 <p>要在手机上"按住录音"，需要先把本系统的证书装成<strong>信任的根证书</strong>。
 只装一次，以后一直有效。</p>
 <p class="tip">只在局域网内使用，这张证书只对这台服务器有效。</p>
</div>

<details{ios_first}><summary>📱 iPhone / iPad</summary>
<div class="card">
 <a class="btn" href="/cert/ios">① 下载描述文件</a>
 <ol>
  <li>点上面的按钮，Safari 弹出<strong>"此网站正尝试下载一个配置描述文件"</strong> → 选<strong>允许</strong>。
    <br><span class="tip">没弹窗？说明不是用 Safari 打开的，见页面顶部提示。</span></li>
  <li>打开 <code>设置</code> App，顶部会出现<strong>"已下载描述文件"</strong>
    → 点进去 → 右上角<strong>安装</strong> → 输入锁屏密码 → 再次<strong>安装</strong>。
    <br>找不到的话：<code>设置 → 通用 → VPN与设备管理</code>。</li>
  <li class="key"><strong>关键一步，漏了前功尽弃：</strong><br>
    <code>设置 → 通用 → 关于本机</code> → 划到最底部 <code>证书信任设置</code>
    → 把<strong>"书画室看板"</strong>的开关<strong>打开</strong>。</li>
  <li>回 Safari 打开 <code>{escape(addr)}</code>，地址栏不再有警告，录音就能用了。</li>
 </ol>
</div>
</details>

<details><summary>🤖 Android</summary>
<div class="card">
 <a class="btn alt" href="/cert">① 下载证书文件</a>
 <ol>
  <li><code>设置</code> → 搜索<strong>"证书"</strong> → <code>安装证书</code> /
    <code>从存储设备安装</code> → 选 <strong>CA 证书</strong> → 选刚下载的文件。</li>
  <li>部分机型路径：<code>设置 → 安全 → 加密与凭据 → 安装证书 → CA 证书</code>。</li>
  <li>系统会警告"你的网络可能被监控"，这是安装自签证书的正常提示，继续即可。</li>
  <li>装好后重新打开 <code>{escape(addr)}</code>。</li>
 </ol>
</div>
</details>

<details><summary>😐 装不上 / 不想装怎么办</summary>
<div class="card">
 <p>不装也能正常用，只是不能在网页里直接录音：上传页的录音控件会自动变成
 <strong>"上传音频文件"</strong>，老师用手机自带录音机（iPhone 的"语音备忘录"）
 录好再选文件上传即可。<strong>拍照和文字评价完全不受影响。</strong></p>
 <p>另外，评语模板库里有现成的常用评语，点一下就填好，很多时候比录音还快。</p>
</div>
</details>

<p style="text-align:center;margin-top:24px"><a href="/">← 返回看板</a></p>
</div></body></html>""")

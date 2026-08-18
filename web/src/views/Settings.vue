<template>
  <!-- 设置页（规格书 §5.5） -->
  <div class="card">
    <h3>剩余课时口径</h3>
    <div class="tabs">
      <button :class="{ on: form.balance_mode === 'estimated' }" @click="setMode('estimated')">估算口径（默认）</button>
      <button :class="{ on: form.balance_mode === 'imported' }" @click="setMode('imported')">导入口径</button>
    </div>
    <p class="muted">
      估算口径 = 导入剩余 − 导入之后的评价课次数（同一天多条算 1 次）；导入口径直接显示教务导出的剩余数量。
      提醒看板的阈值判断使用当前口径。
    </p>
  </div>

  <div class="card">
    <h3>提醒阈值</h3>
    <div class="row">
      <div class="field"><label>续费预警：剩余 ≤</label><input v-model.number="form.renew_threshold" type="number" min="0" /></div>
      <div class="field"><label>到期预警：≤ N 天</label><input v-model.number="form.expire_days" type="number" min="0" /></div>
      <div class="field"><label>缺课关注：缺课 ≥</label><input v-model.number="form.absent_threshold" type="number" min="0" /></div>
    </div>
    <button class="btn" :disabled="saving" @click="save">保存设置</button>
  </div>

  <div class="card">
    <h3>备份</h3>
    <div class="kv"><span class="k">上次备份时间</span><span class="v">{{ backup.last_backup_at || '从未备份' }}</span></div>
    <div class="kv"><span class="k">备份方式</span><span class="v">{{ backup.last_backup_kind === 'manual' ? '手动' : '自动' }}</span></div>
    <div class="kv"><span class="k">已保留天数</span><span class="v">{{ backup.backup_days }} / {{ backup.keep }}</span></div>
    <div class="kv"><span class="k">备份目录</span><span class="v" style="font-size:12px">{{ backup.backup_dir }}</span></div>
    <p v-if="backup.stale" class="muted" style="color:var(--warn)">⚠️ 距上次备份已超过 48 小时。</p>
    <p class="muted">每日 02:00 自动增量备份 app.db 与 media/，保留最近 {{ backup.keep }} 份。</p>
    <button class="btn" :disabled="backing" @click="runBackup">{{ backing ? '备份中…' : '立即备份' }}</button>
  </div>

  <div class="card">
    <h3>手机录音设置</h3>
    <div class="kv"><span class="k">当前地址</span><span class="v" style="font-size:12px">{{ diag.origin }}</span></div>
    <div class="kv"><span class="k">安全上下文</span><span class="v">{{ diag.secure }}</span></div>
    <div class="kv"><span class="k">麦克风 API</span>
      <span class="v"><span :class="['pill', diag.mic === '可用' ? 'green' : 'red']">{{ diag.mic }}</span></span>
    </div>
    <div class="kv"><span class="k">录音 API</span>
      <span class="v"><span :class="['pill', diag.rec === '可用' ? 'green' : 'red']">{{ diag.rec }}</span></span>
    </div>
    <p class="muted">
      手机上要能"按住录音"，需要用 <strong>https://…:{{ store.meta.https_port || 8443 }}</strong> 打开，
      并且把证书装成手机信任的根证书——只要证书不受信任，浏览器就不会开放麦克风。
      <strong>iPhone 必须用 Safari 打开安装页</strong>（微信、Chrome 内置浏览器装不了）。
    </p>
    <a class="btn" href="/cert/help" target="_blank">证书安装说明</a>
    <div class="kv" style="margin-top:10px">
      <span class="k">手机上直接打开</span>
      <span class="v" style="font-size:12px">{{ certHelpUrl }}</span>
    </div>
  </div>

  <div class="card">
    <h3>其他</h3>
    <div class="row">
      <RouterLink class="btn ghost" to="/import">数据导入</RouterLink>
      <RouterLink class="btn ghost" to="/records">订单收支</RouterLink>
      <RouterLink class="btn ghost" to="/templates">评语模板</RouterLink>
      <RouterLink class="btn ghost" to="/asr">语音转文字</RouterLink>
      <RouterLink class="btn ghost" to="/users">用户管理</RouterLink>
    </div>
  </div>

  <div class="card">
    <h3>修改我的密码</h3>
    <div class="field"><label>原密码</label><input v-model="pwd.old" type="password" /></div>
    <div class="field"><label>新密码（至少 6 位）</label><input v-model="pwd.next" type="password" /></div>
    <button class="btn" @click="changePwd">修改密码</button>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { get, patch, post, refreshMeta, store, toast } from '../api'

const certHelpUrl = computed(() => {
  const port = store.meta.https_port || 8443
  return `https://${location.hostname}:${port}/cert/help`
})

const diag = computed(() => ({
  origin: location.origin,
  secure: window.isSecureContext ? '是' : '否',
  mic: navigator.mediaDevices?.getUserMedia ? '可用' : '不可用',
  rec: typeof window.MediaRecorder !== 'undefined' ? '可用' : '不可用',
}))

const form = reactive({ balance_mode: 'estimated', renew_threshold: 3, expire_days: 14, absent_threshold: 2 })
const backup = ref({})
const saving = ref(false)
const backing = ref(false)
const pwd = reactive({ old: '', next: '' })

async function load() {
  const d = await get('/api/settings')
  form.balance_mode = d.settings.balance_mode
  form.renew_threshold = Number(d.settings.renew_threshold)
  form.expire_days = Number(d.settings.expire_days)
  form.absent_threshold = Number(d.settings.absent_threshold)
  backup.value = d.backup
}

async function setMode(m) {
  form.balance_mode = m
  await patch('/api/settings', { balance_mode: m })
  await refreshMeta()
  toast('已切换为' + (m === 'estimated' ? '估算口径' : '导入口径'))
}

async function save() {
  saving.value = true
  try {
    await patch('/api/settings', {
      renew_threshold: form.renew_threshold,
      expire_days: form.expire_days,
      absent_threshold: form.absent_threshold,
    })
    toast('设置已保存')
  } catch (e) { toast('保存失败：' + e.message) } finally { saving.value = false }
}

async function runBackup() {
  backing.value = true
  try {
    const r = await post('/api/backup/run')
    backup.value = r.status
    toast(`备份完成，媒体新增 ${r.media_changed} 个文件`)
    await refreshMeta()
  } catch (e) { toast('备份失败：' + e.message) } finally { backing.value = false }
}

async function changePwd() {
  if (pwd.next.length < 6) { toast('新密码至少 6 位'); return }
  try {
    await post('/api/auth/change-password', { old_password: pwd.old, new_password: pwd.next })
    pwd.old = ''; pwd.next = ''
    toast('密码已修改')
  } catch (e) { toast(e.message) }
}

onMounted(load)
</script>

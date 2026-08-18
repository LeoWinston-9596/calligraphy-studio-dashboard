<template>
  <!-- 未登录 -->
  <div v-if="!store.user" class="login-wrap">
    <form class="login-box" @submit.prevent="login">
      <h1>书画室看板</h1>
      <div class="sub">局域网本地系统</div>
      <p v-if="err" class="err">{{ err }}</p>
      <div class="field">
        <label>用户名</label>
        <input v-model="form.username" autocomplete="username" autocapitalize="off" />
      </div>
      <div class="field">
        <label>密码</label>
        <input v-model="form.password" type="password" autocomplete="current-password" />
      </div>
      <button class="btn block" :disabled="busy">{{ busy ? '登录中…' : '登录' }}</button>
    </form>
  </div>

  <!-- 首次登录强制改密 -->
  <div v-else-if="store.user.must_change_password" class="login-wrap">
    <form class="login-box" @submit.prevent="changePwd">
      <h1>设置新密码</h1>
      <div class="sub">首次登录必须修改初始密码</div>
      <p v-if="err" class="err">{{ err }}</p>
      <div class="field">
        <label>新密码（至少 6 位）</label>
        <input v-model="pwd.a" type="password" autocomplete="new-password" />
      </div>
      <div class="field">
        <label>确认新密码</label>
        <input v-model="pwd.b" type="password" autocomplete="new-password" />
      </div>
      <button class="btn block" :disabled="busy">保存并进入</button>
    </form>
  </div>

  <!-- 主界面 -->
  <div v-else class="app">
    <header class="topbar">
      <h1>{{ $route.meta.title || '书画室看板' }}</h1>
      <span class="who">{{ store.user.name }} · {{ store.user.role_label }}</span>
      <button class="btn ghost sm" @click="logout">退出</button>
    </header>

    <div class="asof">
      学员/课时数据截至：{{ store.meta.asof?.courses_asof || '尚未导入' }}
      <span style="float:right">{{ store.meta.balance_mode === 'imported' ? '导入口径' : '估算口径' }}</span>
    </div>

    <!-- 录音不可用：区分「还在 HTTP」和「证书没被信任」两种原因 -->
    <div v-if="micHint" class="banner" style="background:#e0f2fe;border-color:#7dd3fc;color:#075985">
      🎤 {{ micHint.text }}
      <a :href="micHint.link" style="font-weight:600;text-decoration:underline">{{ micHint.linkText }}</a>
    </div>

    <div v-if="store.meta.backup?.stale" class="banner">
      ⚠️ 距上次备份已超过 48 小时{{ store.meta.backup.last_backup_at ? '（' + store.meta.backup.last_backup_at + '）' : '（从未备份）' }}，
      建议前往<RouterLink to="/settings">设置页</RouterLink>立即备份。
    </div>

    <main class="content">
      <RouterView :key="$route.fullPath" />
    </main>

    <nav class="tabbar">
      <RouterLink to="/workbench" :class="{ active: tab === 'workbench' }"><span class="ico">🖌</span>工作台</RouterLink>
      <RouterLink to="/students" :class="{ active: tab === 'students' }"><span class="ico">👥</span>学员</RouterLink>
      <RouterLink to="/alerts" :class="{ active: tab === 'alerts' }"><span class="ico">🔔</span>提醒</RouterLink>
      <RouterLink to="/settings" :class="{ active: tab === 'more' }"><span class="ico">⚙️</span>更多</RouterLink>
    </nav>
  </div>

  <div v-if="store.toast" class="toast">{{ store.toast }}</div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, post, refreshMeta, store } from './api'

const route = useRoute()
const router = useRouter()
const form = reactive({ username: '', password: '' })
const pwd = reactive({ a: '', b: '' })
const err = ref('')
const busy = ref(false)

const tab = computed(() => route.meta.tab)

const httpsUrl = computed(() => {
  const port = store.meta.https_port || 8443
  return `https://${location.hostname}:${port}${route.fullPath}`
})

// 只在手机可能要录音时提示；localhost 本身就是安全上下文，电脑上不会误报
const micHint = computed(() => {
  if (navigator.mediaDevices?.getUserMedia) return null
  if (location.protocol === 'http:') {
    return { text: '当前是 HTTP，手机不能录音。', link: httpsUrl.value, linkText: '点这里切换到 HTTPS' }
  }
  return {
    text: '证书未被手机信任，麦克风被屏蔽（地址栏是 https 也一样）。',
    link: '/cert/help',
    linkText: '一次性装好证书 →',
  }
})

onMounted(async () => {
  try {
    store.user = await get('/api/auth/me')
    await refreshMeta()
  } catch { store.user = null }
})

async function login() {
  err.value = ''
  busy.value = true
  try {
    store.user = await post('/api/auth/login', { username: form.username, password: form.password })
    await refreshMeta()
  } catch (e) { err.value = e.message } finally { busy.value = false }
}

async function changePwd() {
  err.value = ''
  if (pwd.a.length < 6) { err.value = '新密码至少 6 位'; return }
  if (pwd.a !== pwd.b) { err.value = '两次输入不一致'; return }
  busy.value = true
  try {
    store.user = await post('/api/auth/change-password', { new_password: pwd.a })
    await refreshMeta()
  } catch (e) { err.value = e.message } finally { busy.value = false }
}

async function logout() {
  await post('/api/auth/logout')
  store.user = null
  router.push('/workbench')
}
</script>

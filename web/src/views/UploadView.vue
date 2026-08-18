<template>
  <!-- 上传页（规格书 §5.2）：拍照 ≤3 → 评价三选一 → 可选评级 → 提交 -->
  <div class="card">
    <h3>{{ student.name || '学员' }}</h3>
    <div class="muted">
      学号 {{ student.student_no || '—' }}
      <span v-if="student.total_balance"> · 剩余 {{ student.total_balance.display }}</span>
    </div>
  </div>

  <div class="card">
    <h3>作品照片（最多 3 张）</h3>
    <div v-if="previews.length" class="photos" style="margin-bottom:10px">
      <div v-for="(p, i) in previews" :key="i" class="thumb-wrap">
        <img :src="p" alt="预览" />
        <button class="rm" @click="removePhoto(i)">×</button>
      </div>
    </div>
    <div class="row">
      <button class="btn ghost" @click="cameraInput.click()">📷 拍照</button>
      <button class="btn ghost" @click="albumInput.click()">🖼 从相册选</button>
    </div>
    <input ref="cameraInput" type="file" accept="image/*" capture="environment" hidden @change="addPhotos" />
    <input ref="albumInput" type="file" accept="image/*" multiple hidden @change="addPhotos" />
  </div>

  <div class="card">
    <h3>评价方式</h3>
    <div class="tabs">
      <button :class="{ on: evalType === 'voice' }" @click="evalType = 'voice'">🎤 语音</button>
      <button :class="{ on: evalType === 'text' }" @click="evalType = 'text'">✍️ 文字</button>
      <button :class="{ on: evalType === 'none' }" @click="evalType = 'none'">跳过</button>
    </div>

    <!-- 语音 -->
    <div v-if="evalType === 'voice'">
      <template v-if="canRecord">
        <div class="rec-btn" :class="{ on: recording }"
             @pointerdown.prevent="startRec" @pointerup.prevent="stopRec"
             @pointercancel.prevent="stopRec" @pointerleave="recording && stopRec()">
          {{ recording ? `松开结束 · ${seconds}s` : (audioUrl ? '按住重新录制' : '按住说话') }}
        </div>
        <audio v-if="audioUrl" :src="audioUrl" controls />
        <p class="muted" style="margin-top:6px">录好后可先试听，不满意可重录。</p>
      </template>
      <template v-else>
        <p class="muted" style="margin-bottom:8px">
          <strong>{{ micReason.title }}</strong><br />
          {{ micReason.detail }}
          <a v-if="micReason.link" :href="micReason.link" style="font-weight:600;text-decoration:underline">
            {{ micReason.linkText }}
          </a>
        </p>
        <p class="muted" style="margin-bottom:8px">先用文件上传也可以，功能不受影响：</p>
        <input type="file" accept="audio/*" @change="pickAudio" />
        <audio v-if="audioUrl" :src="audioUrl" controls />
        <details style="margin-top:10px">
          <summary class="muted" style="cursor:pointer">诊断信息（截图发给技术支持）</summary>
          <div class="muted" style="font-size:12px;word-break:break-all">
            <div>地址：{{ diag.origin }}</div>
            <div>安全上下文 isSecureContext：{{ diag.secure }}</div>
            <div>麦克风 API mediaDevices：{{ diag.mediaDevices }}</div>
            <div>录音 API MediaRecorder：{{ diag.recorder }}</div>
            <div>浏览器：{{ diag.ua }}</div>
          </div>
        </details>
      </template>
    </div>

    <!-- 文字 -->
    <div v-else-if="evalType === 'text'">
      <div class="field">
        <textarea v-model="evalText" placeholder="输入评价，或点下方模板快捷选"></textarea>
      </div>
      <div class="tabs">
        <button v-for="c in categories" :key="c" :class="{ on: cat === c }" @click="cat = c">{{ c }}</button>
      </div>
      <div v-if="filteredTemplates.length" class="row" style="gap:6px">
        <button v-for="t in filteredTemplates" :key="t.id" class="btn ghost sm"
                style="flex:none;text-align:left;white-space:normal" @click="applyTemplate(t)">
          {{ t.text }}
        </button>
      </div>
      <p v-else class="muted">该分组暂无模板，可在<RouterLink to="/templates">评语模板</RouterLink>中添加。</p>
    </div>

    <p v-else class="muted">本次不填写评价，仅保存作品照片。</p>
  </div>

  <div class="card">
    <h3>评级（可选）</h3>
    <div class="tabs">
      <button v-for="r in ratings" :key="r" :class="{ on: rating === r }"
              @click="rating = rating === r ? '' : r">{{ r || '不评级' }}</button>
    </div>

    <div class="field" style="margin-top:10px">
      <label>上课日期</label>
      <input v-model="lessonDate" type="date" />
    </div>
    <div class="field">
      <label>班级（决定这次评价算到哪个课程）</label>
      <select v-model="className">
        <option value="">未指定</option>
        <option v-for="c in classOptions" :key="c" :value="c">{{ c }}</option>
      </select>
      <p class="muted" style="margin-top:4px">对应课程：{{ courseName || '—' }}</p>
    </div>
  </div>

  <button class="btn block" :disabled="submitting" @click="submit">
    {{ submitting ? '提交中…' : '提交' }}
  </button>
  <button class="btn ghost block" style="margin-top:8px" @click="$router.back()">返回</button>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, store, toast, upload, todayStr } from '../api'

const route = useRoute()
const router = useRouter()
const studentId = route.params.studentId

const student = ref({})
const photos = ref([])
const previews = ref([])
const cameraInput = ref(null)
const albumInput = ref(null)

const evalType = ref('voice')
const evalText = ref('')
const rating = ref('')
const ratings = ['优', '良', '需加强']
const lessonDate = ref(todayStr())
const className = ref('')
const submitting = ref(false)

const templates = ref([])
const categories = ['书法', '美术', '通用']
const cat = ref('通用')

const canRecord = ref(false)
const recording = ref(false)
const seconds = ref(0)
const audioBlob = ref(null)
const audioUrl = ref('')
let recorder = null
let chunks = []
let stream = null
let timer = null

const httpsUrl = computed(() => {
  if (location.protocol !== 'http:') return ''
  const port = store.meta.https_port || 8443
  return `https://${location.hostname}:${port}${route.fullPath}`
})

const diag = computed(() => ({
  origin: location.origin,
  secure: window.isSecureContext ? '是' : '否',
  mediaDevices: navigator.mediaDevices?.getUserMedia ? '可用' : '不可用',
  recorder: typeof window.MediaRecorder !== 'undefined' ? '可用' : '不可用',
  ua: navigator.userAgent.slice(0, 90),
}))

// 分清三种失败原因，别把它们混成一句话
const micReason = computed(() => {
  if (location.protocol === 'http:') {
    return {
      title: '当前是 HTTP，浏览器一律禁止录音',
      detail: '换成 HTTPS 地址即可。',
      link: httpsUrl.value,
      linkText: '点这里切到 HTTPS',
    }
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    // https 却拿不到麦克风 —— 几乎都是证书没被系统信任
    return {
      title: '证书未被手机信任，麦克风被浏览器屏蔽',
      detail: '地址栏虽然是 https，但只要证书不受信任，Safari / Chrome 就不会开放麦克风。'
        + '按说明把证书装成信任的根证书即可（只需一次）。',
      link: '/cert/help',
      linkText: '查看安装步骤 →',
    }
  }
  if (typeof window.MediaRecorder === 'undefined') {
    return {
      title: '浏览器版本过低，不支持网页录音',
      detail: 'iPhone 需要 iOS 14.3 及以上；请升级系统或改用文件上传。',
      link: '',
      linkText: '',
    }
  }
  return { title: '麦克风不可用', detail: '已自动切换为上传音频文件。', link: '', linkText: '' }
})

const classOptions = computed(() => {
  const own = student.value.classes || []
  const all = store.meta.classes || []
  return [...new Set([...own, ...all])]
})
const courseName = computed(() => store.meta.class_course_map?.[className.value] || '')

const filteredTemplates = computed(() => templates.value.filter((t) => t.category === cat.value))

onMounted(async () => {
  canRecord.value = !!(window.isSecureContext && navigator.mediaDevices?.getUserMedia
    && window.MediaRecorder)
  if (!canRecord.value) evalType.value = 'text'
  student.value = await get(`/api/students/${studentId}`)
  className.value = student.value.classes?.[0] || ''
  templates.value = await get('/api/eval-templates')
  const course = student.value.accounts?.[0]?.course_name || ''
  if (course.includes('书法')) cat.value = '书法'
  else if (course.includes('美术') || course.includes('画')) cat.value = '美术'
})

onUnmounted(() => cleanupRec())

function addPhotos(e) {
  const files = Array.from(e.target.files || [])
  for (const f of files) {
    if (photos.value.length >= 3) { toast('最多 3 张照片'); break }
    photos.value.push(f)
    previews.value.push(URL.createObjectURL(f))
  }
  e.target.value = ''
}

function removePhoto(i) {
  URL.revokeObjectURL(previews.value[i])
  photos.value.splice(i, 1)
  previews.value.splice(i, 1)
}

async function startRec() {
  if (recording.value) return
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (e) {
    toast('无法访问麦克风：' + e.message)
    canRecord.value = false
    return
  }
  chunks = []
  const mime = ['audio/webm', 'audio/mp4', 'audio/ogg'].find((m) => MediaRecorder.isTypeSupported?.(m))
  recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
  recorder.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data)
  recorder.onstop = () => {
    const type = recorder.mimeType || 'audio/webm'
    audioBlob.value = new Blob(chunks, { type })
    if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
    audioUrl.value = URL.createObjectURL(audioBlob.value)
    cleanupRec()
  }
  recorder.start()
  recording.value = true
  seconds.value = 0
  timer = setInterval(() => {
    seconds.value += 1
    if (seconds.value >= 120) stopRec()   // 单条最长 2 分钟
  }, 1000)
}

function stopRec() {
  if (!recording.value) return
  recording.value = false
  clearInterval(timer)
  try { recorder && recorder.state !== 'inactive' && recorder.stop() } catch { /* ignore */ }
}

function cleanupRec() {
  clearInterval(timer)
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null }
}

function pickAudio(e) {
  const f = e.target.files?.[0]
  if (!f) return
  audioBlob.value = f
  if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
  audioUrl.value = URL.createObjectURL(f)
}

function applyTemplate(t) {
  evalText.value = evalText.value ? evalText.value + ' ' + t.text : t.text
}

async function submit() {
  if (!photos.value.length && evalType.value === 'none') {
    toast('请至少上传一张照片或填写评价')
    return
  }
  if (evalType.value === 'text' && !evalText.value.trim() && !photos.value.length) {
    toast('请填写评价内容')
    return
  }
  if (evalType.value === 'voice' && !audioBlob.value && !photos.value.length) {
    toast('请先录音或上传音频')
    return
  }

  const fd = new FormData()
  fd.append('student_id', studentId)
  fd.append('class_name', className.value)
  fd.append('course_name', courseName.value)
  fd.append('lesson_date', lessonDate.value)
  fd.append('eval_type', evalType.value)
  fd.append('eval_text', evalType.value === 'text' ? evalText.value : '')
  fd.append('rating', rating.value)
  photos.value.forEach((f) => fd.append('photos', f, f.name || 'photo.jpg'))
  if (evalType.value === 'voice' && audioBlob.value) {
    const ext = (audioBlob.value.type || '').includes('mp4') ? 'm4a'
      : (audioBlob.value.type || '').includes('ogg') ? 'ogg' : 'webm'
    fd.append('audio', audioBlob.value, audioBlob.value.name || `rec.${ext}`)
  }

  submitting.value = true
  try {
    await upload('/api/artworks', fd)
    toast('提交成功')
    router.push('/students/' + studentId)
  } catch (e) {
    toast('提交失败：' + e.message)
  } finally {
    submitting.value = false
  }
}

watch(evalType, (v) => { if (v === 'voice' && !canRecord.value) toast('当前为 HTTP，已切换为上传音频文件') })
</script>

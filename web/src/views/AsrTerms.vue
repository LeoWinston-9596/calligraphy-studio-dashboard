<template>
  <!-- 语音转文字 + 书画术语表 -->
  <div class="card">
    <h3>语音转文字状态</h3>
    <div class="kv">
      <span class="k">可用状态</span>
      <span class="v">
        <span :class="['pill', st.available ? 'green' : 'red']">
          {{ st.available ? '已就绪' : '未就绪' }}
        </span>
      </span>
    </div>
    <div class="kv"><span class="k">识别引擎</span><span class="v">{{ st.engine || '—' }}</span></div>
    <div class="kv">
      <span class="k">语音模型</span>
      <span class="v">
        <span :class="['pill', st.model_installed ? 'green' : 'red']">
          {{ st.model_installed ? (st.model_size / 1048576).toFixed(0) + ' MB 已安装' : '未安装' }}
        </span>
      </span>
    </div>
    <div class="kv"><span class="k">待转写 / 已完成 / 失败</span>
      <span class="v">{{ st.pending }} / {{ st.done }} / {{ st.failed }}</span>
    </div>
    <div class="kv"><span class="k">语音评价总数</span><span class="v">{{ st.total_voice }}</span></div>

    <div v-if="!st.model_installed" class="muted" style="margin-top:10px">
      模型没装，语音评价不会转成文字（其他功能不受影响）。在项目目录执行一次：
      <div style="margin-top:6px"><code>python install_asr.py</code></div>
      约 230MB，只有这一步需要联网，装完之后转写全程离线。装好后重启服务。
    </div>

    <div class="row" style="margin-top:10px">
      <button class="btn ghost sm" :disabled="busy" @click="requeue(true)">重试失败的</button>
      <button class="btn ghost sm" :disabled="busy" @click="requeue(false)">全部重新转写</button>
      <button class="btn ghost sm" @click="load">刷新</button>
    </div>
    <p class="muted" style="margin-top:6px">
      补完术语表后点「全部重新转写」，之前转错的会按新术语表重跑（老师人工校对过的不会被覆盖）。
    </p>
  </div>

  <div class="card">
    <h3>术语纠正试一试</h3>
    <p class="muted">
      语音识别常把专业词写成同音字（提按→提案、皴法→村法）。
      粘一句转写结果进来，看看术语表能不能纠对。
    </p>
    <div class="field">
      <textarea v-model="probe" rows="2" placeholder="例如：这幅画的村法不错藏风起笔要再明显一些"></textarea>
    </div>
    <button class="btn sm" :disabled="!probe.trim()" @click="preview">试一下</button>
    <template v-if="probeResult">
      <div class="kv" style="margin-top:10px"><span class="k">纠正后</span><span class="v">{{ probeResult.output }}</span></div>
      <div class="kv"><span class="k">改了什么</span>
        <span class="v">{{ probeResult.corrections.map(c => c.from + '→' + c.to).join('、') || '没有改动' }}</span>
      </div>
    </template>
  </div>

  <div class="card">
    <h3>添加术语</h3>
    <p class="muted">至少 2 个字。单字太容易误伤，不参与纠正。</p>
    <div class="row">
      <input v-model="draft" placeholder="如：飞白、皴法、中锋" @keyup.enter="add" />
      <button class="btn sm" style="flex:none" :disabled="!draft.trim()" @click="add">添加</button>
    </div>
    <template v-if="suggestions.length">
      <p class="muted" style="margin-top:10px">从评语模板里发现这些词还没加：</p>
      <div class="chips">
        <button v-for="s in suggestions" :key="s" class="chip" @click="draft = s; add()">+ {{ s }}</button>
      </div>
    </template>
  </div>

  <div class="card">
    <h3>术语表（{{ items.length }}）</h3>
    <div class="chips">
      <button v-for="t in items" :key="t.id"
              :class="['chip', { on: t.active }]"
              :title="t.active ? '点击停用' : '点击启用'"
              @click="toggle(t)">
        {{ t.text }}
        <span class="chip-num">{{ t.source }}</span>
      </button>
    </div>
    <p class="muted" style="margin-top:8px">点一下可停用/启用；停用的不参与纠正。</p>
    <div class="row" style="margin-top:8px">
      <select v-model="removeId">
        <option value="">选一个删除…</option>
        <option v-for="t in items" :key="t.id" :value="t.id">{{ t.text }}</option>
      </select>
      <button class="btn ghost sm" style="flex:none" :disabled="!removeId" @click="remove">删除</button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { del, get, patch, post, toast } from '../api'

const st = ref({ pending: 0, done: 0, failed: 0, total_voice: 0 })
const items = ref([])
const suggestions = ref([])
const draft = ref('')
const probe = ref('')
const probeResult = ref(null)
const removeId = ref('')
const busy = ref(false)

async function load() {
  st.value = await get('/api/asr/status')
  const d = await get('/api/asr/terms')
  items.value = d.items
  suggestions.value = d.suggestions
}

async function add() {
  const text = draft.value.trim()
  if (!text) return
  try {
    await post('/api/asr/terms', { text })
    draft.value = ''
    toast('已添加')
    await load()
  } catch (e) { toast(e.message) }
}

async function toggle(t) {
  await patch(`/api/asr/terms/${t.id}`, { active: !t.active })
  await load()
}

async function remove() {
  if (!removeId.value) return
  await del(`/api/asr/terms/${removeId.value}`)
  removeId.value = ''
  toast('已删除')
  await load()
}

async function preview() {
  probeResult.value = await post('/api/asr/terms/preview', { text: probe.value })
}

async function requeue(onlyFailed) {
  busy.value = true
  try {
    const r = await post('/api/asr/requeue', { only_failed: onlyFailed })
    toast(`已排队 ${r.queued} 条`)
    await load()
  } catch (e) { toast(e.message) } finally { busy.value = false }
}

onMounted(load)
</script>

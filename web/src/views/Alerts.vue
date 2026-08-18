<template>
  <!-- 课时提醒看板（规格书 §5.3） -->
  <div class="tabs">
    <button :class="{ on: tab === 'renew' }" @click="switchTab('renew')">续费预警 {{ counts.renew ?? '' }}</button>
    <button :class="{ on: tab === 'expire' }" @click="switchTab('expire')">到期预警 {{ counts.expire ?? '' }}</button>
    <button :class="{ on: tab === 'absent' }" @click="switchTab('absent')">缺课关注 {{ counts.absent ?? '' }}</button>
  </div>

  <p class="muted" style="margin-bottom:10px">
    <template v-if="tab === 'renew'">规则：{{ data.mode === 'imported' ? '导入' : '估算' }}剩余 ≤ {{ data.thresholds?.renew_threshold }} 课时</template>
    <template v-else-if="tab === 'expire'">规则：{{ data.thresholds?.expire_days }} 天内到期</template>
    <template v-else>规则：缺课次数 ≥ {{ data.thresholds?.absent_threshold }}</template>
    · 共 {{ data.count || 0 }} 条 ·
    <RouterLink to="/settings">改阈值</RouterLink>
  </p>

  <div class="search">
    <select v-model="filterStatus">
      <option value="">全部</option>
      <option value="待跟进">待跟进</option>
      <option value="已跟进">已跟进</option>
    </select>
  </div>

  <p v-if="loading" class="muted">加载中…</p>
  <div v-else-if="!shown.length" class="empty">当前没有需要关注的记录 🎉</div>

  <div v-for="i in shown" :key="i.course_account_id" class="card">
    <EditBadge v-if="i.follow_id" :count="i.edit_count" :badge="i.edit_badge"
               :logs-url="`/api/alerts/follow/${i.follow_id}/logs`" />
    <h3>
      <span @click="$router.push('/students/' + i.student_id)" style="cursor:pointer">{{ i.student_name }}</span>
      <span :class="['pill', i.follow_status === '已跟进' ? 'green' : 'red']" style="margin-left:6px">
        {{ i.follow_status }}
      </span>
    </h3>
    <div class="muted" style="margin-bottom:8px">{{ i.course_name }} · {{ i.class_name }}</div>
    <div class="kv"><span class="k">剩余课时</span><span class="v"><BalanceChip :balance="i.balance" :threshold="data.thresholds?.renew_threshold || 3" /></span></div>
    <div class="kv" v-if="tab === 'expire'"><span class="k">到期时间</span><span class="v">{{ i.expire_date }}（{{ i.days_to_expire }} 天后）</span></div>
    <div class="kv" v-if="tab === 'absent'"><span class="k">缺课次数</span><span class="v">{{ i.absent_count }}</span></div>
    <div class="kv"><span class="k">跟进人</span><span class="v">{{ (i.follow_up_persons || []).join('、') || '—' }}</span></div>
    <div class="kv" v-if="i.follow_note"><span class="k">跟进备注</span><span class="v">{{ i.follow_note }}</span></div>
    <div class="kv" v-if="i.follow_updated_at"><span class="k">最近更新</span><span class="v">{{ i.follow_updated_by }} · {{ i.follow_updated_at }}</span></div>

    <div class="row" style="margin-top:10px">
      <button class="btn sm" @click="openFollow(i)">
        {{ i.follow_status === '已跟进' ? '修改跟进' : '标记已跟进' }}
      </button>
      <button class="btn ghost sm" @click="$router.push('/students/' + i.student_id)">查看学员</button>
    </div>
  </div>

  <Sheet v-if="current" title="跟进记录" @close="current = null">
    <div class="field">
      <label>状态</label>
      <select v-model="followForm.status"><option>已跟进</option><option>待跟进</option></select>
    </div>
    <div class="field">
      <label>备注</label>
      <textarea v-model="followForm.note" placeholder="例如：已电话联系家长，本周内续费"></textarea>
    </div>
    <button class="btn block" :disabled="saving" @click="saveFollow">保存</button>
  </Sheet>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { get, post, toast } from '../api'
import BalanceChip from '../components/BalanceChip.vue'
import EditBadge from '../components/EditBadge.vue'
import Sheet from '../components/Sheet.vue'

const tab = ref('renew')
const data = ref({})
const counts = ref({})
const loading = ref(true)
const filterStatus = ref('')
const current = ref(null)
const saving = ref(false)
const followForm = reactive({ status: '已跟进', note: '' })

const shown = computed(() => {
  const items = data.value.items || []
  return filterStatus.value ? items.filter((i) => i.follow_status === filterStatus.value) : items
})

async function load() {
  loading.value = true
  try {
    data.value = await get('/api/alerts', { tab: tab.value })
    counts.value = await get('/api/alerts/counts')
  } finally { loading.value = false }
}

function switchTab(t) { tab.value = t; load() }

function openFollow(i) {
  current.value = i
  followForm.status = i.follow_status === '已跟进' ? '待跟进' : '已跟进'
  followForm.note = i.follow_note || ''
}

async function saveFollow() {
  saving.value = true
  try {
    await post('/api/alerts/follow', {
      course_account_id: current.value.course_account_id,
      alert_type: tab.value,
      status: followForm.status,
      note: followForm.note,
    })
    toast('已保存')
    current.value = null
    await load()
  } catch (e) { toast('保存失败：' + e.message) } finally { saving.value = false }
}

onMounted(load)
</script>

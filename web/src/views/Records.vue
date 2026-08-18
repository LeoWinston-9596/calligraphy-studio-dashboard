<template>
  <!-- 订单 / 收支（规格书 §5.4）：纯只读 -->
  <div class="tabs">
    <button :class="{ on: tab === 'orders' }" @click="switchTab('orders')">订单</button>
    <button :class="{ on: tab === 'transactions' }" @click="switchTab('transactions')">收支明细</button>
  </div>

  <div class="search">
    <input v-model="start" type="date" />
    <input v-model="end" type="date" />
    <input v-model="q" :placeholder="tab === 'orders' ? '姓名/订单号/项目' : '收付款人/项目/经办人'" />
    <button class="btn sm" @click="reload">查询</button>
  </div>

  <div class="card" v-if="data.totals">
    <template v-if="tab === 'orders'">
      <div class="kv"><span class="k">应收/应退合计</span><span class="v">¥{{ money(data.totals.due) }}</span></div>
      <div class="kv"><span class="k">实收/实退合计</span><span class="v">¥{{ money(data.totals.paid) }}</span></div>
      <div class="kv"><span class="k">欠费合计</span><span class="v">¥{{ money(data.totals.owed) }}</span></div>
    </template>
    <template v-else>
      <div class="kv"><span class="k">收入合计</span><span class="v">¥{{ money(data.totals.income) }}</span></div>
      <div class="kv"><span class="k">支出合计</span><span class="v">¥{{ money(data.totals.expense) }}</span></div>
      <div class="kv"><span class="k">净额</span><span class="v">¥{{ money(data.totals.net) }}</span></div>
    </template>
    <div class="kv"><span class="k">记录数</span><span class="v">{{ data.total }}</span></div>
  </div>

  <p v-if="loading" class="muted">加载中…</p>
  <div v-else-if="!data.items?.length" class="empty">没有匹配的记录</div>

  <div v-else class="table-wrap">
    <table v-if="tab === 'orders'">
      <thead><tr>
        <th>创建时间</th><th>学生</th><th>订单类型</th><th>购买项目</th>
        <th>应收/应退</th><th>实收/实退</th><th>欠费</th><th>状态</th><th>经办人</th>
      </tr></thead>
      <tbody>
        <tr v-for="o in data.items" :key="o.id">
          <td>{{ o.created_time }}</td><td>{{ o.student_name }}</td><td>{{ o.order_type }}</td>
          <td style="white-space:normal;min-width:220px">{{ o.purchase_item }}</td>
          <td>{{ money(o.due_amount) }}</td><td>{{ money(o.paid_amount) }}</td>
          <td>{{ money(o.owed_amount) }}</td><td>{{ o.order_status }}</td><td>{{ o.operator }}</td>
        </tr>
      </tbody>
      <tfoot><tr>
        <td colspan="4">本页合计（全部筛选结果）</td>
        <td>{{ money(data.totals.due) }}</td><td>{{ money(data.totals.paid) }}</td>
        <td>{{ money(data.totals.owed) }}</td><td colspan="2"></td>
      </tr></tfoot>
    </table>

    <table v-else>
      <thead><tr>
        <th>创建时间</th><th>收支项目</th><th>类型</th><th>金额</th>
        <th>支付方式</th><th>收付款人</th><th>经办人</th><th>关联订单号</th><th>校区</th>
      </tr></thead>
      <tbody>
        <tr v-for="t in data.items" :key="t.id">
          <td>{{ t.created_time }}</td><td>{{ t.item }}</td>
          <td><span :class="['pill', t.io_type === '收入' ? 'green' : 'red']">{{ t.io_type }}</span></td>
          <td>{{ money(t.amount) }}</td><td>{{ t.pay_method }}</td><td>{{ t.payer }}</td>
          <td>{{ t.operator }}</td><td>{{ t.related_order_no }}</td><td>{{ t.campus }}</td>
        </tr>
      </tbody>
      <tfoot><tr>
        <td colspan="3">合计（全部筛选结果）</td>
        <td>收 {{ money(data.totals.income) }} / 支 {{ money(data.totals.expense) }}</td>
        <td colspan="5">净额 {{ money(data.totals.net) }}</td>
      </tr></tfoot>
    </table>
  </div>

  <div v-if="data.items?.length && data.items.length < data.total" class="center" style="margin-top:12px">
    <button class="btn ghost" @click="more">加载更多（已显示 {{ data.items.length }} / {{ data.total }}）</button>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { get } from '../api'

const tab = ref('orders')
const start = ref('')
const end = ref('')
const q = ref('')
const page = ref(1)
const data = ref({})
const loading = ref(false)

function money(v) { return (Number(v) || 0).toFixed(2) }

async function load(append = false) {
  loading.value = true
  try {
    const url = tab.value === 'orders' ? '/api/orders' : '/api/transactions'
    const d = await get(url, { start: start.value, end: end.value, q: q.value, page: page.value, page_size: 50 })
    if (append) d.items = [...data.value.items, ...d.items]
    data.value = d
  } finally { loading.value = false }
}

function reload() { page.value = 1; load(false) }
function more() { page.value += 1; load(true) }
function switchTab(t) { tab.value = t; q.value = ''; reload() }

onMounted(() => load())
</script>

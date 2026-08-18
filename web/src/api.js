import { reactive } from 'vue'

// 全局状态：当前用户、元数据（顶栏截止时间、备份状态、筛选项）
export const store = reactive({
  user: null,
  meta: {
    asof: {}, backup: {}, classes: [], courses: [], follow_up_persons: [],
    class_course_map: {}, my_classes: [], teacher_names: [], permissions: {},
  },
  toast: '',
})

let toastTimer = null
export function toast(msg, ms = 2400) {
  store.toast = msg
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (store.toast = ''), ms)
}

async function handle(res) {
  if (res.status === 401) {
    store.user = null
    throw new Error('未登录')
  }
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    const msg = (data && data.detail) || `请求失败（${res.status}）`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export async function get(url, params) {
  const q = params ? '?' + new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined)
  ) : ''
  return handle(await fetch(url + q, { credentials: 'same-origin' }))
}

export async function post(url, body) {
  return handle(await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify(body || {}),
  }))
}

export async function patch(url, body) {
  return handle(await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify(body || {}),
  }))
}

export async function del(url) {
  return handle(await fetch(url, { method: 'DELETE', credentials: 'same-origin' }))
}

export async function upload(url, formData, method = 'POST') {
  return handle(await fetch(url, { method, credentials: 'same-origin', body: formData }))
}

export async function refreshMeta() {
  try { store.meta = await get('/api/meta') } catch { /* 未登录时忽略 */ }
}

export function todayStr() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

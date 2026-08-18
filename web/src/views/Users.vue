<template>
  <!-- 用户管理：账号操作按角色分级；业务数据仍是所有人可看可改 -->
  <div v-if="!perms.can_create_user" class="card">
    <p class="muted" style="margin:0">
      当前账号为<strong>{{ store.user.role_label }}</strong>，只能查看账号列表。
      新增账号请联系教务或校长。
    </p>
  </div>

  <div v-else class="card">
    <h3>新增账号</h3>
    <div class="row">
      <div class="field"><label>用户名（登录用）</label><input v-model="form.username" autocapitalize="off" /></div>
      <div class="field">
        <label>姓名</label>
        <input v-model="form.name" placeholder="如：张老师" @blur="autoMatch" />
      </div>
    </div>
    <div class="row">
      <div class="field"><label>密码（至少 6 位）</label><input v-model="form.password" type="password" /></div>
      <div class="field">
        <label>角色</label>
        <select v-model="form.role_label">
          <option v-for="r in perms.creatable_roles" :key="r" :value="r">{{ r }}</option>
        </select>
        <p class="muted" style="margin-top:4px">{{ store.user.role_label }}只能创建 {{ perms.creatable_roles.join('、') }}</p>
      </div>
    </div>

    <div class="field">
      <label>班级归属</label>
      <div class="tabs">
        <button :class="{ on: form.auto_bind_classes }" @click="form.auto_bind_classes = true">
          自动跟随导入表格（推荐）
        </button>
        <button :class="{ on: !form.auto_bind_classes }" @click="form.auto_bind_classes = false">
          手动勾选
        </button>
      </div>

      <template v-if="form.auto_bind_classes">
        <div class="field">
          <label>对应导入表里的老师身份（「跟进人」列，可多选）</label>
          <div class="chips">
            <button v-for="t in teachers" :key="t.name"
                    :class="['chip', { on: form.teacher_names.includes(t.name) }]"
                    @click="toggleIdentity(form, t.name)">
              {{ t.name }}
              <span class="chip-num">{{ t.class_count }}班 · {{ t.student_count }}人</span>
            </button>
          </div>
        </div>
        <p class="muted">
          <template v-if="matchedClasses.length">
            ✅ 已勾 {{ form.teacher_names.length }} 个身份，共 <strong>{{ matchedClasses.length }}</strong> 个班：
            {{ matchedClasses.slice(0, 4).join('、') }}<span v-if="matchedClasses.length > 4"> 等</span>。
            以后在教务 App 新开的班，只要跟进人还是 TA，导入后会自动出现，不用回来手选。
          </template>
          <template v-else>
            填完姓名会自动勾选匹配的身份；没勾中就手动点上面的名字。
          </template>
        </p>
      </template>

      <template v-else>
        <select multiple v-model="form.class_bindings" style="min-height:130px">
          <option v-for="c in store.meta.classes" :key="c" :value="c">{{ c }}</option>
        </select>
        <p class="muted" style="margin-top:4px">手动模式下，新导入的班级不会自动归属，需要回来补选。</p>
      </template>
    </div>

    <button class="btn" :disabled="busy" @click="add">创建账号</button>
  </div>

  <div v-for="u in users" :key="u.id" class="card">
    <h3>
      {{ u.name }} <span class="pill gray">{{ u.role_label }}</span>
      <span v-if="!u.active" class="pill red">已停用</span>
    </h3>
    <div class="kv"><span class="k">用户名</span><span class="v">{{ u.username }}</span></div>
    <div class="kv">
      <span class="k">班级归属</span>
      <span class="v">
        <span :class="['pill', u.auto_bind_classes ? 'green' : 'gray']">
          {{ u.auto_bind_classes ? '自动跟随' : '手动' }}
        </span>
        {{ u.effective_classes.length }} 个班
        <span v-if="u.auto_bind_classes && u.teacher_names?.length" class="muted">
          （身份：{{ u.teacher_names.join('、') }}）
        </span>
      </span>
    </div>
    <div class="kv" v-if="u.effective_classes.length">
      <span class="k">班级</span>
      <span class="v" style="font-size:12px">{{ u.effective_classes.slice(0, 6).join('、') }}<span v-if="u.effective_classes.length > 6"> 等 {{ u.effective_classes.length }} 个</span></span>
    </div>
    <div class="row" style="margin-top:10px">
      <button v-if="u.can_edit" class="btn ghost sm" @click="startEdit(u)">编辑</button>
      <button v-if="u.can_toggle_active" class="btn ghost sm" @click="toggle(u)">
        {{ u.active ? '停用' : '启用' }}
      </button>
      <span v-if="!u.can_edit && !u.can_toggle_active" class="muted" style="font-size:12px">
        无权修改（{{ store.user.role_label }} 不能操作 {{ u.role_label }}）
      </span>
    </div>
  </div>

  <Sheet v-if="editing" :title="'编辑 ' + editing.name" @close="editing = null">
    <div class="field"><label>姓名</label><input v-model="edit.name" /></div>
    <div class="field" v-if="perms.creatable_roles.length">
      <label>角色</label>
      <select v-model="edit.role_label">
        <option v-for="r in perms.creatable_roles" :key="r" :value="r">{{ r }}</option>
      </select>
    </div>

    <div class="field">
      <label>班级归属</label>
      <div class="tabs">
        <button :class="{ on: edit.auto_bind_classes }" @click="edit.auto_bind_classes = true">自动跟随导入表格</button>
        <button :class="{ on: !edit.auto_bind_classes }" @click="edit.auto_bind_classes = false">手动勾选</button>
      </div>
      <template v-if="edit.auto_bind_classes">
        <div class="chips">
          <button v-for="t in teachers" :key="t.name"
                  :class="['chip', { on: edit.teacher_names.includes(t.name) }]"
                  @click="toggleIdentity(edit, t.name)">
            {{ t.name }}<span class="chip-num">{{ t.class_count }}班</span>
          </button>
        </div>
      </template>
      <template v-else>
        <select multiple v-model="edit.class_bindings" style="min-height:150px">
          <option v-for="c in store.meta.classes" :key="c" :value="c">{{ c }}</option>
        </select>
      </template>
    </div>

    <div class="field"><label>重置密码（留空则不改）</label><input v-model="edit.password" type="password" /></div>
    <button class="btn block" :disabled="busy" @click="save">保存</button>
  </Sheet>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { get, patch, post, refreshMeta, store, toast } from '../api'
import Sheet from '../components/Sheet.vue'

const users = ref([])
const teachers = ref([])
const perms = ref({ can_create_user: false, creatable_roles: [] })
const busy = ref(false)
const editing = ref(null)
const form = reactive({
  username: '', name: '', password: '', role_label: '老师',
  class_bindings: [], auto_bind_classes: true, teacher_names: [],
})
const edit = reactive({
  name: '', role_label: '老师', class_bindings: [],
  auto_bind_classes: true, teacher_names: [], password: '',
})

// 多个身份的班级取并集
const matchedClasses = computed(() => {
  const all = new Set()
  for (const name of form.teacher_names) {
    const t = teachers.value.find((x) => x.name === name)
    if (t) t.classes.forEach((c) => all.add(c))
  }
  return [...all]
})

function toggleIdentity(target, name) {
  const i = target.teacher_names.indexOf(name)
  if (i >= 0) target.teacher_names.splice(i, 1)
  else target.teacher_names.push(name)
}

async function load() {
  const d = await get('/api/users')
  users.value = d.items
  perms.value = d.permissions
  if (perms.value.creatable_roles.length && !perms.value.creatable_roles.includes(form.role_label)) {
    form.role_label = perms.value.creatable_roles[perms.value.creatable_roles.length - 1]
  }
  teachers.value = await get('/api/users/teachers')
}

// 输入姓名后自动勾选对应的老师身份（可能不止一个）
async function autoMatch() {
  if (!form.name.trim() || form.teacher_names.length) return
  const r = await get('/api/users/match-teacher', { name: form.name })
  if (r.matched?.length) {
    form.teacher_names = [...r.matched]
    toast(`已自动勾选「${r.matched.join('、')}」，共 ${r.classes.length} 个班`)
  }
}

async function add() {
  busy.value = true
  try {
    await post('/api/users', { ...form })
    Object.assign(form, {
      username: '', name: '', password: '', role_label: perms.value.creatable_roles.slice(-1)[0] || '老师',
      class_bindings: [], auto_bind_classes: true, teacher_names: [],
    })
    toast('账号已创建')
    await load()
  } catch (e) { toast(e.message) } finally { busy.value = false }
}

function startEdit(u) {
  editing.value = u
  Object.assign(edit, {
    name: u.name, role_label: u.role_label, class_bindings: [...u.class_bindings],
    auto_bind_classes: u.auto_bind_classes, teacher_names: [...(u.teacher_names || [])],
    password: '',
  })
}

async function save() {
  busy.value = true
  try {
    const body = {
      name: edit.name, class_bindings: edit.class_bindings,
      auto_bind_classes: edit.auto_bind_classes, teacher_names: edit.teacher_names,
    }
    if (perms.value.creatable_roles.includes(edit.role_label)) body.role_label = edit.role_label
    if (edit.password) body.password = edit.password
    await patch(`/api/users/${editing.value.id}`, body)
    editing.value = null
    toast('已保存')
    await load()
    await refreshMeta()
  } catch (e) { toast(e.message) } finally { busy.value = false }
}

async function toggle(u) {
  try {
    await patch(`/api/users/${u.id}`, { active: !u.active })
    await load()
  } catch (e) { toast(e.message) }
}

onMounted(load)
</script>

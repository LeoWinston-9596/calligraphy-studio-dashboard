import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

import Workbench from './views/Workbench.vue'
import ClassView from './views/ClassView.vue'
import UploadView from './views/UploadView.vue'
import Students from './views/Students.vue'
import StudentDetail from './views/StudentDetail.vue'
import Alerts from './views/Alerts.vue'
import Records from './views/Records.vue'
import Settings from './views/Settings.vue'
import ImportView from './views/ImportView.vue'
import Templates from './views/Templates.vue'
import AsrTerms from './views/AsrTerms.vue'
import Users from './views/Users.vue'

const routes = [
  { path: '/', redirect: '/workbench' },
  { path: '/workbench', component: Workbench, meta: { title: '工作台', tab: 'workbench' } },
  { path: '/class/:name', component: ClassView, meta: { title: '班级学员', tab: 'workbench' } },
  { path: '/upload/:studentId', component: UploadView, meta: { title: '上传作品', tab: 'workbench' } },
  { path: '/students', component: Students, meta: { title: '学员看板', tab: 'students' } },
  { path: '/students/:id', component: StudentDetail, meta: { title: '学员详情', tab: 'students' } },
  { path: '/alerts', component: Alerts, meta: { title: '课时提醒', tab: 'alerts' } },
  { path: '/records', component: Records, meta: { title: '订单收支', tab: 'more' } },
  { path: '/import', component: ImportView, meta: { title: '数据导入', tab: 'more' } },
  { path: '/templates', component: Templates, meta: { title: '评语模板', tab: 'more' } },
  { path: '/asr', component: AsrTerms, meta: { title: '语音转文字', tab: 'more' } },
  { path: '/users', component: Users, meta: { title: '用户管理', tab: 'more' } },
  { path: '/settings', component: Settings, meta: { title: '设置', tab: 'more' } },
]

const router = createRouter({ history: createWebHistory(), routes })

createApp(App).use(router).mount('#app')

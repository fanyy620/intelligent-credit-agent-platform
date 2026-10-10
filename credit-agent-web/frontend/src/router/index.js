import Vue from 'vue'
import VueRouter from 'vue-router'
import store from '@/store'

Vue.use(VueRouter)

const routes = [
  {
    path: '/login',
    component: () => import('@/views/login/Login.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/',
    component: () => import('@/layout/Layout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        component: () => import('@/views/dashboard/Dashboard.vue'),
        meta: { title: '首页看板', icon: 'el-icon-data-analysis' }
      },
      {
        path: 'chat',
        component: () => import('@/views/chat/ChatPanel.vue'),
        meta: { title: '对公智能顾问', icon: 'el-icon-chat-dot-round' }
      },
      {
        path: 'customer',
        component: () => import('@/views/customer/CustomerList.vue'),
        meta: { title: '企业客户', icon: 'el-icon-office-building' }
      },
      {
        path: 'product',
        component: () => import('@/views/product/ProductList.vue'),
        meta: { title: '信贷产品', icon: 'el-icon-goods' }
      },
      {
        path: 'recommend',
        component: () => import('@/views/recommend/RecommendRecords.vue'),
        meta: { title: '推荐记录', icon: 'el-icon-tickets' }
      },
      {
        path: 'copy',
        component: () => import('@/views/copy/CopyRecords.vue'),
        meta: { title: '文案与合规', icon: 'el-icon-document-checked' }
      },
      {
        path: 'profile',
        component: () => import('@/views/profile/Profile.vue'),
        meta: { title: '个人中心', icon: 'el-icon-postcard' }
      }
    ]
  },
  { path: '*', redirect: '/' }
]

const router = new VueRouter({
  mode: 'hash',
  routes
})

// 登录守卫：无令牌一律去登录页
router.beforeEach((to, from, next) => {
  document.title = (to.meta.title ? to.meta.title + ' · ' : '') + '南洋商业银行 · 智能信贷服务平台'
  if (!store.state.token && to.path !== '/login') {
    next('/login')
  } else if (store.state.token && to.path === '/login') {
    next('/')
  } else {
    next()
  }
})

export default router

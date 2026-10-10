<template>
  <el-container style="height: 100%">
    <!-- 深色侧边栏 -->
    <el-aside :width="collapsed ? '64px' : '210px'" class="layout-aside">
      <div class="layout-logo">
        <span class="ncb-mark"><i>南</i></span>
        <span v-show="!collapsed" class="ncb-logo-text">
          <span class="ncb-logo-name ncb-serif">南洋商业银行</span>
          <span class="ncb-logo-sub">NANYANG COMMERCIAL BANK</span>
        </span>
      </div>
      <el-menu
        :default-active="$route.path"
        :collapse="collapsed"
        background-color="transparent"
        text-color="rgba(255,255,255,0.72)"
        active-text-color="#ffffff"
        router
      >
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <i :class="item.icon"></i>
          <span slot="title">{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶栏 -->
      <el-header class="layout-header" height="60px">
        <div>
          <i
            :class="collapsed ? 'el-icon-s-unfold' : 'el-icon-s-fold'"
            style="font-size: 18px; cursor: pointer; margin-right: 14px"
            @click="collapsed = !collapsed"
          ></i>
          <span style="font-size: 15px; color: #1f2d3d">{{ $route.meta.title || '首页' }}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 16px">
          <el-tooltip :content="agentAvailable ? 'Python 智能助理服务在线' : '智能助理服务离线（降级运行）'">
            <el-tag :type="agentAvailable ? 'success' : 'danger'" size="mini" effect="dark">
              Agent {{ agentAvailable ? '在线' : '离线' }}
            </el-tag>
          </el-tooltip>
          <el-dropdown @command="handleCommand">
            <span style="cursor: pointer; color: #1f2d3d">
              <i class="el-icon-user-solid"></i>
              {{ nickname }}
              <i class="el-icon-arrow-down el-icon--right"></i>
            </span>
            <el-dropdown-menu slot="dropdown">
              <el-dropdown-item command="profile">个人中心</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>

    <!-- 全站悬浮智能助手（Copilot） -->
    <floating-agent />
  </el-container>
</template>

<script>
import { logout, dashboardStats } from '@/api'
import FloatingAgent from '@/components/FloatingAgent.vue'

export default {
  name: 'Layout',
  components: { FloatingAgent },
  data() {
    return {
      collapsed: false,
      menus: [
        { path: '/dashboard', title: '首页看板', icon: 'el-icon-data-analysis' },
        { path: '/chat', title: '对公智能顾问', icon: 'el-icon-chat-dot-round' },
        { path: '/customer', title: '企业客户', icon: 'el-icon-office-building' },
        { path: '/product', title: '信贷产品', icon: 'el-icon-goods' },
        { path: '/recommend', title: '推荐记录', icon: 'el-icon-tickets' },
        { path: '/copy', title: '文案与合规', icon: 'el-icon-document-checked' },
        { path: '/profile', title: '个人中心', icon: 'el-icon-postcard' }
      ]
    }
  },
  computed: {
    nickname() {
      return this.$store.getters.nickname || '用户'
    },
    agentAvailable() {
      return this.$store.state.agentAvailable
    }
  },
  created() {
    this.refreshAgentStatus()
  },
  methods: {
    async refreshAgentStatus() {
      try {
        const res = await dashboardStats()
        this.$store.dispatch('setAgentStatus', !!(res.data && res.data.agentAvailable))
      } catch (e) {
        // 后端未就绪时保持默认状态，不做强提示
      }
    },
    async handleCommand(cmd) {
      if (cmd === 'logout') {
        try {
          await logout()
        } catch (e) {
          // 注销失败也强制清本地登录态
        }
        this.$store.dispatch('resetLogin')
        this.$router.replace('/login')
      } else if (cmd === 'profile') {
        this.$router.push('/profile')
      }
    }
  }
}
</script>

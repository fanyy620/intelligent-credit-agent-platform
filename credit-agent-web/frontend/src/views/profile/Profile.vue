<template>
  <div>
    <el-row :gutter="16">
      <!-- 个人信息卡片 -->
      <el-col :span="10">
        <div class="page-card">
          <h3 class="page-title">个人信息</h3>
          <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 18px">
            <div class="layout-logo" style="width: 64px; height: 64px; border-radius: 50%;
                 background: linear-gradient(135deg, #e30000, #2b1665); font-size: 26px">
              {{ avatarText }}
            </div>
            <div>
              <div style="font-size: 18px; font-weight: 600">{{ user.nickname || user.username }}</div>
              <el-tag size="mini" :type="isAdmin ? 'primary' : 'success'" style="margin-top: 6px">
                {{ user.roleName || '客户经理' }}
              </el-tag>
            </div>
          </div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="登录账号">{{ user.username }}</el-descriptions-item>
            <el-descriptions-item label="姓名">{{ user.nickname }}</el-descriptions-item>
            <el-descriptions-item label="角色">{{ user.roleName }}（{{ user.roleKey }}）</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>

      <!-- 权限与系统信息 -->
      <el-col :span="14">
        <div class="page-card">
          <h3 class="page-title">角色权限</h3>
          <el-table :data="permissions" size="small" border>
            <el-table-column prop="module" label="功能模块" width="160" />
            <el-table-column label="权限">
              <template slot-scope="{ row }">
                <el-tag v-for="p in row.perms" :key="p" size="mini"
                        :type="p.includes('管理') && !isAdmin ? 'info' : 'success'"
                        style="margin-right: 6px">
                  {{ p }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="page-card">
          <h3 class="page-title">系统组成</h3>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="前端">Vue 2 + Element UI + Vite（当前页面）</el-descriptions-item>
            <el-descriptions-item label="业务后端">SSM（Spring 5.3 + SpringMVC + MyBatis 3.5，XML 配置版）+ MySQL + Druid + Jedis</el-descriptions-item>
            <el-descriptions-item label="智能引擎">Python Agent（credit-agent-platform · src/api_server.py，端口 8000）</el-descriptions-item>
            <el-descriptions-item label="缓存/会话">Redis（登录令牌、产品缓存、对话上下文）</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script>
import { getInfo } from '@/api'

export default {
  name: 'ProfilePage',
  data() {
    return {
      user: {},
      permissions: [
        { module: '首页看板', perms: ['查看'] },
        { module: '智能助理', perms: ['对话', '推荐'] },
        { module: '客户管理', perms: ['查看', '新增', '编辑', '删除'] },
        { module: '产品管理', perms: ['查看', '管理'] },
        { module: '推荐记录', perms: ['查看'] },
        { module: '文案与合规', perms: ['生成', '查看', '仅看违规'] }
      ]
    }
  },
  computed: {
    isAdmin() {
      return this.$store.getters.isAdmin
    },
    avatarText() {
      const name = this.user.nickname || this.user.username || '用'
      return String(name).charAt(0)
    }
  },
  created() {
    this.user = this.$store.state.userInfo || {}
    this.refresh()
  },
  methods: {
    async refresh() {
      try {
        const res = await getInfo()
        this.user = res.data || {}
        this.$store.commit('SET_USER', this.user)
      } catch (e) { /* 拦截器已提示 */ }
    }
  }
}
</script>

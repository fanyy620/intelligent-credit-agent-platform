<template>
  <div>
    <!-- Agent 离线提示 -->
    <el-alert
      v-if="stats && !stats.agentAvailable"
      type="warning"
      title="智能引擎（Python Agent）当前离线，智能顾问与文案功能降级运行，其余功能不受影响。"
      :closable="false"
      style="margin-bottom: 16px"
      show-icon
    />

    <!-- 统计卡片 -->
    <el-row :gutter="16">
      <el-col :span="6">
        <div class="stat-card" style="background: linear-gradient(135deg, #e30000, #f23a3a)">
          <div class="stat-label">今日企业授信咨询</div>
          <div class="stat-value">{{ stats.todayChatCount || 0 }}</div>
          <i class="el-icon-chat-dot-round stat-icon"></i>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" style="background: linear-gradient(135deg, #2b1665, #4a2e8f)">
          <div class="stat-label">今日授信推荐</div>
          <div class="stat-value">{{ stats.todayRecommendCount || 0 }}</div>
          <i class="el-icon-position stat-icon"></i>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" style="background: linear-gradient(135deg, #6e1030, #9e1b47)">
          <div class="stat-label">文案合规通过率</div>
          <div class="stat-value">{{ passRateText }}</div>
          <i class="el-icon-circle-check stat-icon"></i>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" style="background: linear-gradient(135deg, #333a4d, #4d5872)">
          <div class="stat-label">在册企业客户</div>
          <div class="stat-value">{{ stats.customerCount || 0 }}</div>
          <i class="el-icon-office-building stat-icon"></i>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <!-- 意图分布 -->
      <el-col :span="12">
        <div class="page-card">
          <h3 class="page-title">企业咨询意图分布</h3>
          <div v-if="intentList.length === 0" style="color: #a0aabb; font-size: 13px">
            暂无咨询数据，去「对公智能顾问」发起一轮企业授信咨询试试
          </div>
          <div v-for="item in intentList" :key="item.intent" class="bar-row">
            <span class="bar-label">{{ item.intent_zh || item.intent }}</span>
            <div class="bar-track">
              <div class="bar-fill" :style="{ width: barWidth(item.cnt) }"></div>
            </div>
            <span class="bar-value">{{ item.cnt }} 次</span>
          </div>
        </div>
      </el-col>
      <!-- 平台能力说明 -->
      <el-col :span="12">
        <div class="page-card">
          <h3 class="page-title">平台能力</h3>
          <el-timeline style="padding-left: 4px">
            <el-timeline-item type="primary" timestamp="三层推荐架构">
              槽位抽取 → 规则+RAG 召回 → 业务评分重排（额度/利率/期限/审批速度四维加权）
            </el-timeline-item>
            <el-timeline-item type="success" timestamp="分层记忆">
              Redis 短期会话记忆 + PGVector 长期事实记忆，跨会话留存企业画像
            </el-timeline-item>
            <el-timeline-item type="warning" timestamp="双重风控文案">
              正则违规词库 + 语义审核双闸拦截；模板填充机制杜绝数值幻觉
            </el-timeline-item>
            <el-timeline-item type="info" timestamp="全链路可观测">
              Langfuse trace：意图识别、记忆检索、工具调用、LLM 推理时延与 Token
            </el-timeline-item>
          </el-timeline>
          <div style="font-size: 13px; color: #8a97a8">
            累计咨询会话 {{ stats.sessionCount || 0 }} 个 · 文案 {{ complianceTotal }} 篇
            （通过 {{ compliancePassed }} 篇）
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script>
import { dashboardStats } from '@/api'

export default {
  name: 'DashboardPage',
  data() {
    return {
      stats: {}
    }
  },
  computed: {
    passRateText() {
      const c = this.stats.compliance
      if (!c) return '—'
      return (c.passRate * 100).toFixed(1) + '%'
    },
    complianceTotal() {
      return this.stats.compliance ? this.stats.compliance.total : 0
    },
    compliancePassed() {
      return this.stats.compliance ? this.stats.compliance.passed : 0
    },
    intentList() {
      return this.stats.intentDistribution || []
    },
    maxIntentCnt() {
      return this.intentList.reduce((m, i) => Math.max(m, Number(i.cnt) || 0), 1)
    }
  },
  created() {
    this.load()
  },
  methods: {
    async load() {
      try {
        const res = await dashboardStats()
        this.stats = res.data || {}
        this.$store.dispatch('setAgentStatus', !!this.stats.agentAvailable)
      } catch (e) {
        // 拦截器已提示
      }
    },
    barWidth(cnt) {
      return Math.max(4, Math.round((Number(cnt) / this.maxIntentCnt) * 100)) + '%'
    }
  }
}
</script>

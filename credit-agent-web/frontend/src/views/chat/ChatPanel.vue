<template>
  <div class="chat-page">
    <!-- 左：会话列表 -->
    <div class="chat-sessions">
      <div style="padding: 12px; border-bottom: 1px solid #f0f2f5">
        <el-button type="primary" size="mini" icon="el-icon-plus" style="width: 100%"
                   @click="newSession">
          新建会话
        </el-button>
      </div>
      <div style="flex: 1; overflow-y: auto">
        <div
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: currentSessionId === s.id }"
          @click="openSession(s)"
        >
          <div class="session-title">{{ s.title || '未命名会话' }}</div>
          <div class="session-time">
            {{ s.customerName || '未关联企业' }} · {{ formatTime(s.updateTime) }}
          </div>
        </div>
        <div v-if="sessions.length === 0" style="padding: 20px; color: #a0aabb; font-size: 12px">
          暂无会话，点击上方按钮开始
        </div>
      </div>
    </div>

    <!-- 中：聊天窗 -->
    <div class="chat-main">
      <div style="padding: 10px 16px; border-bottom: 1px solid #eef1f6; display: flex; align-items: center; gap: 10px">
        <span style="font-size: 14px; font-weight: 600">对公智能顾问</span>
        <el-select v-model="currentCustomerId" size="mini" placeholder="关联企业（可选）"
                   clearable filterable style="width: 220px">
          <el-option v-for="c in customers" :key="c.id" :label="c.name + '（' + (c.occupation || '未知行业') + '）'"
                     :value="c.id" />
        </el-select>
        <el-tag v-if="!agentAvailable" type="danger" size="mini">智能引擎离线·降级回复</el-tag>
      </div>

      <div ref="messages" class="chat-messages">
        <div v-for="(m, idx) in messages" :key="idx" class="msg-row" :class="m.role">
          <div>
            <div class="msg-bubble">{{ m.content }}</div>
            <div v-if="m.intentZh" class="msg-intent" :style="m.role === 'user' ? 'text-align:right' : ''">
              意图：{{ m.intentZh }}（{{ m.intent }}）
            </div>
          </div>
        </div>
        <div v-if="sending" class="msg-row assistant">
          <div class="msg-bubble" style="color: #a0aabb">正在思考…</div>
        </div>
      </div>

      <div class="chat-input">
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="输入企业融资诉求，如：我们是制造业企业，需要200万流动资金贷款，期限12个月，请帮我推荐合适的信贷产品"
          @keydown.enter.native.exact.prevent="send"
        />
        <div style="display: flex; justify-content: space-between; margin-top: 8px">
          <span style="color: #a0aabb; font-size: 12px">Enter 发送 / Shift+Enter 换行</span>
          <el-button type="primary" size="small" :loading="sending" @click="send">
            发送 <i class="el-icon-s-promotion el-icon--right"></i>
          </el-button>
        </div>
      </div>
    </div>

    <!-- 右：推荐与合规面板 -->
    <div class="chat-side">
      <h3 class="page-title">授信推荐方案</h3>
      <div v-if="recommendations.length === 0" style="color: #a0aabb; font-size: 13px">
        触发「授信推荐」意图后，这里展示三层推荐架构的评分结果。
      </div>
      <div v-for="(r, i) in recommendations" :key="i" class="rec-card">
        <div class="rec-head">
          <span class="rec-name">Top{{ i + 1 }} {{ r.product.name }}</span>
          <el-tag size="mini" :type="i === 0 ? 'primary' : 'info'">{{ r.product.category }}</el-tag>
        </div>
        <div style="font-size: 12px; color: #5a6a7a; margin-bottom: 8px">
          {{ r.product.rate_range_pct }} · 最高{{ r.product.max_amount / 10000 }}万 ·
          最快{{ r.product.approval_hours }}小时
        </div>
        <div v-for="dim in dims" :key="dim.key" class="score-row">
          <span class="score-label">{{ dim.label }}</span>
          <div class="bar-track">
            <div class="bar-fill" :style="{ width: Math.round(r.scores[dim.key] * 100) + '%' }"></div>
          </div>
          <span class="bar-value">{{ r.scores[dim.key].toFixed(2) }}</span>
        </div>
        <div class="score-row" style="margin-top: 8px">
          <span class="score-label" style="font-weight: 600">综合分</span>
          <div class="bar-track">
            <div class="bar-fill" style="background: linear-gradient(90deg,#e30000,#f26b6b)"
                 :style="{ width: Math.round(r.scores.final_score * 100) + '%' }"></div>
          </div>
          <span class="bar-value" style="font-weight: 600">{{ r.scores.final_score.toFixed(3) }}</span>
        </div>
        <div v-if="r.reason" style="font-size: 12px; color: #8a97a8; margin-top: 6px">
          推荐理由：{{ r.reason }}
        </div>
      </div>

      <h3 class="page-title" style="margin-top: 16px">合规状态</h3>
      <div v-if="!compliance" style="color: #a0aabb; font-size: 13px">每轮回复均经过双重风控审核</div>
      <template v-else>
        <el-tag :type="compliance.blocked ? 'danger' : 'success'" size="small">
          {{ compliance.blocked ? '已拦截违规内容' : '审核通过' }}
        </el-tag>
        <div v-if="compliance.blocked" style="margin-top: 8px">
          <div v-for="(h, i) in compliance.regex_hits" :key="i" class="violation-text" style="margin-bottom: 6px">
            命中「{{ h.rule_name }}」：{{ h.matched }}
          </div>
        </div>
      </template>

      <h3 class="page-title" style="margin-top: 16px">企业画像记忆</h3>
      <div v-if="!memoryUsed" style="color: #a0aabb; font-size: 13px">展示分层记忆的读取情况</div>
      <div v-else style="font-size: 12px; color: #5a6a7a; line-height: 1.9">
        <div>短期会话：{{ memoryUsed.history_len }} 条</div>
        <div v-for="(v, k) in memoryUsed.facts" :key="k">{{ k }}：{{ v }}</div>
      </div>
    </div>
  </div>
</template>

<script>
import { chatSend, chatSessions, chatMessages, customerPage } from '@/api'

export default {
  name: 'ChatPanel',
  data() {
    return {
      sessions: [],
      currentSessionId: null,
      currentCustomerId: null,
      customers: [],
      messages: [],
      input: '',
      sending: false,
      recommendations: [],
      compliance: null,
      memoryUsed: null,
      dims: [
        { key: 'amount_score', label: '额度匹配' },
        { key: 'rate_score', label: '利率优惠' },
        { key: 'term_score', label: '期限灵活' },
        { key: 'speed_score', label: '审批速度' }
      ]
    }
  },
  computed: {
    agentAvailable() {
      return this.$store.state.agentAvailable
    }
  },
  created() {
    this.loadSessions()
    this.loadCustomers()
  },
  methods: {
    async loadSessions() {
      try {
        const res = await chatSessions({ limit: 50 })
        this.sessions = res.data || []
      } catch (e) { /* 拦截器已提示 */ }
    },
    async loadCustomers() {
      try {
        const res = await customerPage({ pageNum: 1, pageSize: 100 })
        this.customers = (res.data && res.data.list) || []
      } catch (e) { /* 拦截器已提示 */ }
    },
    async openSession(s) {
      this.currentSessionId = s.id
      this.currentCustomerId = s.customerId
      this.recommendations = []
      this.compliance = null
      this.memoryUsed = null
      try {
        const res = await chatMessages({ sessionId: s.id })
        this.messages = (res.data || []).map((m) => ({
          role: m.role,
          content: m.content,
          intent: m.intent,
          intentZh: m.intentZh
        }))
        this.scrollBottom()
      } catch (e) { /* 拦截器已提示 */ }
    },
    newSession() {
      this.currentSessionId = null
      this.messages = []
      this.recommendations = []
      this.compliance = null
      this.memoryUsed = null
    },
    async send() {
      const text = this.input.trim()
      if (!text || this.sending) return
      this.messages.push({ role: 'user', content: text })
      this.input = ''
      this.sending = true
      this.scrollBottom()
      try {
        const res = await chatSend({
          sessionId: this.currentSessionId,
          customerId: this.currentCustomerId,
          message: text
        })
        const d = res.data || {}
        this.currentSessionId = d.session_id
        this.messages.push({
          role: 'assistant',
          content: d.reply || '',
          intent: d.intent,
          intentZh: d.intent_zh
        })
        this.recommendations = d.recommendations || []
        this.compliance = d.compliance || null
        this.memoryUsed = d.memory_used || null
        if (d.agent_available === false) {
          this.$store.dispatch('setAgentStatus', false)
        } else {
          this.$store.dispatch('setAgentStatus', true)
        }
        this.loadSessions()
      } catch (e) {
        this.messages.push({ role: 'assistant', content: '消息发送失败，请稍后重试。' })
      } finally {
        this.sending = false
        this.scrollBottom()
      }
    },
    scrollBottom() {
      this.$nextTick(() => {
        const el = this.$refs.messages
        if (el) el.scrollTop = el.scrollHeight
      })
    },
    formatTime(t) {
      if (!t) return ''
      const d = new Date(t)
      const mm = String(d.getMonth() + 1).padStart(2, '0')
      const dd = String(d.getDate()).padStart(2, '0')
      const hh = String(d.getHours()).padStart(2, '0')
      const mi = String(d.getMinutes()).padStart(2, '0')
      return `${mm}-${dd} ${hh}:${mi}`
    }
  }
}
</script>

<template>
  <div class="fa-root">
    <!-- 展开面板 -->
    <transition name="fa-pop">
      <div v-show="open" class="fa-panel">
        <!-- 头部 -->
        <div class="fa-header">
          <span class="ncb-mark"><i>南</i></span>
          <div class="fa-title">
            <span class="fa-name ncb-serif">南洋智能助手</span>
            <span class="fa-sub">全站 Copilot · 语义驱动页面动作</span>
          </div>
          <i class="el-icon-minus fa-head-btn" title="最小化" @click="open = false"></i>
          <i class="el-icon-close fa-head-btn" title="关闭" @click="open = false"></i>
        </div>

        <!-- 消息区 -->
        <div ref="msgBox" class="fa-msgs">
          <div v-for="(m, i) in messages" :key="i" class="fa-msg" :class="m.role">
            <!-- 文本气泡 -->
            <template v-if="!m.kind">
              <div class="fa-bubble">
                <span v-if="m.intentZh" class="fa-intent">{{ m.intentZh }}</span>
                {{ m.content }}
              </div>
            </template>

            <!-- 动作回执 -->
            <template v-else-if="m.kind === 'action'">
              <div class="fa-action-line">
                <i class="el-icon-position"></i>{{ m.content }}
              </div>
            </template>

            <!-- 迷你统计卡 -->
            <template v-else-if="m.kind === 'stats'">
              <div class="fa-stats">
                <div class="fa-stat">
                  <div class="fa-stat-value">{{ m.stats.todayChatCount || 0 }}</div>
                  <div class="fa-stat-label">今日咨询</div>
                </div>
                <div class="fa-stat">
                  <div class="fa-stat-value">{{ m.stats.todayRecommendCount || 0 }}</div>
                  <div class="fa-stat-label">今日推荐</div>
                </div>
                <div class="fa-stat">
                  <div class="fa-stat-value">{{ passRate(m.stats) }}</div>
                  <div class="fa-stat-label">合规通过率</div>
                </div>
                <div class="fa-stat">
                  <div class="fa-stat-value">{{ m.stats.customerCount || 0 }}</div>
                  <div class="fa-stat-label">在册企业</div>
                </div>
              </div>
            </template>

            <!-- 推荐卡 -->
            <template v-else-if="m.kind === 'recs'">
              <div v-for="(r, j) in m.items" :key="j" class="fa-rec">
                <div class="fa-rec-head">
                  <span class="fa-rec-name">{{ r.product.name }}</span>
                  <el-tag size="mini" effect="plain">{{ r.product.category }}</el-tag>
                </div>
                <div class="fa-rec-meta">
                  {{ r.product.rate_range_pct }} · 最高{{ Math.round(r.product.max_amount / 10000) }}万 ·
                  {{ r.product.approval_hours }}小时审批
                </div>
                <div class="fa-rec-score">
                  <div class="fa-rec-track">
                    <div class="fa-rec-fill"
                         :style="{ width: Math.round(r.scores.final_score * 100) + '%' }"></div>
                  </div>
                  <span>{{ r.scores.final_score.toFixed(3) }}</span>
                </div>
                <div class="fa-rec-reason">{{ r.reason }}</div>
              </div>
            </template>

            <!-- 文案卡 -->
            <template v-else-if="m.kind === 'copy'">
              <div class="fa-copy">
                <div class="fa-copy-head">
                  <el-tag size="mini" effect="dark">{{ m.copy.channel }}</el-tag>
                  <span class="fa-copy-product">{{ m.copy.productName }}</span>
                  <el-tag size="mini" :type="m.copy.compliant ? 'success' : 'danger'" effect="plain">
                    {{ m.copy.compliant ? '双重风控通过' : '命中违规' }}
                  </el-tag>
                </div>
                <div class="fa-copy-content">{{ m.copy.content }}</div>
                <div v-if="!m.copy.compliant && m.copy.hitRules" class="fa-copy-hits">
                  命中规则：{{ m.copy.hitRules }}
                </div>
              </div>
            </template>

            <!-- 行内加载 -->
            <template v-else-if="m.kind === 'loading'">
              <div class="fa-bubble fa-loading">
                <i class="el-icon-loading"></i>{{ m.content }}
              </div>
            </template>
          </div>
        </div>

        <!-- 快捷指令 -->
        <div class="fa-chips">
          <span v-for="c in chips" :key="c" class="fa-chip" @click="quickSend(c)">{{ c }}</span>
        </div>

        <!-- 输入区 -->
        <div class="fa-input">
          <el-input
            v-model="draft"
            size="small"
            placeholder="试试：帮我看看华创那家公司"
            :disabled="sending"
            @keyup.enter.native="send()"
          />
          <el-button
            type="primary"
            size="small"
            icon="el-icon-position"
            :loading="sending"
            :disabled="!draft.trim()"
            @click="send()"
          >发送</el-button>
        </div>
      </div>
    </transition>

    <!-- 悬浮球 -->
    <div class="fa-launcher" :class="{ 'fa-launcher-active': open }" title="南洋智能助手" @click="toggle">
      <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="#fff"
           stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <rect x="4" y="8" width="16" height="11" rx="3" />
        <path d="M12 8V4.5" />
        <circle cx="12" cy="3.5" r="1.2" fill="#fff" stroke="none" />
        <circle cx="9" cy="13" r="1.1" fill="#fff" stroke="none" />
        <circle cx="15" cy="13" r="1.1" fill="#fff" stroke="none" />
        <path d="M9.5 16.2c.8.6 1.6.9 2.5.9s1.7-.3 2.5-.9" />
      </svg>
      <span v-if="unread" class="fa-badge"></span>
    </div>
  </div>
</template>

<script>
import { chatSend, customerPage, customerDetail, productList, copyGenerate, dashboardStats } from '@/api'

/** 动作白名单（与 Agent site_action 提示词层一一对应，前端二次校验防幻觉动作） */
const NAV_PATHS = ['/dashboard', '/customer', '/product', '/recommend', '/copy', '/chat', '/profile']
const PATH_NAMES = {
  '/dashboard': '首页看板', '/customer': '企业客户', '/product': '信贷产品',
  '/recommend': '推荐记录', '/copy': '文案与合规', '/chat': '对公智能顾问', '/profile': '个人中心'
}

export default {
  name: 'FloatingAgent',
  data() {
    return {
      open: false,
      unread: false,
      sending: false,
      draft: '',
      sessionId: null,
      messages: [
        {
          role: 'agent',
          content: '您好，我是南洋智能助手。可以直接吩咐我，例如「帮我看看华创那家公司」「最近业务怎么样」「发个朋友圈宣传税易贷」。'
        }
      ],
      chips: ['今天业务怎么样', '帮我看看华创那家公司', '发个朋友圈宣传税易贷']
    }
  },
  methods: {
    toggle() {
      this.open = !this.open
      if (this.open) {
        this.unread = false
        this.scrollBottom()
      }
    },
    quickSend(text) {
      if (this.sending) return
      this.draft = text
      this.send()
    },
    push(msg) {
      this.messages.push(msg)
      if (!this.open) this.unread = true
      this.scrollBottom()
    },
    scrollBottom() {
      this.$nextTick(() => {
        const box = this.$refs.msgBox
        if (box) box.scrollTop = box.scrollHeight
      })
    },
    async send() {
      const text = this.draft.trim()
      if (!text || this.sending) return
      this.draft = ''
      this.push({ role: 'user', content: text })
      this.sending = true
      try {
        const res = await chatSend({
          message: text,
          sessionId: this.sessionId,
          context: { page: this.$route.path }
        })
        const d = res.data || {}
        this.sessionId = d.session_id || this.sessionId
        if (d.reply) {
          this.push({ role: 'agent', content: d.reply, intentZh: d.intent_zh })
        }
        if (Array.isArray(d.recommendations) && d.recommendations.length) {
          this.push({ role: 'agent', kind: 'recs', items: d.recommendations })
        }
        await this.executeActions(Array.isArray(d.actions) ? d.actions : [], text)
      } catch (e) {
        // 拦截器已提示
      } finally {
        this.sending = false
      }
    },

    /** 动作执行器：白名单校验 + 逐条执行 + 回执消息 */
    async executeActions(actions, rawText) {
      for (const a of actions.slice(0, 2)) {
        if (!a || typeof a.type !== 'string') continue
        const params = a.params && typeof a.params === 'object' ? a.params : {}
        const fn = this['do_' + a.type]
        if (typeof fn === 'function') {
          try {
            await fn.call(this, params, rawText)
          } catch (e) {
            this.push({ role: 'agent', kind: 'action', content: '动作执行未完成，请稍后重试' })
          }
        }
      }
    },
    feedback(content) {
      this.push({ role: 'agent', kind: 'action', content })
    },
    go(path) {
      if (this.$route.path !== path) this.$router.push(path)
    },

    do_navigate(params) {
      const path = String(params.path || '')
      if (!NAV_PATHS.includes(path)) return
      this.go(path)
      this.feedback(`已为您打开「${PATH_NAMES[path]}」`)
    },
    do_search_customer(params) {
      const keyword = String(params.keyword || '').trim()
      if (!keyword) return
      this.$store.commit('COPILOT_CMD', { customerKeyword: keyword })
      this.go('/customer')
      this.feedback(`已跳转到企业客户页，筛选：${keyword}`)
    },
    async do_view_customer(params) {
      const name = String(params.name || '').trim()
      if (!name) return
      const res = await customerPage({ name, pageNum: 1, pageSize: 5 })
      const list = (res.data && res.data.list) || []
      if (!list.length) {
        this.feedback(`未找到名称含「${name}」的企业客户`)
        return
      }
      const hit = list[0]
      const detail = await customerDetail(hit.id)
      this.$store.commit('COPILOT_CMD', { customerDetail: detail.data || hit })
      this.go('/customer')
      this.feedback(`已为您打开「${hit.name}」的客户详情`)
    },
    do_open_product(params) {
      const name = String(params.name || '').trim()
      this.$store.commit('COPILOT_CMD', { productName: name })
      this.go('/product')
      this.feedback(name ? `已跳转到信贷产品页，高亮：${name}` : '已跳转到信贷产品页')
    },
    async do_show_stats() {
      const res = await dashboardStats()
      this.push({ role: 'agent', kind: 'stats', stats: res.data || {} })
      this.feedback('以上为今日看板核心数据')
    },
    do_recommend(params, rawText) {
      const last = [...this.messages].reverse().find((m) => m.kind === 'recs')
      this.feedback(last ? '已根据您的条件生成授信推荐，见上方卡片'
                         : '暂未生成推荐，请补充用途、金额、期限等信息后再试')
    },
    async do_generate_copy(params) {
      const loadingMsg = { role: 'agent', kind: 'loading', content: '正在生成营销文案（双重风控审核中）…' }
      this.push(loadingMsg)
      try {
        const kw = String(params.product_name || '').trim()
        const channel = String(params.channel || '').trim() || '朋友圈'
        const plist = await productList()
        const rows = plist.data || []
        let hit = null
        if (kw) {
          hit = rows.find((r) => r.name && (r.name.includes(kw) || kw.includes(r.name)))
             || rows.find((r) => r.productCode === kw)
        }
        if (!hit) hit = rows[0]
        if (!hit) throw new Error('no product')
        const res = await copyGenerate({ productId: hit.productCode, channel })
        const rec = (res.data && res.data.record) || {}
        this.push({
          role: 'agent',
          kind: 'copy',
          copy: {
            channel: rec.channel || channel,
            productName: rec.productName || hit.name,
            content: rec.content || '',
            compliant: rec.compliant === 1,
            hitRules: rec.hitRules || ''
          }
        })
        this.feedback(`文案已生成并入库，可在「文案与合规」页查看`)
      } finally {
        const idx = this.messages.indexOf(loadingMsg)
        if (idx >= 0) this.messages.splice(idx, 1)
      }
    },

    passRate(stats) {
      const c = stats && stats.compliance
      return c ? (c.passRate * 100).toFixed(1) + '%' : '—'
    }
  }
}
</script>

<style scoped>
.fa-root {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1999;
}

/* ---------- 悬浮球 ---------- */
.fa-launcher {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #e30000, #b30000);
  box-shadow: 0 6px 18px rgba(227, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}
.fa-launcher:hover {
  transform: translateY(-3px) scale(1.05);
  box-shadow: 0 10px 24px rgba(227, 0, 0, 0.5);
}
.fa-launcher-active {
  background: linear-gradient(135deg, #2b1665, #1a0d42);
  box-shadow: 0 6px 18px rgba(43, 22, 101, 0.45);
}
.fa-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #f7ba2a;
  border: 2px solid #fff;
}

/* ---------- 面板 ---------- */
.fa-panel {
  position: absolute;
  right: 0;
  bottom: 68px;
  width: 380px;
  height: 560px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(26, 13, 66, 0.25);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.fa-pop-enter-active, .fa-pop-leave-active {
  transition: all 0.22s ease;
}
.fa-pop-enter, .fa-pop-leave-to {
  opacity: 0;
  transform: translateY(16px) scale(0.96);
}

/* 头部 */
.fa-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: linear-gradient(135deg, #2b1665, #1a0d42);
  color: #fff;
}
.fa-title {
  flex: 1;
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}
.fa-name {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 1px;
}
.fa-sub {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.55);
}
.fa-head-btn {
  cursor: pointer;
  color: rgba(255, 255, 255, 0.75);
  font-size: 14px;
  padding: 4px;
}
.fa-head-btn:hover {
  color: #fff;
}

/* 消息区 */
.fa-msgs {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  background: #f6f4fa;
}
.fa-msg {
  margin-bottom: 10px;
  display: flex;
  flex-direction: column;
}
.fa-msg.user {
  align-items: flex-end;
}
.fa-msg.agent {
  align-items: flex-start;
}
.fa-bubble {
  max-width: 86%;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.fa-msg.user .fa-bubble {
  background: #e30000;
  color: #fff;
  border-bottom-right-radius: 2px;
}
.fa-msg.agent .fa-bubble {
  background: #fff;
  color: #1f2d3d;
  border: 1px solid #ece8f4;
  border-bottom-left-radius: 2px;
}
.fa-intent {
  display: inline-block;
  font-size: 10px;
  color: #e30000;
  background: #fdecec;
  border-radius: 3px;
  padding: 0 5px;
  margin-right: 6px;
}
.fa-loading {
  color: #8a97a8 !important;
}
.fa-loading i {
  margin-right: 6px;
}

/* 动作回执 */
.fa-action-line {
  font-size: 12px;
  color: #2b1665;
  background: rgba(43, 22, 101, 0.07);
  border: 1px dashed rgba(43, 22, 101, 0.25);
  border-radius: 6px;
  padding: 5px 10px;
}
.fa-action-line i {
  margin-right: 5px;
  color: #e30000;
}

/* 迷你统计卡 */
.fa-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  width: 100%;
}
.fa-stat {
  background: #fff;
  border: 1px solid #ece8f4;
  border-radius: 8px;
  padding: 10px 12px;
}
.fa-stat-value {
  font-size: 18px;
  font-weight: 700;
  color: #2b1665;
}
.fa-stat-label {
  font-size: 11px;
  color: #8a97a8;
  margin-top: 2px;
}

/* 推荐卡 */
.fa-rec {
  width: 100%;
  background: #fff;
  border: 1px solid #ece8f4;
  border-left: 3px solid #e30000;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 6px;
}
.fa-rec-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.fa-rec-name {
  font-weight: 700;
  font-size: 13px;
  color: #1f2d3d;
}
.fa-rec-meta {
  font-size: 12px;
  color: #8a97a8;
  margin-bottom: 6px;
}
.fa-rec-score {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #2b1665;
  margin-bottom: 6px;
}
.fa-rec-track {
  flex: 1;
  height: 6px;
  background: #f0edf7;
  border-radius: 3px;
  overflow: hidden;
}
.fa-rec-fill {
  height: 100%;
  background: linear-gradient(90deg, #e30000, #f23a3a);
  border-radius: 3px;
}
.fa-rec-reason {
  font-size: 12px;
  color: #5e6d82;
  line-height: 1.55;
}

/* 文案卡 */
.fa-copy {
  width: 100%;
  background: #fff;
  border: 1px solid #ece8f4;
  border-radius: 8px;
  padding: 10px 12px;
}
.fa-copy-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.fa-copy-product {
  font-size: 12px;
  font-weight: 600;
  color: #2b1665;
  flex: 1;
}
.fa-copy-content {
  font-size: 12px;
  color: #1f2d3d;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  background: #faf9fd;
  border-radius: 6px;
  padding: 8px 10px;
}
.fa-copy-hits {
  margin-top: 6px;
  font-size: 11px;
  color: #f56c6c;
  line-height: 1.5;
}

/* 快捷指令 */
.fa-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 12px 0;
  background: #fff;
}
.fa-chip {
  font-size: 11px;
  color: #e30000;
  background: #fdecec;
  border-radius: 10px;
  padding: 3px 10px;
  cursor: pointer;
  transition: background 0.15s;
}
.fa-chip:hover {
  background: #f9d7d7;
}

/* 输入区 */
.fa-input {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  background: #fff;
  border-top: 1px solid #f0edf7;
}
</style>

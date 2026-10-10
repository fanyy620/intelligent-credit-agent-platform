<template>
  <div>
    <!-- 查询栏 -->
    <div class="page-card">
      <el-form :inline="true" size="small">
        <el-form-item label="企业">
          <el-select v-model="query.customerId" clearable filterable placeholder="全部企业"
                     style="width: 220px">
            <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="el-icon-search" @click="load(1)">查询</el-button>
          <el-button icon="el-icon-refresh" @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 记录列表 -->
    <div class="page-card">
      <el-table :data="rows" v-loading="loading" stripe size="small">
        <el-table-column type="expand">
          <template slot-scope="{ row }">
            <div style="padding: 8px 16px">
              <h4 style="margin: 4px 0 8px">三层推荐评分明细（业务分 + 语义分加权）</h4>
              <div v-for="(r, i) in parseResult(row).recommendations" :key="i" class="rec-card"
                   style="max-width: 640px">
                <div class="rec-head">
                  <span class="rec-name">Top{{ i + 1 }} {{ r.product.name }}</span>
                  <el-tag size="mini">{{ r.product.category }}</el-tag>
                </div>
                <div v-for="dim in dims" :key="dim.key" class="score-row">
                  <span class="score-label">{{ dim.label }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: Math.round((r.scores[dim.key] || 0) * 100) + '%' }"></div>
                  </div>
                  <span class="bar-value">{{ (r.scores[dim.key] || 0).toFixed(2) }}</span>
                </div>
                <div class="score-row">
                  <span class="score-label" style="font-weight: 600">综合分</span>
                  <div class="bar-track">
                    <div class="bar-fill" style="background: linear-gradient(90deg,#e30000,#f26b6b)"
                         :style="{ width: Math.round((r.scores.final_score || 0) * 100) + '%' }"></div>
                  </div>
                  <span class="bar-value" style="font-weight: 600">{{ (r.scores.final_score || 0).toFixed(3) }}</span>
                </div>
              </div>
              <h4 style="margin: 12px 0 8px">抽取槽位</h4>
              <div class="json-view">{{ prettyJson(parseResult(row).slots) }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="企业融资诉求" min-width="240" show-overflow-tooltip>
          <template slot-scope="{ row }">{{ row.message }}</template>
        </el-table-column>
        <el-table-column prop="customerName" label="关联企业" width="180">
          <template slot-scope="{ row }">{{ row.customerName || '—' }}</template>
        </el-table-column>
        <el-table-column label="首推产品" width="120">
          <template slot-scope="{ row }">
            <el-tag size="mini" type="primary">{{ row.topProduct }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="客户经理" width="100" />
        <el-table-column label="时间" width="150">
          <template slot-scope="{ row }">{{ formatTime(row.createTime) }}</template>
        </el-table-column>
      </el-table>
      <el-pagination
        style="margin-top: 12px; text-align: right"
        background
        layout="total, prev, pager, next"
        :total="total"
        :page-size="query.pageSize"
        :current-page.sync="query.pageNum"
        @current-change="load()"
      />
    </div>
  </div>
</template>

<script>
import { recommendPage, customerPage } from '@/api'

export default {
  name: 'RecommendRecords',
  data() {
    return {
      loading: false,
      rows: [],
      total: 0,
      customers: [],
      query: { customerId: null, pageNum: 1, pageSize: 10 },
      dims: [
        { key: 'amount_score', label: '额度匹配' },
        { key: 'rate_score', label: '利率优惠' },
        { key: 'term_score', label: '期限灵活' },
        { key: 'speed_score', label: '审批速度' }
      ]
    }
  },
  created() {
    this.load()
    this.loadCustomers()
  },
  methods: {
    async load(page) {
      if (page) this.query.pageNum = page
      this.loading = true
      try {
        const res = await recommendPage(this.query)
        this.rows = (res.data && res.data.list) || []
        this.total = (res.data && res.data.total) || 0
      } catch (e) { /* 拦截器已提示 */ } finally {
        this.loading = false
      }
    },
    async loadCustomers() {
      try {
        const res = await customerPage({ pageNum: 1, pageSize: 100 })
        this.customers = (res.data && res.data.list) || []
      } catch (e) { /* 拦截器已提示 */ }
    },
    reset() {
      this.query.customerId = null
      this.load(1)
    },
    parseResult(row) {
      try {
        const data = JSON.parse(row.resultJson || '{}')
        return {
          recommendations: data.recommendations || [],
          slots: data.slots || {}
        }
      } catch (e) {
        return { recommendations: [], slots: {} }
      }
    },
    prettyJson(obj) {
      return JSON.stringify(obj, null, 2)
    },
    formatTime(t) {
      if (!t) return ''
      const d = new Date(t)
      const pad = (n) => String(n).padStart(2, '0')
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
    }
  }
}
</script>

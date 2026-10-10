<template>
  <div>
    <!-- 操作栏 -->
    <div class="page-card">
      <el-form :inline="true" size="small">
        <el-form-item>
          <el-switch v-model="onlyViolation" active-text="仅看违规" @change="load(1)" />
        </el-form-item>
        <el-form-item style="float: right">
          <el-button type="primary" icon="el-icon-magic-stick" @click="openGenerate">生成文案</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 记录列表 -->
    <div class="page-card">
      <el-table :data="rows" v-loading="loading" stripe size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="productName" label="产品" width="110" />
        <el-table-column prop="channel" label="渠道" width="80">
          <template slot-scope="{ row }">
            <el-tag size="mini" type="info">{{ row.channel }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文案内容" min-width="300">
          <template slot-scope="{ row }">
            <div :class="{ 'violation-text': row.compliant === 0 }"
                 style="white-space: pre-wrap; line-height: 1.6">
              {{ row.content }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="合规结论" width="110">
          <template slot-scope="{ row }">
            <el-tag size="mini" :type="row.compliant === 1 ? 'success' : 'danger'">
              {{ row.compliant === 1 ? '通过' : '违规' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="命中规则" width="180">
          <template slot-scope="{ row }">
            <span v-if="!parseHits(row).length" style="color: #a0aabb">—</span>
            <el-tag v-for="(h, i) in parseHits(row)" :key="i" size="mini" type="danger"
                    style="margin: 0 4px 4px 0">
              {{ h }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="审核说明" width="200" show-overflow-tooltip />
        <el-table-column prop="username" label="操作人" width="90" />
        <el-table-column label="操作" width="80" fixed="right">
          <template slot-scope="{ row }">
            <el-button type="text" size="mini" @click="viewTemplate(row)">查看模板</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        style="margin-top: 12px; text-align: right"
        background
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page.sync="pageNum"
        @current-change="load()"
      />
    </div>

    <!-- 生成对话框 -->
    <el-dialog title="生成营销文案" :visible.sync="generateVisible" width="560px">
      <el-alert type="info" :closable="false" style="margin-bottom: 14px"
                title="LLM 只生成无数字模板，数值由结构化产品数据填充，从机制上杜绝数值幻觉；产出经双重风控审核后落库。" />
      <el-form label-width="90px" size="small">
        <el-form-item label="产品">
          <el-select v-model="generateForm.productId" style="width: 100%" placeholder="选择产品">
            <el-option v-for="p in products" :key="p.productCode"
                       :label="p.name + '（' + p.category + '）'" :value="p.productCode" />
          </el-select>
        </el-form-item>
        <el-form-item label="投放渠道">
          <el-radio-group v-model="generateForm.channel">
            <el-radio-button label="朋友圈" />
            <el-radio-button label="短信" />
            <el-radio-button label="海报" />
          </el-radio-group>
        </el-form-item>
        <el-form-item label="关联企业">
          <el-select v-model="generateForm.customerId" clearable filterable placeholder="可选"
                     style="width: 100%">
            <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button size="small" @click="generateVisible = false">取消</el-button>
        <el-button size="small" type="primary" :loading="generating" @click="doGenerate">
          生成并审核
        </el-button>
      </div>
    </el-dialog>

    <!-- 模板查看对话框 -->
    <el-dialog title="模板与填充机制" :visible.sync="templateVisible" width="640px">
      <h4 style="margin: 0 0 8px">LLM 输出模板（只允许槽位，禁止数字）</h4>
      <div class="json-view">{{ currentRow.template || '（无）' }}</div>
      <h4 style="margin: 14px 0 8px">最终成稿（数值由结构化数据渲染 + 强制免责声明）</h4>
      <div style="white-space: pre-wrap; line-height: 1.8; font-size: 13px">{{ currentRow.content }}</div>
    </el-dialog>
  </div>
</template>

<script>
import { copyPage, copyGenerate, productList, customerPage } from '@/api'

export default {
  name: 'CopyRecords',
  data() {
    return {
      loading: false,
      generating: false,
      rows: [],
      total: 0,
      pageNum: 1,
      pageSize: 10,
      onlyViolation: false,
      products: [],
      customers: [],
      generateVisible: false,
      generateForm: { productId: '', channel: '朋友圈', customerId: null },
      templateVisible: false,
      currentRow: {}
    }
  },
  created() {
    this.load()
    this.loadProducts()
    this.loadCustomers()
  },
  methods: {
    async load(page) {
      if (page) this.pageNum = page
      this.loading = true
      try {
        const res = await copyPage({
          onlyViolation: this.onlyViolation,
          pageNum: this.pageNum,
          pageSize: this.pageSize
        })
        this.rows = (res.data && res.data.list) || []
        this.total = (res.data && res.data.total) || 0
      } catch (e) { /* 拦截器已提示 */ } finally {
        this.loading = false
      }
    },
    async loadProducts() {
      try {
        const res = await productList()
        this.products = res.data || []
      } catch (e) { /* 拦截器已提示 */ }
    },
    async loadCustomers() {
      try {
        const res = await customerPage({ pageNum: 1, pageSize: 100 })
        this.customers = (res.data && res.data.list) || []
      } catch (e) { /* 拦截器已提示 */ }
    },
    openGenerate() {
      this.generateForm = {
        productId: this.products.length ? this.products[0].productCode : '',
        channel: '朋友圈',
        customerId: null
      }
      this.generateVisible = true
    },
    async doGenerate() {
      if (!this.generateForm.productId) {
        this.$message.warning('请选择产品')
        return
      }
      this.generating = true
      try {
        const res = await copyGenerate(this.generateForm)
        const record = res.data && res.data.record
        if (record && record.compliant === 1) {
          this.$message.success('文案已生成并通过双重风控审核')
        } else {
          this.$message.warning('文案已生成，但命中违规规则，请查看记录')
        }
        this.generateVisible = false
        this.load(1)
      } catch (e) { /* 拦截器已提示（Agent 离线时给出友好提示） */ } finally {
        this.generating = false
      }
    },
    viewTemplate(row) {
      this.currentRow = row
      this.templateVisible = true
    },
    parseHits(row) {
      try {
        const hits = JSON.parse(row.hitRules || '[]')
        return Array.isArray(hits) ? hits : []
      } catch (e) {
        return []
      }
    }
  }
}
</script>

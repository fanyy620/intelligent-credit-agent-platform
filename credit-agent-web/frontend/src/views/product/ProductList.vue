<template>
  <div>
    <div class="page-card">
      <el-row type="flex" justify="space-between" align="middle">
        <span style="color: #8a97a8; font-size: 13px">
          产品库与 Python Agent 的 configs/products.yaml 字段对齐；列表走 Redis 缓存，变更自动失效。
        </span>
        <el-button v-if="isAdmin" type="primary" size="small" icon="el-icon-plus" plain @click="openEdit()">
          新增产品
        </el-button>
      </el-row>
    </div>

    <div class="page-card">
      <el-table :data="rows" v-loading="loading" stripe size="small" :row-class-name="rowClass">
        <el-table-column prop="name" label="产品" width="110">
          <template slot-scope="{ row }">
            <span style="font-weight: 600">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="类别" width="80">
          <template slot-scope="{ row }">
            <el-tag size="mini">{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="额度区间" width="140">
          <template slot-scope="{ row }">
            {{ wan(row.minAmount) }} - {{ wan(row.maxAmount) }}
          </template>
        </el-table-column>
        <el-table-column label="期限（月）" width="90">
          <template slot-scope="{ row }">{{ row.minTermMonths }}-{{ row.maxTermMonths }}</template>
        </el-table-column>
        <el-table-column label="年化利率" width="110">
          <template slot-scope="{ row }">
            {{ pct(row.annualRateMin) }}-{{ pct(row.annualRateMax) }}
          </template>
        </el-table-column>
        <el-table-column label="审批时效" width="90">
          <template slot-scope="{ row }">{{ row.approvalHours }} 小时</template>
        </el-table-column>
        <el-table-column prop="allowedPurposes" label="准入用途" width="150" show-overflow-tooltip />
        <el-table-column prop="tags" label="标签" show-overflow-tooltip />
        <el-table-column label="状态" width="70">
          <template slot-scope="{ row }">
            <el-tag size="mini" :type="row.status === 1 ? 'success' : 'info'">
              {{ row.status === 1 ? '在售' : '下架' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" label="操作" width="130" fixed="right">
          <template slot-scope="{ row }">
            <el-button type="text" size="mini" @click="openEdit(row)">编辑</el-button>
            <el-button type="text" size="mini" style="color: #f56c6c" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 编辑对话框（关键字段；完整字段与 products.yaml 对齐） -->
    <el-dialog :title="form.id ? '编辑产品' : '新增产品'" :visible.sync="dialogVisible" width="640px">
      <el-form ref="form" :model="form" :rules="formRules" label-width="110px" size="small">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="产品编码" prop="productCode">
              <el-input v-model="form.productCode" :disabled="!!form.id" placeholder="如 xinxiangdai" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="产品名称" prop="name">
              <el-input v-model="form.name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="类别">
              <el-select v-model="form.category" style="width: 100%">
                <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-switch v-model="form.status" :active-value="1" :inactive-value="0"
                         active-text="在售" inactive-text="下架" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="起借金额(元)">
              <el-input-number v-model="form.minAmount" :min="0" :step="10000" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最高额度(元)">
              <el-input-number v-model="form.maxAmount" :min="0" :step="100000" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最短期限(月)">
              <el-input-number v-model="form.minTermMonths" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最长期限(月)">
              <el-input-number v-model="form.maxTermMonths" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最低年化(小数)">
              <el-input-number v-model="form.annualRateMin" :min="0" :max="0.36" :step="0.001"
                               :precision="4" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最高年化(小数)">
              <el-input-number v-model="form.annualRateMax" :min="0" :max="0.36" :step="0.001"
                               :precision="4" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="审批时效(小时)">
              <el-input-number v-model="form.approvalHours" :min="0" :step="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最低月收入(元)">
              <el-input-number v-model="form.minMonthlyIncome" :min="0" :step="1000" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="年龄区间">
              <el-input-number v-model="form.minAge" :min="18" style="width: 45%" />
              ~
              <el-input-number v-model="form.maxAge" :min="18" style="width: 45%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最低征信分">
              <el-input-number v-model="form.minCreditScore" :min="0" :max="900" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="准入用途">
              <el-input v-model="form.allowedPurposes" placeholder="逗号分隔，如：消费,装修,教育" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="标签">
              <el-input v-model="form.tags" placeholder="逗号分隔" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="产品描述">
              <el-input v-model="form.description" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <div slot="footer">
        <el-button size="small" @click="dialogVisible = false">取消</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="save">保存</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { productList, productCreate, productUpdate, productDelete } from '@/api'

export default {
  name: 'ProductList',
  data() {
    return {
      loading: false,
      saving: false,
      rows: [],
      highlightName: '',
      categories: ['消费贷', '经营贷', '房抵贷', '车贷'],
      dialogVisible: false,
      form: {},
      formRules: {
        productCode: [{ required: true, message: '请输入产品编码', trigger: 'blur' }],
        name: [{ required: true, message: '请输入产品名称', trigger: 'blur' }]
      }
    }
  },
  computed: {
    isAdmin() {
      return this.$store.getters.isAdmin
    }
  },
  watch: {
    // Copilot 指令消费：高亮目标产品行并滚动到位
    '$store.state.copilot._seq'() {
      const name = this.$store.state.copilot.productName
      if (!name) return
      this.$store.commit('COPILOT_CMD', { productName: '' })
      this.highlightName = name
      this.$nextTick(() => {
        const el = this.$el.querySelector('.copilot-highlight')
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
    }
  },
  created() {
    this.load()
  },
  methods: {
    async load() {
      this.loading = true
      try {
        const res = await productList()
        this.rows = res.data || []
      } catch (e) { /* 拦截器已提示 */ } finally {
        this.loading = false
      }
    },
    openEdit(row) {
      this.form = row ? { ...row } : {
        category: '消费贷', status: 1, minTermMonths: 6, maxTermMonths: 36,
        minAge: 22, maxAge: 55, minCreditScore: 550, approvalHours: 24
      }
      this.dialogVisible = true
    },
    async save() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return
        this.saving = true
        try {
          if (this.form.id) {
            await productUpdate(this.form.id, this.form)
          } else {
            await productCreate(this.form)
          }
          this.$message.success('保存成功（产品缓存已刷新）')
          this.dialogVisible = false
          this.load()
        } catch (e) { /* 拦截器已提示 */ } finally {
          this.saving = false
        }
      })
    },
    remove(row) {
      this.$confirm(`确认删除产品「${row.name}」？`, '删除确认', { type: 'warning' })
        .then(async () => {
          await productDelete(row.id)
          this.$message.success('已删除')
          this.load()
        })
        .catch(() => {})
    },
    wan(v) {
      return v ? Number(v) / 10000 + '万' : '—'
    },
    pct(v) {
      return v != null ? (Number(v) * 100).toFixed(2).replace(/\.?0+$/, '') + '%' : '—'
    },
    rowClass({ row }) {
      const kw = this.highlightName
      if (!kw) return ''
      return (row.name && (row.name.includes(kw) || kw.includes(row.name))) || row.productCode === kw
        ? 'copilot-highlight'
        : ''
    }
  }
}
</script>

<style scoped>
::v-deep .copilot-highlight > td {
  background: #fdecec !important;
  border-top: 1px solid #e30000;
  border-bottom: 1px solid #e30000;
}
::v-deep .copilot-highlight > td:first-child {
  border-left: 3px solid #e30000;
}
</style>

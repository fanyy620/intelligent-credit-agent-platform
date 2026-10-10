<template>
  <div>
    <!-- 查询栏 -->
    <div class="page-card">
      <el-form :inline="true" size="small">
        <el-form-item label="企业名称">
          <el-input v-model="query.name" placeholder="模糊搜索" clearable style="width: 180px" />
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="query.phone" placeholder="模糊搜索" clearable style="width: 150px" />
        </el-form-item>
        <el-form-item label="所属行业">
          <el-select v-model="query.occupation" clearable placeholder="全部" style="width: 130px">
            <el-option v-for="o in occupations" :key="o" :label="o" :value="o" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="el-icon-search" @click="load(1)">查询</el-button>
          <el-button icon="el-icon-refresh" @click="reset">重置</el-button>
        </el-form-item>
        <el-form-item style="float: right">
          <el-button type="primary" icon="el-icon-plus" plain @click="openEdit()">新增企业</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 列表 -->
    <div class="page-card">
      <el-table :data="rows" v-loading="loading" stripe size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="企业名称" min-width="190" show-overflow-tooltip />
        <el-table-column prop="gender" label="企业性质" width="80" />
        <el-table-column prop="phone" label="联系电话" width="140" />
        <el-table-column prop="age" label="成立年限" width="80" />
        <el-table-column prop="occupation" label="所属行业" width="100" />
        <el-table-column label="月均营收" width="130">
          <template slot-scope="{ row }">
            {{ row.monthlyIncome ? Number(row.monthlyIncome).toLocaleString() + ' 元' : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="企业征信" width="90">
          <template slot-scope="{ row }">
            <el-tag size="mini" :type="creditTag(row.creditStatus)">{{ row.creditStatus || '未知' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" show-overflow-tooltip />
        <el-table-column prop="createBy" label="归属经理" width="100" />
        <el-table-column label="操作" width="140" fixed="right">
          <template slot-scope="{ row }">
            <el-button type="text" size="mini" @click="openEdit(row)">编辑</el-button>
            <el-button type="text" size="mini" style="color: #f56c6c" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        style="margin-top: 12px; text-align: right"
        background
        layout="total, prev, pager, next, sizes"
        :total="total"
        :page-size="query.pageSize"
        :current-page.sync="query.pageNum"
        :page-sizes="[10, 20, 50]"
        @current-change="load()"
        @size-change="(s) => { query.pageSize = s; load(1) }"
      />
    </div>

    <!-- 编辑对话框 -->
    <el-dialog :title="form.id ? '编辑企业' : '新增企业'" :visible.sync="dialogVisible" width="520px">
      <el-form ref="form" :model="form" :rules="formRules" label-width="90px" size="small">
        <el-form-item label="企业名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="企业性质">
          <el-radio-group v-model="form.gender">
            <el-radio label="国企">国企</el-radio>
            <el-radio label="民企">民企</el-radio>
            <el-radio label="外企">外企</el-radio>
            <el-radio label="小微">小微</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="form.phone" />
        </el-form-item>
        <el-form-item label="成立年限">
          <el-input-number v-model="form.age" :min="0" :max="100" />
        </el-form-item>
        <el-form-item label="所属行业">
          <el-select v-model="form.occupation" style="width: 100%">
            <el-option v-for="o in occupations" :key="o" :label="o" :value="o" />
          </el-select>
        </el-form-item>
        <el-form-item label="月均营收">
          <el-input-number v-model="form.monthlyIncome" :min="0" :step="100000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="企业征信">
          <el-select v-model="form.creditStatus" style="width: 100%">
            <el-option label="良好" value="良好" />
            <el-option label="一般" value="一般" />
            <el-option label="有逾期" value="有逾期" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button size="small" @click="dialogVisible = false">取消</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="save">保存</el-button>
      </div>
    </el-dialog>

    <!-- 客户详情对话框（Copilot view_customer 动作落点） -->
    <el-dialog title="企业客户详情" :visible.sync="detailVisible" width="560px">
      <div class="detail-grid">
        <div class="detail-item"><span class="detail-label">企业名称</span><span>{{ detail.name }}</span></div>
        <div class="detail-item"><span class="detail-label">企业性质</span><span>{{ detail.gender || '—' }}</span></div>
        <div class="detail-item"><span class="detail-label">联系电话</span><span>{{ detail.phone || '—' }}</span></div>
        <div class="detail-item"><span class="detail-label">成立年限</span><span>{{ detail.age != null ? detail.age + ' 年' : '—' }}</span></div>
        <div class="detail-item"><span class="detail-label">所属行业</span><span>{{ detail.occupation || '—' }}</span></div>
        <div class="detail-item">
          <span class="detail-label">月均营收</span>
          <span>{{ detail.monthlyIncome ? Number(detail.monthlyIncome).toLocaleString() + ' 元' : '—' }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">企业征信</span>
          <el-tag size="mini" :type="creditTag(detail.creditStatus)">{{ detail.creditStatus || '未知' }}</el-tag>
        </div>
        <div class="detail-item"><span class="detail-label">归属经理</span><span>{{ detail.createBy || '—' }}</span></div>
        <div class="detail-item detail-full"><span class="detail-label">备注</span><span>{{ detail.remark || '—' }}</span></div>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { customerPage, customerCreate, customerUpdate, customerDelete } from '@/api'

export default {
  name: 'CustomerList',
  data() {
    return {
      loading: false,
      saving: false,
      rows: [],
      total: 0,
      query: { name: '', phone: '', occupation: '', pageNum: 1, pageSize: 10 },
      occupations: ['制造业', '贸易物流', '建筑工程', '医药科技', '餐饮服务', '批发零售', '其他'],
      dialogVisible: false,
      detailVisible: false,
      detail: {},
      form: {},
      formRules: {
        name: [{ required: true, message: '请输入企业名称', trigger: 'blur' }]
      }
    }
  },
  watch: {
    // Copilot 指令消费：关键词筛选 / 打开详情
    '$store.state.copilot._seq'() {
      const c = this.$store.state.copilot
      if (c.customerKeyword) {
        this.query.name = c.customerKeyword
        this.$store.commit('COPILOT_CMD', { customerKeyword: '' })
        this.load(1)
      }
      if (c.customerDetail) {
        this.detail = c.customerDetail
        this.$store.commit('COPILOT_CMD', { customerDetail: null })
        this.detailVisible = true
      }
    }
  },
  created() {
    this.load()
  },
  methods: {
    async load(page) {
      if (page) this.query.pageNum = page
      this.loading = true
      try {
        const res = await customerPage(this.query)
        this.rows = (res.data && res.data.list) || []
        this.total = (res.data && res.data.total) || 0
      } catch (e) { /* 拦截器已提示 */ } finally {
        this.loading = false
      }
    },
    reset() {
      this.query = { name: '', phone: '', occupation: '', pageNum: 1, pageSize: this.query.pageSize }
      this.load(1)
    },
    openEdit(row) {
      this.form = row ? { ...row } : { gender: '民企', occupation: '制造业', creditStatus: '良好' }
      this.dialogVisible = true
    },
    async save() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return
        this.saving = true
        try {
          if (this.form.id) {
            await customerUpdate(this.form.id, this.form)
          } else {
            await customerCreate(this.form)
          }
          this.$message.success('保存成功')
          this.dialogVisible = false
          this.load()
        } catch (e) { /* 拦截器已提示 */ } finally {
          this.saving = false
        }
      })
    },
    remove(row) {
      this.$confirm(`确认删除企业「${row.name}」？`, '删除确认', { type: 'warning' })
        .then(async () => {
          await customerDelete(row.id)
          this.$message.success('已删除')
          this.load()
        })
        .catch(() => {})
    },
    creditTag(status) {
      if (status === '良好') return 'success'
      if (status === '有逾期') return 'danger'
      return 'warning'
    }
  }
}
</script>

<style scoped>
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 20px;
  font-size: 13px;
}
.detail-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.detail-full {
  grid-column: 1 / -1;
}
.detail-label {
  color: #8a97a8;
  font-size: 12px;
}
</style>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <span class="ncb-mark ncb-mark-lg"><i>南</i></span>
        <div>
          <div class="login-title ncb-serif">南洋商业银行</div>
          <div class="login-brand-en">NANYANG COMMERCIAL BANK</div>
        </div>
      </div>
      <div class="login-subtitle">智能信贷服务平台 · 对公信贷智能营销与咨询中台</div>
      <div class="login-slogan ncb-serif">以客为先 · 以礼待人</div>
      <el-form ref="form" :model="form" :rules="rules" @submit.native.prevent>
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="账号" prefix-icon="el-icon-user"
                    @keyup.enter.native="submit" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码"
                    prefix-icon="el-icon-lock" show-password
                    @keyup.enter.native="submit" />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" @click="submit">
          登 录
        </el-button>
      </el-form>
      <div style="margin-top: 18px; color: #a0aabb; font-size: 12px; text-align: center">
        演示账号：admin / 123456（管理员）&nbsp;·&nbsp;manager01 / 123456（客户经理）
      </div>
    </div>
  </div>
</template>

<script>
import { login } from '@/api'

export default {
  name: 'LoginPage',
  data() {
    return {
      loading: false,
      form: { username: 'admin', password: '' },
      rules: {
        username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
        password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
      }
    }
  },
  methods: {
    submit() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return
        this.loading = true
        try {
          const res = await login(this.form)
          this.$store.commit('SET_TOKEN', res.data.token)
          this.$store.commit('SET_USER', res.data.user)
          this.$message.success('登录成功，欢迎回来')
          this.$router.replace('/')
        } catch (e) {
          // 错误消息已由拦截器统一提示
        } finally {
          this.loading = false
        }
      })
    }
  }
}
</script>

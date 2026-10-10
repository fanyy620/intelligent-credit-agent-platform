import axios from 'axios'
import { Message } from 'element-ui'
import store from '@/store'
import router from '@/router'

/**
 * axios 封装：
 * - baseURL /api（vite 代理到 SSM 后端）
 * - 请求拦截：注入 Authorization: Bearer {token}
 * - 响应拦截：code=0 返回 data；code=401 清登录态跳登录页；其余弹错
 */
const service = axios.create({
  baseURL: '/api',
  timeout: 20000
})

service.interceptors.request.use(
  (config) => {
    const token = store.state.token
    if (token) {
      config.headers['Authorization'] = 'Bearer ' + token
    }
    return config
  },
  (error) => Promise.reject(error)
)

service.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body == null || typeof body.code === 'undefined') {
      return body
    }
    if (body.code === 0) {
      return body
    }
    if (body.code === 401) {
      store.dispatch('resetLogin')
      Message.warning(body.message || '登录已失效，请重新登录')
      router.replace('/login')
      return Promise.reject(new Error(body.message || 'unauthorized'))
    }
    Message.error(body.message || '请求失败')
    return Promise.reject(new Error(body.message || 'error'))
  },
  (error) => {
    const msg = error.response && error.response.data && error.response.data.message
      ? error.response.data.message
      : '网络异常，请确认后端服务已启动'
    Message.error(msg)
    return Promise.reject(error)
  }
)

export default service

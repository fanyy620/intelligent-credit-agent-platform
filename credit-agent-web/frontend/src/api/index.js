import request from './request'

/** 集中式 API 定义：与 SSM 控制器一一对应 */

// ---- 认证 ----
export const login = (data) => request.post('/auth/login', data)
export const logout = () => request.post('/auth/logout')
export const getInfo = () => request.get('/auth/info')

// ---- 数据看板 ----
export const dashboardStats = () => request.get('/dashboard/stats')

// ---- 客户管理 ----
export const customerPage = (params) => request.get('/customer/page', { params })
export const customerDetail = (id) => request.get(`/customer/${id}`)
export const customerCreate = (data) => request.post('/customer', data)
export const customerUpdate = (id, data) => request.put(`/customer/${id}`, data)
export const customerDelete = (id) => request.delete(`/customer/${id}`)

// ---- 产品管理 ----
export const productList = () => request.get('/product/list')
export const productCreate = (data) => request.post('/product', data)
export const productUpdate = (id, data) => request.put(`/product/${id}`, data)
export const productDelete = (id) => request.delete(`/product/${id}`)

// ---- 智能对话 ----
// 真实 LLM（kimi-for-coding reasoning）单轮约 90-130s，聊天与文案请求单独放宽超时
export const chatSend = (data) => request.post('/chat/send', data, { timeout: 180000 })
export const chatSessions = (params) => request.get('/chat/sessions', { params })
export const chatMessages = (params) => request.get('/chat/messages', { params })

// ---- 推荐记录 ----
export const recommendPage = (params) => request.get('/recommend/page', { params })

// ---- 营销文案与合规 ----
export const copyGenerate = (data) => request.post('/copy/generate', data, { timeout: 180000 })
export const copyPage = (params) => request.get('/copy/page', { params })

// ---- 用户与角色 ----
export const userList = () => request.get('/system/user/list')
export const roleList = () => request.get('/system/role/list')

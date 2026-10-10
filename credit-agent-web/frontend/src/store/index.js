import Vue from 'vue'
import Vuex from 'vuex'
import { getToken, setToken, removeToken } from '@/utils/auth'

Vue.use(Vuex)

/** 全局状态：登录令牌 / 用户信息 / Agent 服务可用性 */
export default new Vuex.Store({
  state: {
    token: getToken(),
    userInfo: JSON.parse(localStorage.getItem('credit-web-user') || '{}'),
    agentAvailable: true,
    // Copilot 跨页指令通道：浮动窗写入，目标页面消费（_seq 单调递增保证重复指令也触发 watch）
    copilot: { customerKeyword: '', customerDetail: null, productName: '', _seq: 0 }
  },
  mutations: {
    SET_TOKEN(state, token) {
      state.token = token
      setToken(token)
    },
    SET_USER(state, user) {
      state.userInfo = user || {}
      localStorage.setItem('credit-web-user', JSON.stringify(state.userInfo))
    },
    RESET_LOGIN(state) {
      state.token = ''
      state.userInfo = {}
      removeToken()
      localStorage.removeItem('credit-web-user')
    },
    SET_AGENT_STATUS(state, available) {
      state.agentAvailable = available
    },
    COPILOT_CMD(state, payload) {
      state.copilot = { ...state.copilot, ...payload, _seq: state.copilot._seq + 1 }
    }
  },
  actions: {
    resetLogin({ commit }) {
      commit('RESET_LOGIN')
    },
    setAgentStatus({ commit }, available) {
      commit('SET_AGENT_STATUS', available)
    }
  },
  getters: {
    isAdmin: (state) => state.userInfo && state.userInfo.roleKey === 'admin',
    nickname: (state) => (state.userInfo && (state.userInfo.nickname || state.userInfo.username)) || ''
  }
})

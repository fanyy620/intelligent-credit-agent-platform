#!/usr/bin/env node
/**
 * 一键演示启动脚本（演示模式）：
 *   1) Python Agent 服务  —— credit-agent-platform/src/api_server.py（:8000）
 *   2) Mock 后端          —— credit-agent-web/mock-backend/server.py（:8080，上下文 /credit-web）
 *   3) Vite 开发服务器    —— 前端本体（默认 :5173，可透传 --port/--host）
 *
 * 用法：
 *   npm run dev                      # 三进程齐发
 *   npm run dev -- --port 7100       # 透传给 vite（端口冲突时换端口）
 *   npm run dev:vite                 # 只起前端（连真 SSM 后端时用）
 *
 * 环境变量：
 *   CREDIT_AGENT_URL   覆盖 Agent 地址（默认 http://127.0.0.1:8000）
 *   CREDIT_MOCK_PORT   覆盖 Mock 后端端口（默认 8080；改了要同步改 vite.config.js 的 proxy target）
 *   CREDIT_PYTHON      指定 Python 解释器路径（默认自动探测 python / python3）
 *
 * Ctrl+C 退出时会连同整棵子进程树一起清理（Windows 下用 taskkill /T）。
 */
'use strict'

const { spawn, spawnSync } = require('node:child_process')
const path = require('node:path')
const fs = require('node:fs')

// frontend/scripts/dev-all.js → 仓库根 = ../../
const ROOT = path.resolve(__dirname, '..', '..')
const AGENT_ENTRY = path.join(ROOT, '..', 'credit-agent-platform', 'src', 'api_server.py')
const MOCK_ENTRY = path.join(ROOT, 'mock-backend', 'server.py')
const VITE_ENTRY = path.join(ROOT, 'frontend', 'node_modules', 'vite', 'bin', 'vite.js')

const AGENT_URL = process.env.CREDIT_AGENT_URL || 'http://127.0.0.1:8000'
const MOCK_PORT = process.env.CREDIT_MOCK_PORT || '8080'

/** 探测可用的 Python 解释器（Windows 上 python 在 PATH 中；python3 兜底） */
function findPython() {
  if (process.env.CREDIT_PYTHON && fs.existsSync(process.env.CREDIT_PYTHON)) {
    return process.env.CREDIT_PYTHON
  }
  for (const cmd of ['python', 'python3']) {
    const probe = spawnSync(cmd, ['--version'], { stdio: 'pipe', shell: false })
    if (!probe.error && probe.status === 0) {
      return cmd
    }
  }
  // Kimi Work 托管 Python 兜底（预览环境 PATH 中可能没有 python）
  const managed = 'C:\\Users\\Fyy\\AppData\\Roaming\\kimi-desktop\\daimon-share\\daimon\\runtime\\python\\.venv\\Scripts\\python.exe'
  if (fs.existsSync(managed)) return managed
  if (process.platform === 'win32') {
    const where = spawnSync('where', ['python'], { stdio: 'pipe', shell: true })
    if (!where.error && where.status === 0) {
      const first = String(where.stdout).split(/\r?\n/)[0].trim()
      if (first && fs.existsSync(first)) return first
    }
  }
  return null
}

function assertFile(p, hint) {
  if (!fs.existsSync(p)) {
    console.error(`[dev-all] 找不到文件: ${p}`)
    console.error(`[dev-all] ${hint}`)
    process.exit(1)
  }
}

const children = []
let shuttingDown = false

function launch(name, command, args) {
  const child = spawn(command, args, { stdio: 'inherit', shell: false })
  child.on('error', (err) => {
    console.error(`[dev-all] ${name} 启动失败: ${err.message}`)
    shutdown(1)
  })
  child.on('exit', (code, signal) => {
    if (!shuttingDown) {
      console.error(`[dev-all] ${name} 意外退出 (code=${code}, signal=${signal})，正在关闭其余服务…`)
      shutdown(code || 1)
    }
  })
  children.push(child)
  return child
}

/** 结束整棵进程树（Windows: taskkill /T；POSIX: 信号） */
function killTree(child) {
  if (!child || child.killed) return
  try {
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore' })
    } else {
      child.kill('SIGTERM')
    }
  } catch { /* 已退出则忽略 */ }
}

function shutdown(code) {
  if (shuttingDown) return
  shuttingDown = true
  for (const c of children) killTree(c)
  // 给 taskkill 一点时间再退出，避免端口残留
  setTimeout(() => process.exit(code), 300)
}

process.on('SIGINT', () => shutdown(0))
process.on('SIGTERM', () => shutdown(0))
process.on('exit', () => { for (const c of children) killTree(c) })

function main() {
  assertFile(AGENT_ENTRY, '请确认 credit-agent-platform 与 credit-agent-web 同级目录。')
  assertFile(MOCK_ENTRY, 'mock-backend/server.py 缺失。')
  assertFile(VITE_ENTRY, '请先执行 npm install（在 frontend 目录下）。')

  const python = findPython()
  if (!python) {
    console.error('[dev-all] 未找到 Python 解释器（尝试过 python / python3 / where python）。')
    console.error('[dev-all] 请安装 Python 3.10+，或设置环境变量 CREDIT_PYTHON 指向解释器。')
    process.exit(1)
  }

  console.log('='.repeat(68))
  console.log('  智能信贷营销与咨询平台 · 演示模式（无需 JDK / MySQL / Redis）')
  console.log(`  Agent  : ${AGENT_URL}          （credit-agent-platform）`)
  console.log(`  Mock   : http://localhost:${MOCK_PORT}/credit-web （内存版 SSM 后端）`)
  console.log('  前端   : 见下方 vite 输出（/api 已代理到 Mock 后端）')
  console.log('  账号   : admin / 123456 · manager01 / 123456')
  console.log('='.repeat(68))

  launch('Agent 服务', python, [AGENT_ENTRY, '--port', '8000', '--host', '127.0.0.1'])
  launch('Mock 后端', python, [MOCK_ENTRY, '--port', MOCK_PORT, '--host', '::', '--agent', AGENT_URL])
  launch('Vite 前端', process.execPath, [VITE_ENTRY, ...process.argv.slice(2)])
}

main()

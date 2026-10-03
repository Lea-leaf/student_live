/**
 * 静态检查：找出「没有接住 reject」的 ElMessageBox 调用。
 *
 * **为什么需要这个脚本**
 *
 * Element Plus 的 `ElMessageBox.confirm/prompt/alert` 返回一个 Promise，
 * 而**用户用 × / ESC / 点遮罩关闭弹窗时它会 reject（reason 是 'cancel'）**。
 * 如果调用处既没有 `await`（在 try 里）也没有 `.catch()`，
 * 浏览器控制台就会冒出：
 *
 *     Uncaught (in promise) cancel
 *
 * 这是本项目实际踩到的 bug（6 处 alert 漏了 catch）。它不影响功能，
 * 但污染控制台，且新增代码时极易重新引入，所以用脚本卡住。
 *
 * **判定算法（行级扫描 + 括号深度）**
 *
 * 逐行累积「语句片段」：遇到 `ElMessageBox.xxx(` 开始记录，并跟踪括号深度；
 * 深度回到 0 后如果紧跟 `.then(` / `.catch(` 就继续累积（链式调用），
 * 直到遇到语句终止（`;`）或深度变负（走出当前块）。
 * 最后检查片段里有没有 `.catch`；`await` 开头的调用交给外层 try/catch，视为安全。
 *
 * 注：早期版本用「字符级配平找右括号」，会把链式 `.catch(` 的括号算进嵌套，
 * 导致起点错误、误报，已改为行级扫描。
 *
 * 用法：
 *     node scripts/check-messagebox.js              # 报告问题，有问题退出码 1
 *     node scripts/check-messagebox.js --fix-hint   # 额外打印修复建议
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SRC = path.resolve(__dirname, '..', 'src')

const METHODS = ['confirm', 'prompt', 'alert']
const CALL_RE = new RegExp(`ElMessageBox\\.(${METHODS.join('|')})\\s*\\(`)

/** 递归收集 .js / .vue 文件 */
function collect(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === 'dist') continue
      collect(full, out)
    } else if (/\.(js|vue)$/.test(entry.name)) {
      out.push(full)
    }
  }
  return out
}

/** 统计一行里括号的净变化（忽略字符串内的括号，粗略但足够） */
function depthDelta(line) {
  let delta = 0
  let quote = null
  let inTemplate = false
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i]
    const prev = line[i - 1]
    if (quote) { if (ch === quote && prev !== '\\') quote = null; continue }
    if (inTemplate) { if (ch === '`' && prev !== '\\') inTemplate = false; continue }
    if (ch === "'" || ch === '"') { quote = ch; continue }
    if (ch === '`') { inTemplate = true; continue }
    if (ch === '(') delta += 1
    else if (ch === ')') delta -= 1
  }
  return delta
}

function checkFile(file) {
  const lines = fs.readFileSync(file, 'utf8').split('\n')
  const problems = []

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const match = line.match(CALL_RE)
    if (!match) continue

    // await 开头的调用：由外层 try/catch 负责，跳过
    if (/await\s+$/.test(line.slice(0, match.index))) continue
    if (/await\s+ElMessageBox/.test(line)) continue

    // 累积整条语句：
    // 逐行加进 span 并跟踪括号深度；当深度回到 0 时，看**下一个非空字符**：
    //   - 是 `.` → 说明后面还有 .then/.catch 链式调用，继续累积；
    //   - 不是 `.` → 语句结束。
    // （早期版本用正则匹配 `)\s*\.\s*then`，因 `)` 与 `.then` 之间换行而失效 → 误报。）
    let span = ''
    let depth = 0
    let started = false
    let terminated = false

    outer:
    for (let j = i; j < lines.length && j < i + 30; j += 1) {
      const current = lines[j]
      const delta = depthDelta(current)

      // 上一行结束后已回到深度 0，检查本行开头是否继续链式调用
      if (started && depth === 0) {
        const head = current.replace(/^\s+/, '')
        if (!head.startsWith('.')) {
          terminated = true
          break
        }
      }

      span += (j === i ? '' : '\n') + current
      depth += delta
      if (!started && depth > 0) started = true

      if (started && depth === 0) {
        // 本行剩余部分是否以 `.` 续接（同一行内的链式调用）
        const tail = current.slice(current.lastIndexOf(')') + 1).trim()
        if (tail.startsWith('.')) continue

        // 看下一行是否以 `.` 开头
        const next = (lines[j + 1] || '').replace(/^\s+/, '')
        if (next.startsWith('.')) continue

        terminated = true
        break outer
      }
      if (depth < 0) { terminated = true; break }
    }

    if (!terminated) continue          // 语句没扫完（异常写法），保守跳过
    if (/\.catch\s*\(/.test(span)) continue

    problems.push({
      line: i + 1,
      method: match[1],
      snippet: span.replace(/\s+/g, ' ').slice(0, 90),
    })
  }
  return problems
}

function main() {
  const showHint = process.argv.includes('--fix-hint')
  const files = collect(SRC)
  let total = 0

  for (const file of files) {
    const problems = checkFile(file)
    if (!problems.length) continue
    total += problems.length
    console.log(`\n${path.relative(path.resolve(__dirname, '..'), file)}`)
    for (const p of problems) {
      console.log(`  第 ${p.line} 行  ElMessageBox.${p.method}(...)  未接住 reject`)
      console.log(`      ${p.snippet}...`)
    }
  }

  console.log(`\n检查了 ${files.length} 个文件。`)
  if (total === 0) {
    console.log('未发现未处理的 ElMessageBox 调用 ✓')
    return 0
  }

  console.log(`发现 ${total} 处未接住 reject 的调用。`)
  if (showHint) {
    console.log('\n修法（二选一）：')
    console.log('  1) 加 await 并放在 try 里：')
    console.log('       try { await ElMessageBox.alert(...) } catch { /* 用户关闭 */ }')
    console.log('  2) 链式吞掉：')
    console.log('       ElMessageBox.alert(...).catch(() => {})')
  }
  return 1
}

process.exit(main())

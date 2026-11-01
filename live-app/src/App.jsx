import { useState, useRef, useEffect } from 'react'
import { Canvas } from '@react-three/fiber'
import { Environment, Float, Stars } from '@react-three/drei'
import Robot from './components/Robot.jsx'
import { SpaceBackground } from './components/SpaceBackground.jsx'
import './App.css'

// Split assistant text into prose + fenced code segments. During streaming a
// trailing unclosed ``` fence is treated as a live-growing code block.
function parseRich(text) {
  const parts = []
  const rx = /```(\w*)\n?([\s\S]*?)```/g
  let last = 0, m, k = 0
  while ((m = rx.exec(text)) !== null) {
    if (m.index > last) parts.push({ t: 'txt', v: text.slice(last, m.index) })
    parts.push({ t: 'code', lang: m[1] || 'python', v: m[2], idx: k++ })
    last = m.index + m[0].length
  }
  if (last < text.length) {
    const tail = text.slice(last)
    const opens = (text.match(/```/g) || []).length
    if (opens % 2 === 1) {
      const nl = tail.indexOf('\n')
      const rawLang = nl > -1 && nl < 16 ? tail.slice(0, nl) : ''
      const lang = rawLang.replace(/`/g, '').trim() || 'python'
      parts.push({ t: 'code', lang, v: rawLang ? tail.slice(nl + 1) : tail, idx: k++, live: true })
    } else {
      parts.push({ t: 'txt', v: tail })
    }
  }
  return parts
}

function CodeBlock({ seg, run, runState, onFix, onArtifact }) {
  const [copied, setCopied] = useState(false)
  const lang = (seg.lang || '').toLowerCase()
  const isPy = /^(python|py)$/.test(lang)
  const isJs = /^(js|javascript|node)$/.test(lang)
  const isHtml = /^(html)$/.test(lang)
  const res = runState?.result
  return (
    <div className={`code-block ${seg.live ? 'live' : ''}`} dir="ltr">
      <div className="code-head">
        <span className="code-lang">{seg.live ? seg.lang + ' • بث حي...' : seg.lang}</span>
        <div className="code-actions">
          <button title="نسخ" onClick={() => { navigator.clipboard.writeText(seg.v); setCopied(true); setTimeout(() => setCopied(false), 1200) }}>
            {copied ? '✅' : '📋'}
          </button>
          {isPy && (
            <button className="run-btn" title="تنفيذ حي" onClick={() => run(seg.idx, seg.v, 'python')} disabled={runState?.loading}>
              {runState?.loading ? '⏳ يعمل...' : '▶️ تشغيل'}
            </button>
          )}
          {isJs && (
            <button className="run-btn" title="تنفيذ حي عبر Node.js" onClick={() => run(seg.idx, seg.v, 'javascript')} disabled={runState?.loading}>
              {runState?.loading ? '⏳ يعمل...' : '▶️ تشغيل JS'}
            </button>
          )}
          {isHtml && (
            <button className="artifact-btn" title="تشغيل كتطبيق حي" onClick={() => onArtifact(seg.v)}>
              🚀 تشغيل كتطبيق
            </button>
          )}
        </div>
      </div>
      <pre><code>{seg.v}</code></pre>
      {(runState?.loading || res) && (
        <div className={`code-output ${res && !res.ok ? 'err' : 'ok'}`}>
          {runState?.loading ? <div className="out-head">⏳ جاري التنفيذ...</div> : (
            <>
              <div className="out-head">
                {res?.ok ? '✅ نُفِّذ بنجاح' : '❌ فشل'} • {res?.duration_ms}ms
                {!res?.ok && res?.stderr && (
                  <button className="fix-btn" onClick={() => onFix(seg.v, res.stderr)}>🛠️ صحّح تلقائياً</button>
                )}
              </div>
              <pre>{res?.stdout || res?.stderr || '(لا مخرجات)'}</pre>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// Full multi-file project delivery — the agent planned, generated and
// packaged a complete project; here is its tree, live preview and ZIP.
function ProjectCard({ p, onPreview }) {
  return (
    <div className="project-card">
      <div className="project-head">🏗️ {p.name} — {p.files.length} ملفات جاهزة</div>
      <div className="project-files">
        {p.files.map(f => <span key={f} className="project-file">{f}</span>)}
      </div>
      <div className="project-actions">
        {p.preview && (
          <button className="preview-btn" onClick={() => onPreview('http://127.0.0.1:8000' + p.preview)}>
            🚀 معاينة حية
          </button>
        )}
        <a className="zip-link" href={'http://127.0.0.1:8000' + p.zip}>⬇️ تحميل المشروع ZIP</a>
      </div>
    </div>
  )
}

// Agent-loop phase icons — the user SEES which phase of the build is running
function stageIcon(s) {
  if (s.includes('عصف')) return '🧠 '
  if (s.includes('أخطط') || s.includes('الخطة')) return '🗺️ '
  if (s.includes('أفحص')) return '🔍 '
  if (s.includes('أعيد')) return '🔁 '
  if (s.includes('شف')) return '🩺 '
  return '⚡ '
}

export default function App() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      text: 'أهلاً بك في وحدة القيادة المركزية لـ OSS Work.\n\nأنا OS_V1، مساعدك الذكي المتكامل. لقد تم تحديث أنظمتي ودرعي بالكامل لتقديم تجربة فائقة الذكاء.\n\nأستطيع مساعدتك في:\n• التحليل الهندسي المتقدم\n• الهندسة العكسية للبرمجيات\n• البرمجة والعلوم المعقدة\n• الأمن السيبراني\n\nما هي المهمة التي تود البدء بها؟',
      time: new Date().toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' })
    }
  ])
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [stage, setStage] = useState('')
  const [robotMood, setRobotMood] = useState('idle')
  const [showSettings, setShowSettings] = useState(false)
  const [cloudCfg, setCloudCfg] = useState({ active: false, providers: {} })
  const [gwState, setGwState] = useState(null)
  const [agentMode, setAgentMode] = useState(false)
  const [deviceMode, setDeviceMode] = useState('safe')
  const [teamMode, setTeamMode] = useState(false)
  const [showMedia, setShowMedia] = useState(false)
  const [mediaItems, setMediaItems] = useState([])
  const [mediaLoading, setMediaLoading] = useState(false)
  const [showSec, setShowSec] = useState(false)
  const [secPath, setSecPath] = useState('')
  const [secLoading, setSecLoading] = useState(false)
  const [secRes, setSecRes] = useState(null)
  const [providersGuide, setProvidersGuide] = useState(null)
  const [newKey, setNewKey] = useState('')
  const [issuing, setIssuing] = useState(false)

  async function issueKey() {
    setIssuing(true)
    try {
      const r = await fetch('http://127.0.0.1:8000/api/v1/gateway/issue-key', { method: 'POST' })
      const d = await r.json()
      if (d.ok) setNewKey(d.key)
    } catch { /* الخادم غير متاح */ }
    finally { setIssuing(false) }
  }
  const [cfgProvider, setCfgProvider] = useState('gemini')
  const [cfgKey, setCfgKey] = useState('')
  const [cfgModel, setCfgModel] = useState('')
  const [cfgStatus, setCfgStatus] = useState('')
  const [sessionId] = useState(() => `session_${Date.now()}`)
  const [runs, setRuns] = useState({})
  const [artifact, setArtifact] = useState(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  // Load cloud config status once
  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/v1/config')
      .then(r => r.json())
      .then(d => setCloudCfg(d))
      .catch(() => {})
    // Provider Gateway pool: the bandit's live view of the world
    fetch('http://127.0.0.1:8000/api/v1/gateway/status')
      .then(r => r.json())
      .then(d => { if (d.ok) setGwState(d) })
      .catch(() => {})
    // خريطة استحضار المفاتيح: كل مزود بمصدر مفتاحه
    fetch('http://127.0.0.1:8000/api/v1/providers')
      .then(r => r.json())
      .then(d => { if (d.ok) setProvidersGuide(d) })
      .catch(() => {})
  }, [])

  async function openMedia() {
    setShowMedia(true)
    setMediaLoading(true)
    try {
      const r = await fetch('http://127.0.0.1:8000/api/v1/media/list')
      const d = await r.json()
      const items = d.ok ? (d.list || '').split('\n').filter(l => l.includes(' — ')).map(line => {
        const name = line.split(' — ')[0].trim()
        const isVid = /\.(webp|gif|mp4)$/i.test(name)
        return { name, kind: isVid ? 'video' : 'image',
                 url: `http://127.0.0.1:8000/api/v1/media/file/${name}` }
      }) : []
      setMediaItems(items)
    } catch { setMediaItems([]) }
    finally { setMediaLoading(false) }
  }

  async function runSecScan() {
    setSecLoading(true)
    setSecRes(null)
    try {
      const r = await fetch('http://127.0.0.1:8000/api/v1/security/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ path: secPath })
      })
      setSecRes(await r.json())
    } catch {
      setSecRes({ ok: false, message: 'تعذر الوصول للخادم' })
    }
    finally { setSecLoading(false) }
  }

  async function saveCloudConfig() {
    setCfgStatus('جاري فحص المفتاح...')
    try {
      const resp = await fetch('http://127.0.0.1:8000/api/v1/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ provider: cfgProvider, key: cfgKey, model: cfgModel })
      })
      const d = await resp.json()
      setCfgStatus(d.message || (d.ok ? 'تم!' : 'فشل'))
      if (d.ok) {
        setCloudCfg(prev => ({ ...prev, active: true, provider: cfgProvider }))
        setRobotMood('happy')
        setTimeout(() => setShowSettings(false), 1800)
      }
    } catch {
      setCfgStatus('تعذر الوصول للخادم — تأكد أنه يعمل')
    }
  }

  async function runCode(msgId, idx, code, language = 'python') {
    setRuns(prev => ({ ...prev, [msgId]: { ...(prev[msgId] || {}), [idx]: { loading: true } } }))
    try {
      const r = await fetch('http://127.0.0.1:8000/api/v1/code/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ code, language })
      })
      const d = await r.json()
      setRuns(prev => ({ ...prev, [msgId]: { ...(prev[msgId] || {}), [idx]: { result: d } } }))
    } catch {
      setRuns(prev => ({ ...prev, [msgId]: { ...(prev[msgId] || {}), [idx]: { result: { ok: false, stderr: 'تعذر الوصول للخادم', exit: -1 } } } }))
    }
  }

  async function openArtifact(html) {
    setArtifact({ loading: true })
    try {
      const r = await fetch('http://127.0.0.1:8000/api/v1/artifact/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ html, title: 'OS_V1' })
      })
      const d = await r.json()
      setArtifact(d.ok ? { url: 'http://127.0.0.1:8000' + d.url } : { error: d.message || 'فشل إنشاء التطبيق' })
    } catch {
      setArtifact({ error: 'تعذر الوصول للخادم' })
    }
  }

  async function fixCode(code, stderr) {
    sendMessage(`صحح هذا الكود الذي فشل:\n\`\`\`python\n${code}\n\`\`\`\nرسالة الخطأ:\n${stderr}`)
  }

  async function sendMessage(text, opts = {}) {
    if (!text.trim() || isTyping) return
    const now = () => new Date().toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' })
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', text, time: now() }])
    setInput('')
    setIsTyping(true)
    setStage('')
    setRobotMood('thinking')

    // الوسائط تحتاج أدوات الوكيل — التفعيل تلقائي وشفاف عند نية وسائط
    // (جذور قصيرة تلتقط الاشتقاقات: صورة/صور، فيديو/الفيديو، مقطعاً، رسم/ارسم...)
    let useAgent = opts.agent ?? agentMode
    if (!useAgent && /(صور|فيد|مقطع|أنيميشن|انيميشن|رسم|شعار|لوغو|avatar|logo)/i.test(text)) {
      useAgent = true
      setAgentMode(true)
      setStage('🖼️ فُعّل وضع الوكيل تلقائياً — الوسائط تحتاج أدواته الحقيقية')
    }

    const botId = Date.now() + 1
    // DeepSeek-style streaming: assistant bubble appears with the first token
    let fullText = ''
    let sources = []
    let engineTag = ''
    let botAdded = false
    const ensureBot = () => {
      if (botAdded) return
      botAdded = true
      setStage('')
      setMessages(prev => [...prev, { id: botId, role: 'assistant', text: '', time: now(), engine: '', sources: [] }])
    }

    try {
      const endpoint = useAgent ? 'http://127.0.0.1:8000/api/v1/agent/run' : 'http://127.0.0.1:8000/api/v1/chat/stream'
      const body = useAgent
        ? { task: text, session_id: sessionId, device: deviceMode,
            mode: opts.mode ?? (teamMode ? 'team' : 'solo') }
        : { message: text, model: 'os_v1', session_id: sessionId }
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify(body)
      })
      if (!resp.ok || !resp.body) throw new Error('stream unavailable')

      // Read the SSE stream token by token
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const events = buf.split('\n\n')
        buf = events.pop()
        for (const ev of events) {
          if (!ev.startsWith('data: ')) continue
          let evt
          try { evt = JSON.parse(ev.slice(6)) } catch { continue }
          if (evt.type === 'status') {
            setStage(evt.text || '')
          } else if (evt.type === 'agent_step') {
            // live tool step: the agent is REALLY executing something
            const mark = evt.ok ? '✓' : '✗'
            const prev = evt.preview?.command || evt.preview?.path || evt.preview?.pattern || evt.preview?.query || evt.preview?.name || ''
            setStage(`🤖 خطوة ${evt.step}: ${evt.tool} ${mark}${prev ? ` — ${String(prev).slice(0, 60)}` : ''}`)
          } else if (evt.type === 'sources') {
            sources = evt.sources || []
          } else if (evt.type === 'delta') {
            ensureBot()
            fullText += evt.text
            setMessages(prev => prev.map(m => m.id === botId ? { ...m, text: fullText } : m))
          } else if (evt.type === 'replace') {
            // instant draft was shown — clear it so the refined answer replaces it
            fullText = ''
            botAdded = false
            setMessages(prev => prev.filter(m => m.id !== botId))
          } else if (evt.type === 'project') {
            // full multi-file project built — attach the delivery card
            setMessages(prev => prev.map(m => m.id === botId ? { ...m, project: evt } : m))
          } else if (evt.type === 'done') {
            engineTag = evt.engine || engineTag
            if (evt.sources && evt.sources.length) sources = evt.sources
          }
        }
      }
      if (!botAdded && !fullText) throw new Error('empty stream')
      setMessages(prev => prev.map(m => m.id === botId
        ? { ...m, text: fullText || 'لم يصل رد من المحرك.', engine: engineTag, sources }
        : m))
      setRobotMood('happy')
    } catch (e) {
      // Stream path failed — try the plain endpoint before giving up
      try {
        const resp = await fetch('http://127.0.0.1:8000/api/v1/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json; charset=utf-8' },
          body: JSON.stringify({ message: text, model: 'os_v1', session_id: sessionId })
        })
        const data = await resp.json()
        setMessages(prev => [...prev, {
          id: botId,
          role: 'assistant',
          text: data.reply || data.message || 'تم الاستلام.',
          time: now(),
          engine: data.engine,
          sources: data.sources || []
        }])
        setRobotMood('happy')
      } catch (e2) {
        // Backend fully offline — honest message, no fake intelligence
        setMessages(prev => [...prev, {
          id: botId,
          role: 'assistant',
          text: '⚠️ الخادم غير متصل حالياً. شغّل oss_work_live.py ثم أعد الإرسال.',
          time: now(),
          engine: 'offline'
        }])
        setRobotMood('idle')
      }
    } finally {
      setIsTyping(false)
      setStage('')
      setTimeout(() => setRobotMood('idle'), 3000)
    }
  }

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="logo-area">
          <div className="logo-icon">
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
              <rect x="2" y="2" width="24" height="24" rx="6" stroke="#00d4ff" strokeWidth="2.5"/>
              <path d="M 8 10 L 20 10 M 8 15 L 20 15 M 8 20 L 14 20" stroke="#00d4ff" strokeWidth="2.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="logo-name">OSS Work</span>
          <span className="logo-model">OS_V1</span>
        </div>
        <div className="header-status">
          {gwState && (
            <button className="gw-chip" onClick={() => setShowSettings(true)}
                    title={`استراتيجية ${gwState.strategy} — اضغط للتفاصيل`}>
              🏛️ بوابة OS_V — {gwState.members.length} مزودين
            </button>
          )}
          <span className={`status-dot ${robotMood === 'thinking' ? 'thinking' : ''}`} />
          <span>{robotMood === 'thinking' ? 'مزامنة البيانات...' : (cloudCfg.active ? '⚡ OS_V1 — ذكاء حدودي' : 'OS_V1 — وضع محلي')}</span>
          <button className="tool-btn" onClick={openMedia} title="معرض الوسائط المولّدة — الصور والمقاطع">🖼️</button>
          <button className="tool-btn" onClick={() => { setShowSec(true); setSecRes(null) }} title="فحص أمني شامل لأي مشروع">🛡️</button>
          <button className="settings-btn" onClick={() => setShowSettings(true)} title="إعدادات الذكاء السحابي">⚙️</button>
        </div>
      </header>

      {/* Cloud settings modal */}
      {showSettings && (
        <div className="modal-backdrop" onClick={() => setShowSettings(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>⚙️ ربط OS_V1 بذكاء حدودي سحابي</h3>
            <p className="modal-hint">
              للوصول لذكاء بمستوى Gemini/GPT بسرعته: احصل على مفتاح مجاني من أحد المزودين،
              الصقه هنا مرة واحدة — يُحفظ في جهازك فقط (ملف محلي، لا يُرسل لأي مكان إلا للمزود).
            </p>
            <label>المزود:</label>
            <select value={cfgProvider} onChange={e => { setCfgProvider(e.target.value); setCfgModel('') }}>
              {Object.entries(cloudCfg.providers || {
                gemini: 'Google Gemini — مجاني من aistudio.google.com/apikey',
                groq: 'Groq — مجاني من console.groq.com/keys',
                openrouter: 'OpenRouter — نماذج :free',
                deepseek: 'DeepSeek API'
              }).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
            <label>المفتاح (API Key):</label>
            <input type="password" value={cfgKey} onChange={e => setCfgKey(e.target.value)}
                   placeholder="الصق المفتاح هنا" dir="ltr" />
            <label>النموذج (اختياري — اتركه فارغاً للافتراضي):</label>
            <input type="text" value={cfgModel} onChange={e => setCfgModel(e.target.value)}
                   placeholder="مثال: gemini-2.0-flash" dir="ltr" />
            <button className="modal-save" onClick={saveCloudConfig} disabled={!cfgKey.trim()}>
              حفظ وفحص المفتاح
            </button>
            {cfgStatus && <div className="modal-status">{cfgStatus}</div>}

            {gwState && (
              <div className="gw-panel">
                <h4>🏛️ بوابة OS_V — مخزون المزودين</h4>
                <p className="gw-hint">
                  مفتاحك الواحد يوصل بك لمخزون يجمع المزودين من كل الجهات — البوابة تتعلم من
                  كل نداء (سرعة/نجاح/حصص) وتوجّه تلقائياً. استراتيجية التوجيه: <b>{gwState.strategy}</b>
                </p>
                <div className="gw-members">
                  {gwState.members.map(m => (
                    <div key={m.provider} className="gw-member">
                      <span className="gw-name">{m.provider}</span>
                      <span className={`gw-badge ${m.failures > m.successes ? 'bad' : 'good'}`}>
                        {m.failures > m.successes ? 'متعب' : 'سليم'}
                      </span>
                      <span className="gw-stats">
                        {m.successes}✓ / {m.failures}✗
                        {m.avg_ttfb_ms > 0 && ` · ${(m.avg_ttfb_ms / 1000).toFixed(1)}s`}
                        {m.tok_per_sec > 0 && ` · ${m.tok_per_sec} رمز/ث`}
                        {m.cooldown_s > 0 && ` · تبريد ${m.cooldown_s}ث`}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="gw-keybox">
                  <button className="gw-issue" onClick={issueKey} disabled={issuing}>
                    {issuing ? 'جاري الإصدار...' : '🔑 إصدار مفتاح os_v موحد'}
                  </button>
                  {newKey && (
                    <div className="gw-key-reveal">
                      <code dir="ltr">{newKey}</code>
                      <p>انسخه الآن — يُخزَّن مُجزَّأً ولن يُعرض مرة أخرى. استخدمه في أي أداة متوافقة مع OpenAI على العنوان <code dir="ltr">http://127.0.0.1:8000/v1</code></p>
                    </div>
                  )}
                </div>
              </div>
            )}
            {providersGuide && (
              <div className="gw-panel">
                <h4>🗺️ استحضار المفاتيح — {providersGuide.count} مزوداً</h4>
                <p className="gw-hint">
                  لكل مزود مصدر مفتاحه الرسمي — اضغط الرابط لتحصل على مفتاحك المجاني مباشرة،
                  ثم الصقه في النموذج أعلاه.
                </p>
                <div className="prov-list">
                  {providersGuide.providers.map(p => (
                    <div key={p.name} className="prov-row" title={p.label}>
                      <span className="prov-name">{p.name}</span>
                      <span className="prov-model" dir="ltr">{p.default_model}</span>
                      {/^https?:/.test(p.key_url) ? (
                        <a className="prov-link" href={p.key_url} target="_blank" rel="noreferrer">الحصول على المفتاح ↗</a>
                      ) : (
                        <span className="prov-auto">{p.key_url}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <button className="modal-close" onClick={() => setShowSettings(false)}>إغلاق</button>
          </div>
        </div>
      )}

      {/* Live artifact viewer — games/apps built by OS_V1 run right here */}
      {artifact && (
        <div className="modal-backdrop" onClick={() => setArtifact(null)}>
          <div className="artifact-modal" onClick={e => e.stopPropagation()}>
            <div className="artifact-head">
              <span>🚀 تطبيق حي بنيه OS_V1 الآن</span>
              <div className="artifact-tools">
                {artifact.url && <a href={artifact.url} target="_blank" rel="noreferrer">فتح في تبويب ↗</a>}
                <button onClick={() => setArtifact(null)}>✕</button>
              </div>
            </div>
            {artifact.loading && <div className="artifact-note">أجهّز التطبيق...</div>}
            {artifact.error && <div className="artifact-note err">{artifact.error}</div>}
            {artifact.url && (
              <iframe src={artifact.url} title="OS_V1 artifact"
                      sandbox="allow-scripts allow-same-origin allow-modals" />
            )}
          </div>
        </div>
      )}

      {/* Media gallery — images/videos the agent really generated */}
      {showMedia && (
        <div className="modal-backdrop" onClick={() => setShowMedia(false)}>
          <div className="modal media-modal" onClick={e => e.stopPropagation()}>
            <h3>🖼️ معرض وسائط OS_V1 — مولّدة فعلياً</h3>
            <p className="modal-hint">كل عنصر هنا ملف حقيقي على القرص في مجلد media — الصور مولّدة من أوصاف عربية، والمقاطع مركّبة من مشاهد مولّدة (بصدق: إطارات متحركة لا نموذج فيديو).</p>
            <div className="media-toolbar">
              <button className="gw-issue" onClick={openMedia} disabled={mediaLoading}>
                {mediaLoading ? 'جاري التحديث...' : '🔄 تحديث'}
              </button>
              <button className="modal-close" onClick={() => setShowMedia(false)}>إغلاق</button>
            </div>
            {mediaLoading && <div className="modal-status">جاري جلب القائمة...</div>}
            {!mediaLoading && mediaItems.length === 0 && (
              <div className="modal-status">لا وسائط بعد — اطلب من الوكيل «أنشئ صورة...» وسظهر هنا</div>
            )}
            <div className="media-grid">
              {mediaItems.map(m => m.name.endsWith('.mp4') ? (
                <div key={m.name} className="media-card">
                  <video src={m.url} controls muted loop className="media-vid" />
                  <span className="media-name" dir="ltr">🎬 {m.name}</span>
                </div>
              ) : m.kind === 'video' ? (
                <a key={m.name} className="media-card" href={m.url} target="_blank" rel="noreferrer">
                  <img src={m.url} alt={m.name} className="media-vid" />
                  <span className="media-name" dir="ltr">🎬 {m.name}</span>
                </a>
              ) : (
                <a key={m.name} className="media-card" href={m.url} target="_blank" rel="noreferrer">
                  <img src={m.url} alt={m.name} loading="lazy" />
                  <span className="media-name" dir="ltr">{m.name}</span>
                </a>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Security scanner — the تأمين lane, read-only static analysis */}
      {showSec && (
        <div className="modal-backdrop" onClick={() => setShowSec(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>🛡️ الفحص الأمني — اختبار اختراق ثابت</h3>
            <p className="modal-hint">
              فحص قراءة فقط لكل الملفات: أسرار مكشوفة، حقن SQL، أوامر خطر، TLS معطل —
              بأدلة ملف:سطر وترتيب حسب الخطورة. اتركه فارغاً لفحص مشروع OS_V1 نفسه.
            </p>
            <label>مسار المشروع (اختياري):</label>
            <input type="text" value={secPath} onChange={e => setSecPath(e.target.value)}
                   placeholder="C:\path\to\project — فارغ = فحص OS_V1 نفسه" dir="ltr" />
            <button className="modal-save" onClick={runSecScan} disabled={secLoading}>
              {secLoading ? 'جاري الفحص...' : '🔍 افحص الآن'}
            </button>
            {secLoading && <div className="modal-status">يفحص الملفات بـ14 قاعدة أمنية...</div>}
            {secRes && secRes.ok && (
              <div className="sec-result">
                <div className={`sec-badge ${secRes.clean ? 'clean' : 'dirty'}`}>
                  {secRes.clean
                    ? `✅ نظيف مؤكد — ${secRes.files_scanned} ملفاً بلا أي إشارة`
                    : `🛡️ ${Object.entries(secRes.counts).map(([k, v]) => `${k}: ${v}`).join(' · ')}`}
                </div>
                <pre className="sec-report">{secRes.report}</pre>
              </div>
            )}
            {secRes && !secRes.ok && <div className="modal-status">{secRes.message || 'فشل الفحص'}</div>}
            <button className="modal-close" onClick={() => setShowSec(false)}>إغلاق</button>
          </div>
        </div>
      )}

      {/* Main area */}
      <div className="main-area">
        {/* 3D Background Canvas (Lab Environment) */}
        <div className="canvas-container">
          <Canvas
            camera={{ position: [0, 0, 7], fov: 45 }}
            gl={{ antialias: true, alpha: true }}
          >
            <ambientLight intensity={0.15} />
            <Stars radius={100} depth={50} count={3000} factor={4} saturation={0} fade speed={1} />
            <SpaceBackground />
            <Float speed={1.5} rotationIntensity={0.15} floatIntensity={0.4}>
              <Robot mood={robotMood} />
            </Float>
            <Environment preset="night" />
          </Canvas>
        </div>

        {/* Full-screen HUD chat overlay */}
        <div className="chat-overlay">
          {/* Top bar */}
          <div className="chat-topbar">
            <div className="chat-topbar-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              <span>نظام المحادثة المتقدم — OS_V1</span>
            </div>
            <div className={`mood-badge ${robotMood === 'thinking' ? 'thinking' : ''}`}>
              <span className="dot" />
              <span>{robotMood === 'thinking' ? 'جاري التحليل...' : 'جاهز للعمل'}</span>
            </div>
          </div>

          {/* Messages Area */}
          <div className="messages-area">
            {messages.map(msg => (
              <div key={msg.id} className={`message ${msg.role}`}>
                <div className="msg-avatar">
                  {msg.role === 'assistant' ? 'OS' : 'US'}
                </div>
                <div className="msg-bubble">
                  <div className="msg-text">
                    {parseRich(msg.text).map((p, i) => p.t === 'code' ? (
                      <CodeBlock key={i} seg={p} run={(idx, code, lang) => runCode(msg.id, idx, code, lang)}
                                 runState={(runs[msg.id] || {})[p.idx]} onFix={fixCode} onArtifact={openArtifact} />
                    ) : (
                      <span key={i} style={{ whiteSpace: 'pre-wrap' }}>{p.v}</span>
                    ))}
                  </div>
                  {msg.project && (
                    <ProjectCard p={msg.project} onPreview={url => setArtifact({ url })} />
                  )}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="msg-sources">
                      {msg.sources.slice(0, 4).map((s, i) => (
                        <span key={i} className="source-chip">🔗 {s.length > 34 ? s.slice(0, 34) + '…' : s}</span>
                      ))}
                    </div>
                  )}
                  <div className="msg-time">{msg.time}{msg.engine ? ` • ${msg.engine}` : ''}</div>
                </div>
              </div>
            ))}

            {isTyping && (
              <div className="message assistant typing">
                <div className="msg-avatar">OS</div>
                <div className="msg-bubble typing-dots">
                  <span /><span /><span />
                  {stage && <span className="typing-stage">{stageIcon(stage)}{stage}</span>}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick actions bar */}
          <div className="quick-bar">
            <button onClick={() => sendMessage('ابني لي لعبة الأفعى snake بملف HTML واحد كامل بواجهة عربية جميلة')} disabled={isTyping}>🎮 ابنِ لعبة</button>
            <button onClick={() => sendMessage('اكتب كود بايثون يحل برج هانوي مع تنفيذ كامل وطباعة الخطوات')} disabled={isTyping}>🗼 برج هانوي</button>
            <button onClick={() => sendMessage('أنشئ صورة لشعار OS_V1: دماغ متوهج أزرق داخل هندسة معمارية ذهبية، مينيمال')} disabled={isTyping}>🎨 صورة</button>
            <button onClick={() => sendMessage('أنشئ فيديو حقيقياً: نابليون بونابرت بقبعة بيكونت ومعطفه الرمادي يسير على سطح سفينة حربية وسط جنوده المتصطفين، أمواج وغروب ذهبي، سينمائي')} disabled={isTyping}>🎬 فيديو حقيقي</button>
            <button onClick={() => sendMessage('ولّد صورة سينمائية لنابليون على سطح سفينة عند الغروب ثم طبق عليها حركة crash_zoom ثم أنشئ رؤيات جينجتسو من الصورة نفسها وأعطني مسارات كل الملفات')} disabled={isTyping}>🎥 حركة سينمائية</button>
            <button onClick={() => sendMessage('ابنِ مشروعاً كاملاً بفريق متوازٍ: صفحة هبوط HTML عربية احترافية + وحدة بايثون لحساب فاتورة ضريبية مع اختباراتها + ملف README عربي يشرح الكل — نفذ الأجزاء الثلاثة بالتوازي', { agent: true, mode: 'team' })} disabled={isTyping}>👥 مشروع بفريق</button>
            <button onClick={() => sendMessage('أمّن مشروع OS_V1: نفّذ security_scan وأصلح كل ثغرة تجدها ثم أعد الفحص حتى النظافة الكاملة')} disabled={isTyping}>🛡️ أمّن المشروع</button>
            <button onClick={() => sendMessage('ابني لي مشروع متجر إلكتروني كامل بعدة ملفات')} disabled={isTyping}>🏗️ متجر إلكتروني كامل</button>
          </div>

          {/* Input field */}
          <form className="input-area" onSubmit={e => { e.preventDefault(); sendMessage(input) }}>
            <div className="agent-cluster">
              <button type="button" className={`agent-toggle ${agentMode ? 'on' : ''}`}
                      onClick={() => setAgentMode(v => !v)}
                      title="وضع الوكيل: أدوات حقيقية (تنفيذ/ملفات/بحث/وسائط/أمان) داخل مساحة عمل">
                🤖
              </button>
              {agentMode && (
                <button type="button" className={`device-pill ${teamMode ? 'full' : 'safe'}`}
                        onClick={() => setTeamMode(v => !v)}
                        title="سرب الوكلاء: تفكيك المهمة إلى مسارات متوازية يعمل عليها عدة وكلاء آنياً — للمشاريع متعددة الأجزاء">
                  {teamMode ? '👥 سرب' : '👤 فردي'}
                </button>
              )}
              {agentMode && (
                <button type="button" className={`device-pill ${deviceMode}`}
                        onClick={() => setDeviceMode(m => m === 'safe' ? 'full' : 'safe')}
                        title="آمن: الملفات والتنفيذ داخل مساحة العمل | كامل: تحكم بالجهاز (إشعارات/عمليات) — يُسأل عند الخطرة">
                  {deviceMode === 'safe' ? '🛡️ آمن' : '⚡ كامل'}                </button>
              )}
            </div>
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) } }}
              placeholder="اطلب أي شيء من OS_V1... (Enter للإرسال)"
              className="chat-input"
              disabled={isTyping}
              autoFocus
            />
            <button type="submit" className="send-btn" disabled={isTyping || !input.trim()}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </form>
        </div>
      </div>

      {/* Footer */}
      <footer className="app-footer">
        <span>نظام OSS Work v9.0 AgentEngine — OS_V1 (عصف ذهني + تخطيط + بناء توازي + فحص مصيري وشفاء ذاتي)</span>
        <span>Osama-SysEng © 2026</span>
      </footer>
    </div>
  )
}

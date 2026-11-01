import { useRef, useEffect } from 'react'
import './Chat.css'

export default function ChatPanel({ messages, input, isTyping, onInputChange, onSend, robotMood }) {
  const inputRef = useRef(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  function handleSubmit(e) {
    e.preventDefault()
    onSend(input)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend(input)
    }
  }

  return (
    <div className="chat-panel">
      {/* Panel header */}
      <div className="chat-header">
        <div className="chat-title">
          <span className="chat-title-icon">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 4h12M2 8h8M2 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </span>
          <span>محادثات OS_V1</span>
        </div>
        <div className={`mood-indicator mood-${robotMood}`}>
          <span className="mood-dot" />
          <span>{
            robotMood === 'thinking' ? 'تحليل...' :
            robotMood === 'happy' ? 'مبتهج' :
            robotMood === 'listening' ? 'يستمع' :
            'جاهز'
          }</span>
        </div>
      </div>

      {/* Messages */}
      <div className="messages-container">
        {messages.map(msg => (
          <div key={msg.id} className={`message ${msg.role}`}>
            {msg.role === 'assistant' && (
              <div className="msg-avatar">
                <svg width="18" height="18" viewBox="0 0 28 28" fill="none">
                  <rect x="2" y="2" width="24" height="24" rx="6" stroke="currentColor" strokeWidth="2"/>
                  <circle cx="9" cy="11" r="2" fill="currentColor"/>
                  <circle cx="19" cy="11" r="2" fill="currentColor"/>
                  <path d="M 8 18 Q 14 22 20 18" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round"/>
                </svg>
              </div>
            )}
            <div className="msg-bubble">
              <div className="msg-text">{msg.text}</div>
              <div className="msg-time">{msg.time}</div>
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="message assistant typing">
            <div className="msg-avatar">
              <svg width="18" height="18" viewBox="0 0 28 28" fill="none">
                <rect x="2" y="2" width="24" height="24" rx="6" stroke="currentColor" strokeWidth="2"/>
                <circle cx="9" cy="11" r="2" fill="currentColor"/>
                <circle cx="19" cy="11" r="2" fill="currentColor"/>
                <path d="M 8 18 Q 14 22 20 18" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round"/>
              </svg>
            </div>
            <div className="msg-bubble typing-bubble">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <form className="input-area" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="اكتب رسالتك هنا... (Enter للإرسال)"
          className="chat-input"
          disabled={isTyping}
          autoFocus
        />
        <button type="submit" className="send-btn" disabled={isTyping || !input.trim()}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path d="M22 2L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </form>

      {/* Quick actions */}
      <div className="quick-actions">
        <button onClick={() => onSend('حلل الكود في المجلد الحالي')} disabled={isTyping}>🔍 تحليل الكود</button>
        <button onClick={() => onSend('أنشئ تقريراً عن المشروع')} disabled={isTyping}>📊 تقرير</button>
        <button onClick={() => onSend('ما هي قدرات OS_V1؟')} disabled={isTyping}>❓ القدرات</button>
      </div>
    </div>
  )
}

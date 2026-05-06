import { useState, useRef, useEffect } from 'react'
import useWebSocket from '../hooks/useWebSocket'
import MessageBubble from './MessageBubble'
import StatusBar from './StatusBar'
import FileUpload from './FileUpload'

export default function ChatWindow({ sessionId, onPhaseChange }) {
  const {
    connected, reconnecting, messages, phase,
    statusText, isStreaming, sendMessage, sendFile,
  } = useWebSocket(sessionId)

  const [input, setInput] = useState('')
  const [file, setFile] = useState(null)
  const messagesEndRef = useRef(null)

  const isBusy = isStreaming || !!statusText

  // Propagate phase changes to parent (for PhaseIndicator)
  useEffect(() => {
    onPhaseChange?.(phase)
  }, [phase, onPhaseChange])

  // Auto-scroll on new messages or status changes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, statusText])

  const handleSend = () => {
    const text = input.trim()
    if (!text && !file) return
    if (isBusy) return

    if (file) {
      sendFile(file, text)
    } else {
      sendMessage(text)
    }

    setInput('')
    setFile(null)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="h-full flex flex-col max-w-4xl mx-auto">
      {/* Connection status */}
      {reconnecting && (
        <div className="bg-amber-50 text-amber-700 text-sm text-center py-1.5 border-b border-amber-200">
          Reconnecting...
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-6 chat-scroll">
        {messages.map((msg, idx) => (
          <MessageBubble key={idx} message={msg} />
        ))}
        <StatusBar text={statusText} />
        <div ref={messagesEndRef} />
      </div>

      {/* File attachment indicator */}
      {file && (
        <div className="px-6 pb-2">
          <div className="inline-flex items-center gap-2 bg-bank-teal/10 text-bank-teal px-3 py-1.5 rounded-full text-sm">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
            </svg>
            {file.name}
            <button
              onClick={() => setFile(null)}
              className="ml-1 hover:text-red-500"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="p-4 border-t border-gray-200 bg-white">
        <div className="flex items-end gap-3">
          <FileUpload
            onFileSelect={setFile}
            disabled={isBusy}
          />

          <div className="flex-1">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={connected ? 'Type your message...' : 'Connecting...'}
              className="w-full resize-none rounded-xl border border-gray-200 px-4 py-3 text-sm
                focus:outline-none focus:border-bank-teal focus:ring-1 focus:ring-bank-teal
                min-h-[44px] max-h-[120px]"
              rows={1}
              disabled={isBusy || !connected}
            />
          </div>

          <button
            onClick={handleSend}
            disabled={isBusy || !connected || (!input.trim() && !file)}
            className="p-2.5 bg-bank-teal text-white rounded-xl hover:bg-bank-teal/90
              disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}

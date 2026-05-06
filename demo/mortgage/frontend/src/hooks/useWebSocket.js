import { useState, useEffect, useRef, useCallback } from 'react'

const RECONNECT_MIN = 1000
const RECONNECT_MAX = 30000

export default function useWebSocket(sessionId) {
  const [connected, setConnected] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [messages, setMessages] = useState([])
  const [phase, setPhase] = useState('GREETING')
  const [sessionMeta, setSessionMeta] = useState({})
  const [statusText, setStatusText] = useState(null)
  const [isStreaming, setIsStreaming] = useState(false)

  const wsRef = useRef(null)
  const reconnectDelay = useRef(RECONNECT_MIN)
  const reconnectTimer = useRef(null)
  const sessionIdRef = useRef(sessionId)

  sessionIdRef.current = sessionId

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) return

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${location.host}/api/ws`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      setReconnecting(false)
      reconnectDelay.current = RECONNECT_MIN

      // Send init handshake
      ws.send(JSON.stringify({ type: 'init', session_id: sessionIdRef.current }))
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)

        switch (msg.type) {
          case 'history':
            setMessages(msg.messages || [])
            setPhase(msg.phase || 'GREETING')
            setSessionMeta(msg.session || {})
            setStatusText(null)
            setIsStreaming(false)
            break

          case 'message_chunk':
            setStatusText(null)
            setIsStreaming(true)
            setMessages(prev => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last?.role === 'assistant' && last.streaming) {
                updated[updated.length - 1] = { ...last, content: last.content + msg.text }
              } else {
                updated.push({ role: 'assistant', content: msg.text, streaming: true })
              }
              return updated
            })
            break

          case 'message_end':
            setStatusText(null)
            setIsStreaming(false)
            setMessages(prev => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last?.role === 'assistant') {
                updated[updated.length - 1] = { ...last, streaming: false }
              }
              return updated
            })
            if (msg.phase) setPhase(msg.phase)
            break

          case 'status':
            setStatusText(msg.text)
            if (msg.phase) setPhase(msg.phase)
            break

          case 'error':
            setStatusText(null)
            setIsStreaming(false)
            setMessages(prev => [...prev, { role: 'assistant', content: msg.text, isError: true }])
            break
        }
      } catch (e) {
        console.error('WebSocket message parse error:', e)
      }
    }

    ws.onclose = () => {
      setConnected(false)
      setStatusText(null)
      setIsStreaming(false)
      wsRef.current = null

      // Auto-reconnect with exponential backoff
      setReconnecting(true)
      reconnectTimer.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, RECONNECT_MAX)
        connect()
      }, reconnectDelay.current)
    }

    ws.onerror = (err) => {
      console.error('WebSocket error:', err)
      ws.close()
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.onclose = null // Prevent reconnect on intentional close
        wsRef.current.close()
      }
    }
  }, [connect])

  const sendMessage = useCallback((text) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return

    // Add user message locally
    setMessages(prev => [...prev, { role: 'user', content: text }])

    wsRef.current.send(JSON.stringify({ type: 'message', text }))
  }, [])

  const sendFile = useCallback((file, text = '') => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return

    const reader = new FileReader()
    reader.onload = () => {
      const base64 = reader.result.split(',')[1]

      // Add user message locally
      const displayText = text || `Uploaded: ${file.name}`
      setMessages(prev => [...prev, { role: 'user', content: displayText, fileName: file.name }])

      if (text) {
        wsRef.current.send(JSON.stringify({
          type: 'message_with_file',
          text,
          file: { data: base64, name: file.name, media_type: file.type || 'image/jpeg' },
        }))
      } else {
        wsRef.current.send(JSON.stringify({
          type: 'file',
          data: base64,
          name: file.name,
          media_type: file.type || 'image/jpeg',
        }))
      }
    }
    reader.readAsDataURL(file)
  }, [])

  return {
    connected,
    reconnecting,
    messages,
    phase,
    sessionMeta,
    statusText,
    isStreaming,
    sendMessage,
    sendFile,
  }
}

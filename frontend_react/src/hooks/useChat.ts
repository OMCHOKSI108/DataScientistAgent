import { useState, useCallback } from 'react'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { useAuthStore } from '@/store/useAuthStore'

export interface AgentStep {
  tool: string;
  input: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  steps?: AgentStep[];
}

export function useChat() {
  const { token } = useAuthStore()
  const [messages, setMessages] = useState<Message[]>([])
  const [isTyping, setIsTyping] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sendMessage = useCallback(async (text: string, sessionId?: string, fileContext?: any) => {
    if (!text.trim()) return

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text
    }
    
    // Add user message and a temporary assistant message
    const assistantMsgId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, userMsg, { id: assistantMsgId, role: 'assistant', content: '', steps: [] }])
    setIsTyping(true)
    setError(null)

    try {
      await fetchEventSource('/api/chat/stream/chat_stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          file_context: fileContext
        }),
        onmessage(ev) {
          if (ev.data === '[DONE]') {
            setIsTyping(false)
            return
          }
          try {
            const data = JSON.parse(ev.data)
            setMessages(prev => {
              const updated = [...prev]
              const lastIdx = updated.length - 1
              if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                if (data.type === 'message') {
                  updated[lastIdx].content += data.content
                } else if (data.type === 'step') {
                  updated[lastIdx].steps = updated[lastIdx].steps || []
                  updated[lastIdx].steps.push({ tool: data.tool, input: data.input })
                }
              }
              return updated
            })
          } catch (e) {
            console.error('Failed to parse SSE event', e)
          }
        },
        onclose() {
          setIsTyping(false)
        },
        onerror(err) {
          console.error('SSE Error:', err)
          setError('Failed to connect to chat stream')
          setIsTyping(false)
          throw err // To prevent retries on fatal errors
        }
      })
    } catch (err: any) {
      setError(err.message || 'Stream failed')
      setIsTyping(false)
    }
  }, [token])

  return { messages, isTyping, error, sendMessage, setMessages }
}

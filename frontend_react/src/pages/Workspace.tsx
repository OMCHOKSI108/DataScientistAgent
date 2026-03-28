import { useEffect, useState, useRef } from 'react'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/useAuthStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { LogOut, PlusCircle, MessageSquare, Send, Download } from 'lucide-react'
import { useChat } from '@/hooks/useChat'
import { MessageList } from '@/components/MessageList'
import { UploadComponent } from '@/components/Upload'

export default function Workspace() {
  const { token, email, logout } = useAuthStore()
  const [sessions, setSessions] = useState<any[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | undefined>()
  const [fileContext, setFileContext] = useState<any>(null)
  const [chatInput, setChatInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  
  const { messages, isTyping, error, sendMessage, setMessages } = useChat()

  useEffect(() => {
    // Load chat sessions for sidebar
    if (token) {
      api.get('/api/chat/sessions', token).then(data => {
        if (data.sessions) setSessions(data.sessions)
      }).catch(console.error)
    }
  }, [token])

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault()
    if (!chatInput.trim() || isTyping) return
    sendMessage(chatInput, activeSessionId, fileContext)
    setChatInput('')
  }

  const handleUploadSuccess = (data: any) => {
    setFileContext({
      name: data.filename || data.original_name,
      rows: data.rows,
      cols: data.columns,
      summary: data.summary,
      dtypes: data.dtypes
    })
  }

  const handleExportNotebook = async () => {
    if (!activeSessionId) return
    try {
      const res = await fetch(`/api/export/notebook/${activeSessionId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Export failed')
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `analysis_${activeSessionId.slice(0, 8)}.ipynb`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Notebook export failed:', err)
    }
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 border-r bg-muted/20 flex flex-col">
        <div className="p-4 border-b">
          <Button 
            className="w-full flex gap-2" 
            variant="default"
            onClick={() => {
              setActiveSessionId(undefined)
              setMessages([])
              setFileContext(null)
            }}
          >
            <PlusCircle size={16} /> New Chat
          </Button>
        </div>
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-1">
            {sessions.map((s) => (
              <Button 
                key={s.id} 
                variant={activeSessionId === s.id ? "secondary" : "ghost"} 
                className="w-full justify-start text-sm truncate pl-2"
                onClick={() => setActiveSessionId(s.id)}
              >
                <MessageSquare size={14} className="mr-2 opacity-70 flex-shrink-0" />
                <span className="truncate">{s.title || "New Chat"}</span>
              </Button>
            ))}
          </div>
        </ScrollArea>
        <div className="p-4 border-t mt-auto">
          <div className="text-sm font-medium truncate mb-2">{email}</div>
          <Button variant="ghost" className="w-full justify-start text-muted-foreground hover:text-foreground" onClick={logout}>
            <LogOut size={16} className="mr-2" /> Logout
          </Button>
        </div>
      </aside>
      
      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col relative bg-card text-card-foreground">
        
        {/* Error Banner */}
        {error && (
          <div className="absolute top-0 left-0 right-0 bg-destructive/10 text-destructive text-sm p-2 text-center z-10">
            {error}
          </div>
        )}

        <ScrollArea className="flex-1 p-4 mb-20">
          {messages.length === 0 ? (
            <div className="flex-1 h-full flex flex-col items-center justify-center text-center max-w-2xl mx-auto py-20">
              <h2 className="text-3xl font-bold mb-4">How can I help you analyze data today?</h2>
              <p className="text-muted-foreground mb-10 max-w-md">
                Upload a CSV, Text, or Parquet file below to give me context, or just ask me a general data science question.
              </p>
              {!fileContext ? (
                <div className="w-full max-w-md">
                  <UploadComponent onUploadSuccess={handleUploadSuccess} />
                </div>
              ) : (
                <div className="bg-primary/5 border border-primary/20 p-4 rounded-xl flex items-center justify-between w-full max-w-md">
                  <div className="text-left">
                    <p className="font-semibold text-primary">Data Loaded</p>
                    <p className="text-sm text-muted-foreground">{fileContext.name}</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => setFileContext(null)}>Remove</Button>
                </div>
              )}
            </div>
          ) : (
            <>
              {fileContext && (
                <div className="w-full max-w-4xl mx-auto mb-6 px-4">
                  <div className="bg-muted p-2 flex justify-between items-center text-xs rounded-md text-muted-foreground border">
                    <span>Context Provided: {fileContext.name}</span>
                    <Button variant="ghost" size="sm" onClick={handleExportNotebook} className="h-6 px-2 text-xs">
                      <Download size={12} className="mr-1" /> Export .ipynb
                    </Button>
                  </div>
                </div>
              )}
              {/* Fallback export button if no context */}
              {!fileContext && activeSessionId && messages.length > 0 && (
                <div className="w-full max-w-4xl mx-auto mb-6 px-4 flex justify-end">
                   <Button variant="outline" size="sm" onClick={handleExportNotebook}>
                      <Download size={14} className="mr-2" /> Export to Notebook
                   </Button>
                </div>
              )}
              <MessageList messages={messages} />
            </>
          )}
          <div ref={scrollRef} className="h-4" />
        </ScrollArea>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 right-0 p-4 bg-background border-t">
          <form onSubmit={handleSend} className="max-w-4xl mx-auto flex gap-2">
            <Input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Type your message..."
              className="flex-1 rounded-full px-6 bg-muted/50 focus-visible:bg-background"
              disabled={isTyping}
            />
            <Button type="submit" size="icon" className="rounded-full shrink-0" disabled={!chatInput.trim() || isTyping}>
              <Send size={18} />
            </Button>
          </form>
          <div className="text-center mt-2">
            <span className="text-[10px] text-muted-foreground">AI Agent responses may sometimes be inaccurate.</span>
          </div>
        </div>
      </main>
    </div>
  )
}

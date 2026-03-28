import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeKatex from 'rehype-katex'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { Message } from '@/hooks/useChat'
import { User, Bot, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'

export function MessageList({ messages }: { messages: Message[] }) {
  return (
    <div className="flex flex-col gap-6 w-full max-w-4xl mx-auto px-4 pb-10">
      {messages.map((msg) => (
        <div key={msg.id} className={cn("flex gap-4", msg.role === 'user' ? 'justify-end' : 'justify-start')}>
          {msg.role === 'assistant' && (
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5 text-primary" />
            </div>
          )}
          
          <div className={cn("max-w-[85%] flex flex-col gap-2", msg.role === 'user' ? 'items-end' : 'items-start')}>
            {/* Render Agent Steps if Assistant */}
            {msg.role === 'assistant' && msg.steps && msg.steps.length > 0 && (
              <div className="flex flex-col gap-2 w-full mb-2">
                {msg.steps.map((step, idx) => (
                  <div key={idx} className="text-xs bg-muted/30 border border-border rounded-md p-3 font-mono">
                    <div className="flex items-center gap-2 text-muted-foreground font-semibold mb-1">
                      <Wrench className="w-3 h-3" />
                      Agent used tool: {step.tool}
                    </div>
                    <pre className="whitespace-pre-wrap overflow-x-auto text-muted-foreground/80">
                      {step.input}
                    </pre>
                  </div>
                ))}
              </div>
            )}
            
            {/* Render Main Content */}
            {msg.content && (
              <div className={cn(
                "p-4 rounded-xl", 
                msg.role === 'user' ? "bg-primary text-primary-foreground" : "bg-card border border-border"
              )}>
                {msg.role === 'user' ? (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                ) : (
                  <article className="prose prose-sm dark:prose-invert max-w-none">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeKatex]}
                      components={{
                        code({ node, inline, className, children, ...props }: any) {
                          const match = /language-(\w+)/.exec(className || '')
                          return !inline && match ? (
                            <SyntaxHighlighter
                              style={vscDarkPlus as any}
                              language={match[1]}
                              PreTag="div"
                              className="rounded-md"
                              {...props}
                            >
                              {String(children).replace(/\n$/, '')}
                            </SyntaxHighlighter>
                          ) : (
                            <code className="bg-muted px-1.5 py-0.5 rounded-sm" {...props}>
                              {children}
                            </code>
                          )
                        }
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </article>
                )}
              </div>
            )}
          </div>

          {msg.role === 'user' && (
            <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0">
              <User className="w-5 h-5 text-primary-foreground" />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

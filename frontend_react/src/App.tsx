import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Link, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { Button } from '@/components/ui/button'

import Login from '@/pages/Login'
import Signup from '@/pages/Signup'

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-background font-sans text-foreground antialiased selection:bg-primary selection:text-primary-foreground flex flex-col">
          <header className="border-b bg-background sticky top-0 z-50">
            <div className="container flex h-14 items-center justify-between">
              <Link to="/" className="font-semibold text-lg hover:opacity-80 transition-opacity">
                Data Scientist Agent
              </Link>
              <AuthNav />
            </div>
          </header>
          <main className="flex-1 flex flex-col">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<Signup />} />
              <Route path="/workspace" element={<WorkspaceGuard />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

function AuthNav() {
  const { token, logout } = useAuthStore()
  if (token) {
    return (
      <div className="flex gap-4 items-center">
        <Link to="/workspace">
          <Button variant="ghost">Workspace</Button>
        </Link>
        <Button variant="outline" onClick={logout}>Logout</Button>
      </div>
    )
  }
  return (
    <div className="flex gap-4">
      <Link to="/login"><Button variant="ghost">Login</Button></Link>
      <Link to="/signup"><Button>Sign Up</Button></Link>
    </div>
  )
}

function Home() {
  return (
    <div className="flex flex-col items-center justify-center flex-1 p-4 text-center">
      <h1 className="text-5xl font-extrabold mb-6 tracking-tight">Autonomous Data Science</h1>
      <p className="text-muted-foreground text-xl max-w-2xl mb-10 leading-relaxed">
        Upload your datasets, ask natural language questions, and instantly generate insights, charts, and Jupyter Notebooks using cutting-edge Agent workflows.
      </p>
      <div className="flex gap-4">
        <Link to="/signup">
          <Button size="lg" className="h-12 px-8 text-base">Get Started</Button>
        </Link>
      </div>
    </div>
  )
}

import Workspace from '@/pages/Workspace'

function WorkspaceGuard() {
  const { token } = useAuthStore()
  if (!token) return <Navigate to="/login" replace />
  return <Workspace />
}

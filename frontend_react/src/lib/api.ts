const API_BASE_URL = "" // Proxy handles this in dev, Vercel in prod

export const api = {
  get: async (endpoint: string, token: string | null = null) => {
    const headers: HeadersInit = {}
    if (token) headers["Authorization"] = `Bearer ${token}`
    
    const res = await fetch(`${API_BASE_URL}${endpoint}`, { headers })
    if (!res.ok) throw new Error(await res.text() || res.statusText)
    return res.json()
  },
  
  post: async (endpoint: string, body: any, token: string | null = null) => {
    const headers: HeadersInit = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`

    const res = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body)
    })
    
    // Parse JSON safely because some error responses might not be JSON
    let data
    try {
      data = await res.json()
    } catch {
      if (!res.ok) throw new Error(await res.text() || res.statusText)
      return null
    }

    if (!res.ok) throw new Error(data.detail || data.error || res.statusText)
    return data
  }
}

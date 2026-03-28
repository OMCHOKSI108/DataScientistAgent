import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { UploadCloud, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useAuthStore } from '@/store/useAuthStore'
import { cn } from '@/lib/utils'

interface UploadProps {
  onUploadSuccess?: (fileData: any) => void
}

export function UploadComponent({ onUploadSuccess }: UploadProps) {
  const { token } = useAuthStore()
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return
    
    setError(null)
    setSuccess(null)
    setUploading(true)
    
    const file = acceptedFiles[0]
    const formData = new FormData()
    formData.append('file', file)

    try {
      // Direct fetch for multipart/form-data because api helper uses application/json
      const res = await fetch('/api/upload', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData,
      })
      
      const data = await res.json()
      
      if (!res.ok) {
        throw new Error(data.detail || data.error || 'Upload failed')
      }
      
      setSuccess(`Successfully uploaded ${file.name}`)
      if (onUploadSuccess) onUploadSuccess(data)
    } catch (err: any) {
      setError(err.message || 'File upload failed')
    } finally {
      setUploading(false)
    }
  }, [token, onUploadSuccess])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt'],
      'application/vnd.apache.parquet': ['.parquet']
    },
    maxFiles: 1,
    multiple: false
  })

  return (
    <div className="w-full">
      <div 
        {...getRootProps()} 
        className={cn(
          "border-2 border-dashed rounded-xl p-8 transition-colors flex flex-col items-center justify-center cursor-pointer min-h-[160px]",
          isDragActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-muted/50",
          uploading && "opacity-50 pointer-events-none"
        )}
      >
        <input {...getInputProps()} />
        <UploadCloud className={cn("w-10 h-10 mb-4", isDragActive ? "text-primary" : "text-muted-foreground")} />
        <p className="text-sm font-medium text-center">
          {isDragActive ? "Drop the file here" : "Drag & drop a file here, or click to select"}
        </p>
        <p className="text-xs text-muted-foreground mt-2 text-center">
          Supports CSV, TXT, PDF, and Parquet
        </p>
      </div>
      
      {error && (
        <div className="mt-4 p-3 bg-destructive/10 text-destructive text-sm rounded-md flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}
      
      {success && (
        <div className="mt-4 p-3 bg-emerald-500/10 text-emerald-600 text-sm rounded-md flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          {success}
        </div>
      )}
    </div>
  )
}

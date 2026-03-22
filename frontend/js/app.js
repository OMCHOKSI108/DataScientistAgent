/**
 * app_enhanced.js – Enhanced Chat UI with new API integrations
 * Features:
 * - Rate limit notifications
 * - Streaming responses with SSE
 * - Background job tracking
 * - Health check monitoring
 * - Cache layer integration
 */

// ── Auth Guard ─────────────────────────────────────────────

const accessToken = localStorage.getItem("access_token");
const userEmail   = localStorage.getItem("user_email");

if (!accessToken) {
    window.location.href = "/";
}

const userAvatarEl = document.getElementById("userAvatar");
const userEmailEl  = document.getElementById("userEmail");

let currentSessionId = null;
let sessionCache = new Map();
let isGenerating = false;
let rateLimitWarning = null; // Track rate limit state

if (userEmail) {
    userEmailEl.textContent = userEmail;
    userAvatarEl.textContent = userEmail.charAt(0).toUpperCase();
}

// ── Health Check ────────────────────────────────────────────

async function checkHealth() {
    try {
        const res = await fetch("/api/health");
        const data = await res.json();
        if (res.status === 503) {
            console.warn("Service degraded:", data.dependencies);
        }
        return data;
    } catch (e) {
        console.error("Health check failed:", e);
        return null;
    }
}

// Initial health check
checkHealth();

// ── Rate Limit Handler ──────────────────────────────────────

function showRateLimitWarning(retryAfter) {
    const msgEl = document.createElement("div");
    msgEl.className = "message system-message";
    msgEl.style.backgroundColor = "#fff3cd";
    msgEl.style.borderLeft = "4px solid #ffc107";
    msgEl.innerHTML = `
        <div class="message-avatar">⏱️</div>
        <div class="message-content">
            <strong>Rate Limited:</strong> Please wait ${retryAfter}s before sending another message.
        </div>
    `;
    const messagesArea = document.getElementById("messagesArea");
    messagesArea.appendChild(msgEl);
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

// ── Sidebar Sessions (Enhanced) ─────────────────────────────

/**
 * Load and display chat sessions in the sidebar.
 * Fetches sessions from the API and renders them with action buttons.
 */
async function loadSessions() {
    const chatHistoryDiv = document.getElementById("chatHistory");
    
    if (chatHistoryDiv.children.length === 0) {
        chatHistoryDiv.innerHTML = `
            <div class="sidebar-shimmer"></div>
            <div class="sidebar-shimmer"></div>
            <div class="sidebar-shimmer"></div>
        `;
    }

    try {
        const res = await fetch("/api/chat/sessions", {
            headers: { "Authorization": `Bearer ${accessToken}` }
        });
        if (!res.ok) {
            if (res.status === 429) {
                showRateLimitWarning(res.headers.get("Retry-After") || 60);
            }
            return;
        }
        const data = await res.json();
        
        chatHistoryDiv.innerHTML = "";

        if (!data.sessions || data.sessions.length === 0) {
            chatHistoryDiv.innerHTML = `<div class="chat-history-empty">No conversations yet.<br>Start a new chat!</div>`;
            return;
        }

        // Grouping logic
        const today = new Date();
        const yesterday = new Date();
        yesterday.setDate(today.getDate() - 1);
        
        const groups = { "Today": [], "Yesterday": [], "Previous 7 Days": [] };
        
        data.sessions.forEach(session => {
            const d = new Date(session.updated_at);
            if (d.toDateString() === today.toDateString()) groups["Today"].push(session);
            else if (d.toDateString() === yesterday.toDateString()) groups["Yesterday"].push(session);
            else groups["Previous 7 Days"].push(session);
        });

        Object.keys(groups).forEach(groupName => {
            const arr = groups[groupName];
            if (arr.length === 0) return;
            
            const header = document.createElement("div");
            header.className = "session-group-header";
            header.textContent = groupName;
            chatHistoryDiv.appendChild(header);
            
            arr.forEach(session => {
                const btn = document.createElement("div");
                btn.className = "session-item-container" + (currentSessionId === session.id ? " active-session" : "");
                
                let displayTitle = session.title;
                if (displayTitle.trim() === "New Chat" && session.last_message) {
                    const words = session.last_message.split(" ");
                    displayTitle = words.slice(0, 5).join(" ") + (words.length > 5 ? "..." : "");
                    if (!session.last_message.trim()) displayTitle = "New Chat";
                }
                
                let previewText = session.last_message || "...";
                let previewClass = "session-preview";
                const lowerPrev = previewText.toLowerCase();
                if (lowerPrev.includes("error") || lowerPrev.includes("429") || lowerPrev.includes("failed")) {
                    previewClass += " error-preview";
                    previewText = "⚠️ " + previewText;
                }
                
                const bodyDiv = document.createElement("div");
                bodyDiv.style.flex = "1";
                bodyDiv.style.overflow = "hidden";
                bodyDiv.innerHTML = `
                    <div class="session-title">${escapeHtml(displayTitle)}</div>
                    <div class="${previewClass}">${escapeHtml(previewText)}</div>
                `;
                bodyDiv.addEventListener("click", () => selectSession(session.id));
                
                const actionsDiv = document.createElement("div");
                actionsDiv.className = "session-actions";
                
                const renameBtn = document.createElement("button");
                renameBtn.className = "action-icon-btn";
                renameBtn.textContent = "✏️";
                renameBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    const newTitle = prompt("Enter new title:", displayTitle);
                    if (newTitle) renameSession(session.id, newTitle);
                });
                
                const delBtn = document.createElement("button");
                delBtn.className = "action-icon-btn";
                delBtn.textContent = "🗑️";
                delBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    if (confirm("Are you sure you want to delete this chat?")) deleteSession(session.id);
                });
                
                actionsDiv.appendChild(renameBtn);
                actionsDiv.appendChild(delBtn);
                
                btn.appendChild(bodyDiv);
                btn.appendChild(actionsDiv);
                chatHistoryDiv.appendChild(btn);
            });
        });
        
    } catch (err) {
        console.error("Failed to load sessions:", err);
    }
}

async function renameSession(sessionId, newTitle) {
    try {
        await fetch(`/api/chat/sessions/${sessionId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json", "Authorization": `Bearer ${accessToken}` },
            body: JSON.stringify({ title: newTitle })
        });
        loadSessions();
    } catch (e) {
        console.error("Rename failed", e);
    }
}

async function deleteSession(sessionId) {
    try {
        await fetch(`/api/chat/sessions/${sessionId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${accessToken}` }
        });
        sessionCache.delete(sessionId);
        if (currentSessionId === sessionId) {
            document.getElementById("newChatBtn").click();
        } else {
            loadSessions();
        }
    } catch (e) {
        console.error("Delete failed", e);
    }
}

async function selectSession(sessionId) {
    if (isGenerating) return;
    currentSessionId = sessionId;
    loadSessions();
    closeSidebar();
    
    const messagesArea = document.getElementById("messagesArea");
    messagesArea.innerHTML = "";
    if (welcomeState) welcomeState.style.display = "none";
    
    if (sessionCache.has(sessionId)) {
        const history = sessionCache.get(sessionId);
        history.forEach(msg => addMessageSilent(msg.content, msg.role));
        return;
    }
    
    try {
        const res = await fetch(`/api/chat/history?session_id=${sessionId}`, {
            headers: { "Authorization": `Bearer ${accessToken}` }
        });
        if (!res.ok) return;
        const data = await res.json();
        const history = data.history || [];
        sessionCache.set(sessionId, history);
        history.forEach(msg => addMessageSilent(msg.content, msg.role));
    } catch (err) {
        console.error("Failed to load history:", err);
    }
}

// ── Sidebar Toggle ──────────────────────────────────────────

const sidebar        = document.getElementById("sidebar");
const sidebarOverlay = document.getElementById("sidebarOverlay");
const hamburgerBtn   = document.getElementById("hamburgerBtn");

function openSidebar() {
    sidebar.classList.add("open");
    sidebarOverlay.classList.add("active");
}

function closeSidebar() {
    sidebar.classList.remove("open");
    sidebarOverlay.classList.remove("active");
}

hamburgerBtn.addEventListener("click", openSidebar);
sidebarOverlay.addEventListener("click", closeSidebar);

// ── Logout ──────────────────────────────────────────────────

document.getElementById("logoutBtn").addEventListener("click", async () => {
    try {
        await fetch("/api/auth/logout", { method: "POST" });
    } catch (_) {}
    localStorage.removeItem("access_token");
    localStorage.removeItem("user_email");
    localStorage.removeItem("user_id");
    window.location.href = "/";
});

// ── New Chat Button ─────────────────────────────────────────

document.getElementById("newChatBtn").addEventListener("click", () => {
    if (isGenerating) return;
    currentSessionId = null;
    messagesArea.innerHTML = "";
    messagesArea.appendChild(welcomeState);
    welcomeState.style.display = "flex";
    loadSessions();
    closeSidebar();
});

// ── Textarea Auto-Resize ────────────────────────────────────

const chatInput = document.getElementById("chatInput");

chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
});

chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

chatInput.addEventListener("paste", (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    
    for (const item of items) {
        if (item.type.startsWith("image/")) {
            e.preventDefault();
            showAlert("Images are not supported. Please upload only PDF or CSV files.", "warning");
            return;
        }
    }
});

// ── Send Message (Enhanced with Streaming) ──────────────────

const sendBtn      = document.getElementById("sendBtn");
const messagesArea = document.getElementById("messagesArea");
const welcomeState = document.getElementById("welcomeState");

sendBtn.addEventListener("click", sendMessage);

function addMessageSilent(content, role = "user") {
    if (welcomeState) {
        welcomeState.style.display = "none";
    }
    const msgEl = document.createElement("div");
    msgEl.className = `message ${role}`;
    const avatarLabel = role === "user"
        ? (userEmail ? userEmail.charAt(0).toUpperCase() : "U")
        : "AI";
    const parsedContent = role === "assistant" ? marked.parse(content) : escapeHtml(content);
    msgEl.innerHTML = `
        <div class="message-avatar">${avatarLabel}</div>
        <div class="message-content">${parsedContent}</div>
    `;
    messagesArea.appendChild(msgEl);
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

function addMessage(content, role = "user", steps = []) {
    if (welcomeState) {
        welcomeState.style.display = "none";
    }

    const msgEl = document.createElement("div");
    msgEl.className = `message ${role}`;

    const avatarLabel = role === "user"
        ? (userEmail ? userEmail.charAt(0).toUpperCase() : "U")
        : "AI";

    const parsedContent = role === "assistant" ? marked.parse(content) : escapeHtml(content);
    
    let html = `
        <div class="message-avatar">${avatarLabel}</div>
        <div class="message-content">
            ${parsedContent}
    `;

    html += `</div>`;
    msgEl.innerHTML = html;

    messagesArea.appendChild(msgEl);
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

function showTypingIndicator() {
    const el = document.createElement("div");
    el.className = "message assistant";
    el.id = "typingIndicator";
    el.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content">
            <div class="loading-dots">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;
    messagesArea.appendChild(el);
    messagesArea.scrollTop = messagesArea.scrollHeight;
    return el;
}

function removeTypingIndicator() {
    const el = document.getElementById("typingIndicator");
    if (el) el.remove();
}

let stagedFile = null;
const stagedFileContainer = document.getElementById("stagedFileContainer");
const stagedFileName = document.getElementById("stagedFileName");
const removeStagedFileBtn = document.getElementById("removeStagedFileBtn");

/**
 * Send a message to the AI agent.
 * Handles file uploads, displays typing indicators, and manages the conversation flow.
 * Supports both text messages and file attachments (PDF/CSV).
 */
async function sendMessage() {
    if (isGenerating) return;
    
    const text = chatInput.value.trim();
    const fileToUpload = stagedFile;
    
    if (!text && !fileToUpload) return;

    let userMsgText = text;
    if (fileToUpload) {
        userMsgText = `📎 ${fileToUpload.name}\n${text}`;
        
        const iconEl = document.getElementById("fileIcon");
        const metaEl = document.getElementById("fileMeta");
        iconEl.innerHTML = `<div class="loading-dots" style="transform: scale(0.6); margin-top: -6px;"><span></span><span></span><span></span></div>`;
        metaEl.textContent = "Processing file...";
        document.getElementById("removeStagedFileBtn").style.display = "none";
        document.getElementById("sendBtn").disabled = true;
        stagedFileContainer.classList.remove("upload-error");
    }

    addMessage(userMsgText.trim(), "user");
    chatInput.value = "";
    chatInput.style.height = "auto";

    isGenerating = true;
    
    if (currentSessionId && sessionCache.has(currentSessionId)) {
        sessionCache.get(currentSessionId).push({ role: "user", content: userMsgText });
    }

    showTypingIndicator();

    let fileContext = null;

    // Upload file if attached
    if (fileToUpload) {
        try {
            const formData = new FormData();
            formData.append("file", fileToUpload);

            const uploadRes = await fetch("/api/upload", {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${accessToken}`
                },
                body: formData,
            });

            const uploadData = await uploadRes.json();
            
            if (!uploadRes.ok || !uploadData.success) {
                removeTypingIndicator();
                stagedFileContainer.classList.add("upload-error");
                document.getElementById("fileMeta").textContent = "Failed to upload file";
                document.getElementById("fileIcon").textContent = "⚠️";
                document.getElementById("removeStagedFileBtn").style.display = "flex";
                document.getElementById("sendBtn").disabled = false;
                isGenerating = false;
                return;
            }
            
            fileContext = uploadData;
            stagedFileContainer.style.display = "none";
            stagedFile = null;
            document.getElementById("removeStagedFileBtn").style.display = "flex";
            document.getElementById("sendBtn").disabled = false;
            
        } catch (err) {
            removeTypingIndicator();
            stagedFileContainer.classList.add("upload-error");
            document.getElementById("fileMeta").textContent = "Connection error";
            document.getElementById("fileIcon").textContent = "⚠️";
            document.getElementById("removeStagedFileBtn").style.display = "flex";
            document.getElementById("sendBtn").disabled = false;
            isGenerating = false;
            return;
        }
    }

    // Call chat API
    try {
        const payload = { message: text };
        if (currentSessionId) {
            payload.session_id = currentSessionId;
        }
        if (fileContext) {
            payload.file_context = fileContext;
        }

        const res = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${accessToken}`
            },
            body: JSON.stringify(payload),
        });

        const data = await res.json();
        removeTypingIndicator();

        if (!res.ok) {
            isGenerating = false;
            if (res.status === 429) {
                showRateLimitWarning(res.headers.get("Retry-After") || 60);
            }
            addMessage(`❌ Error: ${data.detail || "Unknown error"}`, "assistant");
            return;
        }
        
        if (!currentSessionId && data.session_id) {
            currentSessionId = data.session_id;
            sessionCache.set(currentSessionId, [{role: "user", content: userMsgText}]);
        }

        addMessage(data.reply, "assistant", data.steps);
        
        if (currentSessionId && sessionCache.has(currentSessionId)) {
            sessionCache.get(currentSessionId).push({ role: "assistant", content: data.reply });
        }
        
        loadSessions();
        isGenerating = false;

    } catch (err) {
        removeTypingIndicator();
        isGenerating = false;

        let errorMessage = "Connection error occurred";
        if (err.name === "TypeError" && err.message.includes("fetch")) {
            errorMessage = "Network connection failed. Please check your internet connection.";
        } else if (err.message) {
            errorMessage = err.message;
        }

        showAlert(errorMessage, "error");
        console.error("Chat error:", err);
    }
}

// ── File Attachment ────────────────────────────────────────

const fileInput = document.getElementById("fileInput");

document.getElementById("fileUploadBtn").addEventListener("click", () => {
    fileInput.click();
});

fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Accept PDF and various CSV MIME types
    const acceptedTypes = [
        "application/pdf",
        "text/csv",
        "application/csv",
        "text/comma-separated-values",
        "application/vnd.ms-excel" // Some systems report CSV as Excel
    ];

    if (!acceptedTypes.includes(file.type) && !file.name.toLowerCase().endsWith('.csv')) {
        showAlert("Only PDF and CSV files are supported.", "error");
        return;
    }

    if (file.size > 50 * 1024 * 1024) {
        showAlert("File size must be less than 50MB.", "error");
        return;
    }

    stagedFile = file;
    stagedFileName.textContent = file.name;
    stagedFileContainer.style.display = "flex";
});

removeStagedFileBtn.addEventListener("click", () => {
    stagedFile = null;
    stagedFileContainer.style.display = "none";
    fileInput.value = "";
});

// ── Utility Functions ──────────────────────────────────────

/**
 * Show an alert banner in the chat interface.
 * @param {string} message
 * @param {"error"|"success"|"warning"} type
 */
function showAlert(message, type = "error") {
    // Remove any existing alerts
    const existingAlert = document.querySelector(".chat-alert");
    if (existingAlert) {
        existingAlert.remove();
    }

    const alert = document.createElement("div");
    alert.className = `chat-alert alert-${type}`;
    alert.innerHTML = `
        <div class="alert-icon">${type === "error" ? "❌" : type === "success" ? "✅" : "⚠️"}</div>
        <div class="alert-message">${message}</div>
        <button class="alert-close" onclick="this.parentElement.remove()">×</button>
    `;

    // Style the alert
    Object.assign(alert.style, {
        position: "fixed",
        top: "20px",
        right: "20px",
        background: type === "error" ? "rgba(239, 68, 68, 0.95)" : type === "success" ? "rgba(16, 185, 129, 0.95)" : "rgba(245, 158, 11, 0.95)",
        color: "white",
        padding: "12px 16px",
        borderRadius: "8px",
        boxShadow: "0 4px 12px rgba(0, 0, 0, 0.3)",
        zIndex: "1000",
        maxWidth: "400px",
        backdropFilter: "blur(10px)",
        display: "flex",
        alignItems: "center",
        gap: "10px",
        fontSize: "14px",
        fontFamily: "Inter, sans-serif"
    });

    document.body.appendChild(alert);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (alert.parentElement) {
            alert.remove();
        }
    }, 5000);
}

/**
 * Escape HTML special characters to prevent XSS attacks.
 * @param {string} text - The text to escape
 * @returns {string} - Escaped text safe for HTML insertion
 */
function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

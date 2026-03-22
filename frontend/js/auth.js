/**
 * auth.js – Handles login and signup form submissions.
 * Communicates with the FastAPI backend at /api/auth/*.
 * Stores the access token in localStorage on success.
 */

const API_BASE = "";  // same origin
let SUPABASE_CONFIG = {};

// Fetch config on startup
document.addEventListener("DOMContentLoaded", async () => {
    try {
        const res = await fetch(`${API_BASE}/api/config`);
        if (!res.ok) throw new Error("Could not load backend config");
        SUPABASE_CONFIG = await res.json();

        if (!SUPABASE_CONFIG.supabase_url) {
            showAlert("Supabase URL is not configured on the backend.");
        }
    } catch (err) {
        showAlert(err.message);
    }
});

// ── Helpers ────────────────────────────────────────────────

/**
 * Show an alert banner inside the auth card.
 * @param {string} message
 * @param {"error"|"success"} type
 */
function showAlert(message, type = "error") {
    const alert = document.getElementById("alert");
    if (!alert) return;
    alert.textContent = message;
    alert.className = `alert alert-${type}`;
    alert.style.display = "block";
}

/** Hide the alert banner. */
function hideAlert() {
    const alert = document.getElementById("alert");
    if (!alert) return;
    alert.style.display = "none";
}

/**
 * Set the button to a loading state.
 * @param {HTMLButtonElement} btn
 * @param {boolean} loading
 */
function setLoading(btn, loading) {
    if (!btn) return;
    btn.disabled = loading;
    btn.textContent = loading ? "Please wait…" : btn.dataset.label;
}

// ── Login Form ─────────────────────────────────────────────

const loginForm = document.getElementById("loginForm");

if (loginForm) {
    const loginBtn = document.getElementById("loginBtn");
    loginBtn.dataset.label = loginBtn.textContent;

    // If already logged in, redirect to chat
    if (localStorage.getItem("access_token")) {
        window.location.href = "/chat.html";
    }

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        hideAlert();
        setLoading(loginBtn, true);

        const email = document.getElementById("email").value.trim();
        const password = document.getElementById("password").value;

        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password }),
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || "Login failed.");
            }

            // Store token & user info
            localStorage.setItem("access_token", data.access_token);
            localStorage.setItem("user_email", data.email);
            localStorage.setItem("user_id", data.user_id);

            showAlert("Login successful! Redirecting…", "success");
            setTimeout(() => {
                window.location.href = "/chat.html";
            }, 600);
        } catch (err) {
            showAlert(err.message);
        } finally {
            setLoading(loginBtn, false);
        }
    });
}

// ── Signup Form ────────────────────────────────────────────

const signupForm = document.getElementById("signupForm");

if (signupForm) {
    const signupBtn = document.getElementById("signupBtn");
    signupBtn.dataset.label = signupBtn.textContent;

    // If already logged in, redirect to chat
    if (localStorage.getItem("access_token")) {
        window.location.href = "/chat.html";
    }

    signupForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        hideAlert();

        const email = document.getElementById("email").value.trim();
        const password = document.getElementById("password").value;
        const confirmPassword = document.getElementById("confirmPassword").value;

        // Client-side validation
        if (password !== confirmPassword) {
            showAlert("Passwords do not match.");
            return;
        }

        if (password.length < 6) {
            showAlert("Password must be at least 6 characters.");
            return;
        }

        setLoading(signupBtn, true);

        try {
            const res = await fetch(`${API_BASE}/api/auth/signup`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password }),
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || "Signup failed.");
            }

            // If session is returned (email confirmation disabled), auto-login
            if (data.access_token) {
                localStorage.setItem("access_token", data.access_token);
                localStorage.setItem("user_email", data.email);
                localStorage.setItem("user_id", data.user_id);
                showAlert("Account created! Redirecting…", "success");
                setTimeout(() => {
                    window.location.href = "/chat.html";
                }, 600);
            } else {
                showAlert("Account created! Check your email to confirm.", "success");
            }
        } catch (err) {
            showAlert(err.message);
        } finally {
            setLoading(signupBtn, false);
        }
    });
}

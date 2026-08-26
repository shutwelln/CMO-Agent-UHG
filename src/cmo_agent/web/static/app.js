// CMO Agent Web UI

const API_BASE = '';
const SESSION_KEY = 'cmo_session_id';

// Get or create session ID
function getSessionId() {
    let sessionId = localStorage.getItem(SESSION_KEY);
    if (!sessionId) {
        sessionId = crypto.randomUUID();
        localStorage.setItem(SESSION_KEY, sessionId);
    }
    return sessionId;
}

// DOM elements
const messagesEl = document.getElementById('messages');
const chatForm = document.getElementById('chat-form');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const clearBtn = document.getElementById('clear-btn');
const sessionIdEl = document.getElementById('session-id');

// Display session ID
sessionIdEl.textContent = getSessionId().slice(0, 8) + '...';

// Add message to chat
function addMessage(content, type, actions = [], traceId = null) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${type}`;

    // Simple markdown-like formatting
    let formattedContent = content
        .replace(/```([\s\S]*?)```/g, '<pre>$1</pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');

    let html = `<div class="content">${formattedContent}</div>`;

    // Add actions if present
    if (actions.length > 0) {
        html += `
            <div class="actions">
                <div class="actions-title">Actions taken:</div>
                <ul>
                    ${actions.map(a => `<li>${escapeHtml(a)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    // Add trace ID for assistant messages
    if (traceId && type === 'assistant') {
        html += `<div class="trace-id">Trace: ${traceId.slice(0, 8)}</div>`;
    }

    messageEl.innerHTML = html;
    messagesEl.appendChild(messageEl);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Escape HTML for security
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Send message to API
async function sendMessage(message) {
    const sessionId = getSessionId();

    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                session_id: sessionId,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Request failed');
        }

        return await response.json();
    } catch (error) {
        throw error;
    }
}

// Handle form submission
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const message = messageInput.value.trim();
    if (!message) return;

    // Disable form
    messageInput.disabled = true;
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<span class="loading"></span>';

    // Add user message
    addMessage(message, 'user');
    messageInput.value = '';

    try {
        const response = await sendMessage(message);
        addMessage(
            response.reply,
            response.status === 'error' ? 'error' : 'assistant',
            response.actions_taken,
            response.trace_id
        );
    } catch (error) {
        addMessage(`Error: ${error.message}`, 'error');
    } finally {
        // Re-enable form
        messageInput.disabled = false;
        sendBtn.disabled = false;
        sendBtn.textContent = 'Send';
        messageInput.focus();
    }
});

// Clear chat
clearBtn.addEventListener('click', async () => {
    const sessionId = getSessionId();

    // Clear UI
    messagesEl.innerHTML = '';

    // Try to delete session on server
    try {
        await fetch(`${API_BASE}/session/${sessionId}`, {
            method: 'DELETE',
        });
    } catch (e) {
        // Ignore errors
    }

    // Generate new session
    const newSessionId = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, newSessionId);
    sessionIdEl.textContent = newSessionId.slice(0, 8) + '...';
});

// Focus input on load
messageInput.focus();

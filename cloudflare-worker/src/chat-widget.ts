/**
 * Saverwell Chat Widget - Frontend UI
 *
 * Inline JS+CSS served from /widget/v1/chat.js
 * Shadow DOM isolates styles from host page.
 *
 * Features: FAB, chat panel, SSE streaming, suggested questions,
 * email capture, GA4 events, accessibility, mobile support.
 */

// ---------------------------------------------------------------------------
// CSS (scoped inside Shadow DOM)
// ---------------------------------------------------------------------------
export const CHAT_WIDGET_CSS = `\
:host{display:block;font-family:Manrope,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.5;--teal:#2A9D8F;--teal-dark:#238577;--teal-bg:#f0fdfa;--gray-900:#1f2937;--gray-600:#6b7280;--gray-400:#9ca3af;--gray-200:#e5e7eb;--gray-50:#f9fafb;--white:#fff;--red:#ef4444}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

/* FAB */
.sw-chat-fab{position:fixed;bottom:24px;right:24px;width:56px;height:56px;border-radius:50%;background:var(--teal);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(0,0,0,.15);z-index:9999;transition:transform .2s ease,box-shadow .2s ease}
.sw-chat-fab:hover{transform:scale(1.05);box-shadow:0 6px 16px rgba(0,0,0,.2)}
.sw-chat-fab:focus-visible{outline:3px solid var(--teal);outline-offset:3px}
.sw-chat-fab svg{width:28px;height:28px;fill:var(--white)}
.sw-chat-fab .sw-tooltip{position:absolute;right:68px;top:50%;transform:translateY(-50%);background:var(--gray-900);color:var(--white);font-size:13px;padding:6px 12px;border-radius:6px;white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .2s ease}
.sw-chat-fab:hover .sw-tooltip{opacity:1}

/* Panel */
.sw-chat-panel{position:fixed;bottom:24px;right:24px;width:380px;height:520px;background:var(--white);border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,.15);z-index:10000;display:none;flex-direction:column;overflow:hidden}
.sw-chat-panel.sw-open{display:flex}
@media(max-width:480px){.sw-chat-panel{width:calc(100% - 16px);height:90vh;bottom:8px;right:8px;border-radius:12px}}

/* Header */
.sw-chat-header{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--gray-200);flex-shrink:0}
.sw-chat-header-left{display:flex;align-items:center;gap:10px}
.sw-chat-header-logo{width:24px;height:24px}
.sw-chat-header-title{font-size:15px;font-weight:600;color:var(--gray-900)}
.sw-chat-close{width:44px;height:44px;display:flex;align-items:center;justify-content:center;border:none;background:none;cursor:pointer;border-radius:8px;color:var(--gray-600)}
.sw-chat-close:hover{background:var(--gray-50)}
.sw-chat-close:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
.sw-chat-close svg{width:24px;height:24px}

/* Messages area */
.sw-chat-messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;scroll-behavior:smooth}

/* Message cards */
.sw-chat-msg{padding:12px 14px;border-radius:10px;font-size:16px;color:var(--gray-900);line-height:1.6;max-width:95%;word-wrap:break-word}
.sw-chat-msg a{color:var(--teal-dark);text-decoration:underline;text-underline-offset:2px}
.sw-chat-msg a:hover{color:var(--teal)}
.sw-chat-msg-user{background:var(--gray-50);align-self:flex-end;border-radius:10px 10px 2px 10px}
.sw-chat-msg-assistant{background:var(--teal-bg);align-self:flex-start;border-left:3px solid var(--teal);border-radius:2px 10px 10px 10px}
.sw-chat-msg-assistant strong{font-weight:600}

/* Sources */
.sw-chat-sources{display:flex;flex-direction:column;gap:6px;margin-top:8px}
.sw-chat-source-link{display:block;padding:8px 12px;background:var(--white);border:1px solid var(--gray-200);border-radius:8px;text-decoration:none;color:var(--teal-dark);font-size:14px;font-weight:500;transition:border-color .15s}
.sw-chat-source-link:hover{border-color:var(--teal)}

/* Suggestions (chips) */
.sw-chat-suggestions{display:flex;flex-wrap:wrap;gap:8px;padding:4px 0}
.sw-chat-chip{display:inline-block;padding:8px 14px;background:var(--white);border:1px solid var(--gray-200);border-radius:20px;font-size:15px;color:var(--teal-dark);cursor:pointer;transition:background .15s,border-color .15s;min-height:44px;line-height:1.4;text-align:left}
.sw-chat-chip:hover{background:var(--teal-bg);border-color:var(--teal)}
.sw-chat-chip:focus-visible{outline:2px solid var(--teal);outline-offset:2px}

/* Email capture */
.sw-chat-email-fields{display:flex;flex-direction:column;gap:6px;padding:8px 0}
.sw-chat-email-row{display:flex;gap:8px}
.sw-chat-email-row input{flex:1;padding:10px 12px;border:1px solid var(--gray-200);border-radius:8px;font-size:15px;font-family:inherit;color:var(--gray-900);outline:none;min-height:44px}
.sw-chat-email-row input:focus{border-color:var(--teal);box-shadow:0 0 0 2px rgba(42,157,143,.2)}
.sw-chat-email-row input.sw-zip-input{flex:0 0 100px;max-width:100px;text-align:center}
.sw-chat-email-row button{padding:10px 16px;background:var(--teal);color:var(--white);border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap;min-height:44px;font-family:inherit}
.sw-chat-email-row button:hover{background:var(--teal-dark)}
.sw-chat-email-row button:disabled{opacity:.6;cursor:not-allowed}
.sw-chat-email-ok{font-size:14px;color:var(--teal);padding:4px 0}
.sw-chat-email-err{font-size:14px;color:var(--red);padding:4px 0}

/* Input area */
.sw-chat-input-area{display:flex;gap:8px;padding:12px 16px;border-top:1px solid var(--gray-200);flex-shrink:0;align-items:flex-end}
.sw-chat-input{flex:1;padding:10px 14px;border:1px solid var(--gray-200);border-radius:10px;font-size:16px;font-family:inherit;color:var(--gray-900);outline:none;resize:none;min-height:44px;max-height:88px;line-height:1.4}
.sw-chat-input:focus{border-color:var(--teal);box-shadow:0 0 0 2px rgba(42,157,143,.2)}
.sw-chat-input::placeholder{color:var(--gray-400)}
.sw-chat-send{width:44px;height:44px;display:flex;align-items:center;justify-content:center;background:var(--teal);border:none;border-radius:10px;cursor:pointer;flex-shrink:0}
.sw-chat-send:hover{background:var(--teal-dark)}
.sw-chat-send:disabled{opacity:.4;cursor:not-allowed}
.sw-chat-send:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
.sw-chat-send svg{width:20px;height:20px;fill:var(--white)}

/* Loading */
.sw-chat-loading{display:flex;align-items:center;gap:8px;padding:12px 14px;color:var(--gray-600);font-size:14px}
.sw-chat-dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--teal);animation:sw-pulse 1.4s infinite ease-in-out both}
.sw-chat-dot:nth-child(1){animation-delay:-.32s}
.sw-chat-dot:nth-child(2){animation-delay:-.16s}
@keyframes sw-pulse{0%,80%,100%{transform:scale(0);opacity:.5}40%{transform:scale(1);opacity:1}}

/* Reduced motion */
@media(prefers-reduced-motion:reduce){
.sw-chat-fab{transition:none}
.sw-chat-panel{transition:none}
.sw-chat-dot{animation:none;opacity:1;transform:scale(1)}
.sw-chat-chip{transition:none}
}

/* Turn limit banner */
.sw-chat-limit{padding:12px 16px;background:var(--teal-bg);border-top:1px solid var(--gray-200);font-size:14px;color:var(--gray-900);text-align:center}
.sw-chat-limit a{color:var(--teal-dark)}
.sw-chat-new-btn{display:inline-block;margin-top:8px;padding:8px 16px;background:var(--teal);color:var(--white);border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;min-height:44px;font-family:inherit}
.sw-chat-new-btn:hover{background:var(--teal-dark)}
`;

// ---------------------------------------------------------------------------
// JS (inlined, self-executing)
// ---------------------------------------------------------------------------
export const CHAT_WIDGET_JS = `\
(function(){
'use strict';

// === Config ===
var API_URL = '/widget/v1/api/chat';
var SUBSCRIBE_URL = '/widget/v1/api/subscribe';
var MAX_TURNS = 8;
var MAX_MSG_LEN = 500;

// === State ===
var isOpen = false;
var isStreaming = false;
var turnNumber = 0;
var history = [];
var sessionKey = 'sw_chat_session';
var openTime = 0;
var capturedZip = '';

// Restore session
try {
  var saved = sessionStorage.getItem(sessionKey);
  if (saved) {
    var s = JSON.parse(saved);
    history = s.history || [];
    turnNumber = s.turnNumber || 0;
  }
} catch(e) {}

function saveSession() {
  try {
    sessionStorage.setItem(sessionKey, JSON.stringify({
      history: history.slice(-8),
      turnNumber: turnNumber
    }));
  } catch(e) {}
}

// === Shadow DOM setup ===
var host = document.createElement('div');
host.id = 'sw-chat-widget';
document.body.appendChild(host);
var shadow = host.attachShadow({ mode: 'closed' });

var style = document.createElement('style');
style.textContent = '__CHAT_CSS__';
shadow.appendChild(style);

var container = document.createElement('div');
shadow.appendChild(container);

// === GA4 tracking ===
function track(event, params) {
  if (window.swTrack && typeof window.dataLayer !== 'undefined') {
    var data = { event: event };
    if (params) {
      for (var key in params) {
        if (params.hasOwnProperty(key)) data[key] = params[key];
      }
    }
    window.dataLayer.push(data);
  }
}

// === Page-aware suggestions ===
function getSuggestions() {
  var path = window.location.pathname;
  if (path.match(/^\\/guides\\/medicare/)) {
    return [
      'What are the enrollment deadlines?',
      'How can I save on Medicare?',
      'What should I watch out for?'
    ];
  }
  if (path.match(/^\\/guides\\//)) {
    return [
      'Summarize the key points',
      'What should I watch out for?',
      'How can this save me money?'
    ];
  }
  if (path.match(/^\\/protect\\//)) {
    return [
      'What are the red flags?',
      'What should I do right now?',
      'Show me the phone script'
    ];
  }
  if (path.match(/^\\/dma\\//)) {
    return [
      'What discounts are near my ZIP?',
      'Which stores have biggest discounts?',
      'Are there restaurant deals?'
    ];
  }
  if (path === '/') {
    return [
      'I need help with Medicare',
      'I think I\\'m being scammed',
      'Find discounts near me'
    ];
  }
  return [
    'What can Saverwell help with?',
    'Find discounts near me',
    'Medicare questions'
  ];
}

// === SVG icons ===
var chatIcon = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>';
var closeIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
var sendIcon = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>';
var logoSvg = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#2A9D8F"><circle cx="12" cy="12" r="10" fill="#2A9D8F"/><path d="M8 12l2.5 2.5L16 9" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>';

// === Build FAB ===
var fab = document.createElement('button');
fab.className = 'sw-chat-fab';
fab.setAttribute('aria-label', 'Open chat assistant');
fab.setAttribute('tabindex', '0');
fab.innerHTML = chatIcon + '<span class="sw-tooltip">Need help?</span>';
container.appendChild(fab);

// === Build Panel ===
var panel = document.createElement('div');
panel.className = 'sw-chat-panel';
panel.setAttribute('role', 'dialog');
panel.setAttribute('aria-label', 'Saverwell chat assistant');
panel.innerHTML = [
  '<div class="sw-chat-header">',
    '<div class="sw-chat-header-left">',
      '<span class="sw-chat-header-logo">' + logoSvg + '</span>',
      '<span class="sw-chat-header-title">Saverwell</span>',
    '</div>',
    '<button class="sw-chat-close" aria-label="Close chat">' + closeIcon + '</button>',
  '</div>',
  '<div class="sw-chat-messages" aria-live="polite"></div>',
  '<div class="sw-chat-input-area">',
    '<input type="text" class="sw-chat-input" placeholder="Ask a question..." maxlength="' + MAX_MSG_LEN + '" aria-label="Type your message">',
    '<button class="sw-chat-send" aria-label="Send message" disabled>' + sendIcon + '</button>',
  '</div>'
].join('');
container.appendChild(panel);

var closeBtn = panel.querySelector('.sw-chat-close');
var messagesArea = panel.querySelector('.sw-chat-messages');
var inputField = panel.querySelector('.sw-chat-input');
var sendBtn = panel.querySelector('.sw-chat-send');

// === Render helpers ===
function esc(str) {
  var d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function renderMarkdown(text) {
  // Simple markdown: bold, links, line breaks
  return text
    .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
    .replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '<a href="$2">$1</a>')
    .replace(/\\n/g, '<br>');
}

function addMessage(role, html) {
  var div = document.createElement('div');
  div.className = 'sw-chat-msg sw-chat-msg-' + role;
  div.innerHTML = html;
  messagesArea.appendChild(div);
  messagesArea.scrollTop = messagesArea.scrollHeight;
  return div;
}

function addSuggestions(questions) {
  var wrap = document.createElement('div');
  wrap.className = 'sw-chat-suggestions';
  for (var i = 0; i < questions.length; i++) {
    var chip = document.createElement('button');
    chip.className = 'sw-chat-chip';
    chip.textContent = questions[i];
    chip.setAttribute('tabindex', '0');
    chip.addEventListener('click', (function(q) {
      return function() {
        track('chat_suggestion_click', { suggestion_text: q, page_context: window.location.pathname });
        sendMessage(q);
      };
    })(questions[i]));
    wrap.appendChild(chip);
  }
  messagesArea.appendChild(wrap);
  messagesArea.scrollTop = messagesArea.scrollHeight;
}

function addSources(articles) {
  var wrap = document.createElement('div');
  wrap.className = 'sw-chat-sources';
  for (var i = 0; i < articles.length; i++) {
    var a = document.createElement('a');
    a.className = 'sw-chat-source-link';
    a.href = articles[i].url;


    a.textContent = articles[i].title;
    a.addEventListener('click', (function(article, idx) {
      return function() {
        track('chat_article_click', { article_slug: article.slug, position: idx + 1 });
      };
    })(articles[i], i));
    wrap.appendChild(a);
  }
  messagesArea.appendChild(wrap);
  messagesArea.scrollTop = messagesArea.scrollHeight;
}

function addEmailCapture(trigger) {
  var wrap = document.createElement('div');
  wrap.className = 'sw-chat-msg sw-chat-msg-assistant';
  var label = trigger === 'scam_triage'
    ? 'I can email you these steps so you have them handy. Enter your email and ZIP code:'
    : 'Want a weekly digest of tips like this? Enter your email and ZIP code:';
  wrap.innerHTML = '<div>' + esc(label) + '</div>' +
    '<div class="sw-chat-email-fields">' +
      '<div class="sw-chat-email-row">' +
        '<input type="email" placeholder="Your email address" aria-label="Email address">' +
        '<input type="text" class="sw-zip-input" inputmode="numeric" pattern="[0-9]{5}" maxlength="5" placeholder="ZIP" aria-label="ZIP code" value="' + esc(capturedZip) + '">' +
      '</div>' +
      '<div class="sw-chat-email-row">' +
        '<button>Send</button>' +
      '</div>' +
    '</div>' +
    '<div class="sw-chat-email-msg" style="display:none"></div>';
  messagesArea.appendChild(wrap);
  messagesArea.scrollTop = messagesArea.scrollHeight;

  var emailInput = wrap.querySelector('input[type="email"]');
  var zipInput = wrap.querySelector('.sw-zip-input');
  var emailBtn = wrap.querySelector('button');
  var emailMsg = wrap.querySelector('.sw-chat-email-msg');

  emailBtn.addEventListener('click', function() {
    var email = emailInput.value.trim();
    var zip = zipInput.value.trim();
    if (!email || !/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(email)) return;
    if (!zip || !/^\\d{5}$/.test(zip)) {
      emailMsg.style.display = 'block';
      emailMsg.className = 'sw-chat-email-err';
      emailMsg.textContent = 'Please enter a valid 5-digit ZIP code.';
      zipInput.focus();
      return;
    }
    emailBtn.disabled = true;
    emailBtn.textContent = '...';
    var slug = window.location.pathname.split('/').pop() || '';
    fetch(SUBSCRIBE_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email,
        zip: zip,
        source: 'chat',
        content_slug: slug
      })
    })
    .then(function(r) { return r.json(); })
    .then(function(res) {
      if (res.success || !res.error) {
        wrap.querySelector('.sw-chat-email-fields').style.display = 'none';
        emailMsg.style.display = 'block';
        emailMsg.className = 'sw-chat-email-ok';
        emailMsg.textContent = 'Done! Check your inbox.';
        track('chat_email_capture', { trigger: trigger });
      } else {
        emailBtn.disabled = false;
        emailBtn.textContent = 'Send';
        emailMsg.style.display = 'block';
        emailMsg.className = 'sw-chat-email-err';
        emailMsg.textContent = 'Something went wrong. Try again.';
      }
    })
    .catch(function() {
      emailBtn.disabled = false;
      emailBtn.textContent = 'Send';
      emailMsg.style.display = 'block';
      emailMsg.className = 'sw-chat-email-err';
      emailMsg.textContent = 'Something went wrong. Try again.';
    });
  });
}

function showLoading() {
  var div = document.createElement('div');
  div.className = 'sw-chat-loading';
  div.id = 'sw-loading';
  div.innerHTML = '<span class="sw-chat-dot"></span><span class="sw-chat-dot"></span><span class="sw-chat-dot"></span> Looking through our articles...';
  messagesArea.appendChild(div);
  messagesArea.scrollTop = messagesArea.scrollHeight;
}

function hideLoading() {
  var el = messagesArea.querySelector('#sw-loading');
  if (el) el.remove();
}

function showTurnLimit() {
  var div = document.createElement('div');
  div.className = 'sw-chat-limit';
  div.innerHTML = "I've shared what I can. For the full picture, browse our " +
    '<a href="/guides">Guides</a> or ' +
    '<a href="/protect">Protection Tips</a>.' +
    '<br><button class="sw-chat-new-btn">Start new conversation</button>';
  messagesArea.appendChild(div);
  messagesArea.scrollTop = messagesArea.scrollHeight;

  var newBtn = div.querySelector('.sw-chat-new-btn');
  newBtn.addEventListener('click', function() {
    history = [];
    turnNumber = 0;
    saveSession();
    messagesArea.innerHTML = '';
    addSuggestions(getSuggestions());
    inputField.disabled = false;
    sendBtn.disabled = false;
  });

  inputField.disabled = true;
  sendBtn.disabled = true;
}

// === SSE streaming ===
function sendMessage(text) {
  if (isStreaming || !text.trim()) return;
  if (turnNumber >= MAX_TURNS) {
    showTurnLimit();
    return;
  }

  var cleanText = text.replace(/<[^>]*>/g, '').replace(/[\\[\\](){}*_~\`#>|]/g, '').trim().slice(0, MAX_MSG_LEN);
  if (!cleanText) return;

  isStreaming = true;
  turnNumber++;
  inputField.value = '';
  inputField.disabled = true;
  sendBtn.disabled = true;

  // Remove old suggestions
  var oldChips = messagesArea.querySelectorAll('.sw-chat-suggestions');
  for (var i = 0; i < oldChips.length; i++) oldChips[i].remove();

  // Add user message
  addMessage('user', esc(cleanText));
  history.push({ role: 'user', content: cleanText });

  // Auto-capture ZIP from user message (5-digit pattern)
  var zipMatch = cleanText.match(/\\b(\\d{5})\\b/);
  if (zipMatch) capturedZip = zipMatch[1];

  // Classify intent for tracking
  var intent = 'content_qa';
  var lower = cleanText.toLowerCase();
  if (/scam|fraud|suspicious|hacked|stolen|gave them/.test(lower)) intent = 'scam_triage';
  else if (/discount|deals|near me|coupon|save money/.test(lower)) intent = 'discount_lookup';
  track('chat_message_sent', { intent: intent, page_context: window.location.pathname, turn_number: turnNumber });

  showLoading();

  // SSE request
  fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: cleanText,
      page_context: window.location.pathname,
      history: history.slice(-8),
      turn_number: turnNumber
    })
  })
  .then(function(response) {
    if (response.status === 429) {
      hideLoading();
      addMessage('assistant', "You're asking great questions! Give me a moment to catch up. Try again in about a minute.");
      isStreaming = false;
      inputField.disabled = false;
      sendBtn.disabled = !!inputField.value;
      track('chat_error', { error_type: 'rate_limit' });
      return;
    }

    if (!response.ok || !response.body) {
      hideLoading();
      addMessage('assistant', "I'm having trouble right now. Try our <a href=\\"/search\\">search</a> or browse <a href=\\"/guides\\">Guides</a>.");
      isStreaming = false;
      inputField.disabled = false;
      sendBtn.disabled = !!inputField.value;
      track('chat_error', { error_type: 'api_timeout' });
      return;
    }

    var contentType = response.headers.get('content-type') || '';

    // Handle non-streaming JSON responses (turn limit)
    if (contentType.includes('application/json')) {
      return response.json().then(function(data) {
        hideLoading();
        if (data.type === 'turn_limit') {
          showTurnLimit();
        } else if (data.error) {
          addMessage('assistant', esc(data.error));
        }
        isStreaming = false;
        inputField.disabled = false;
        sendBtn.disabled = !inputField.value;
      });
    }

    // SSE streaming
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    var assistantDiv = null;
    var fullText = '';

    hideLoading();

    function processChunk() {
      return reader.read().then(function(result) {
        if (result.done) {
          // Finalize
          if (fullText) {
            history.push({ role: 'assistant', content: fullText });
            saveSession();
          }
          isStreaming = false;
          inputField.disabled = false;
          sendBtn.disabled = !inputField.value;
          inputField.focus();
          return;
        }

        buffer += decoder.decode(result.value, { stream: true });
        var lines = buffer.split('\\n');
        buffer = lines.pop() || '';

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i].trim();
          if (!line.startsWith('data: ')) continue;
          var json = line.slice(6);
          try {
            var evt = JSON.parse(json);
            if (evt.type === 'token' && evt.text) {
              fullText += evt.text;
              if (!assistantDiv) {
                assistantDiv = addMessage('assistant', '');
              }
              assistantDiv.innerHTML = renderMarkdown(esc(fullText));
              messagesArea.scrollTop = messagesArea.scrollHeight;
            }
            else if (evt.type === 'sources' && evt.articles) {
              addSources(evt.articles);
            }
            else if (evt.type === 'suggestions' && evt.questions) {
              addSuggestions(evt.questions);
            }
            else if (evt.type === 'email_prompt' && evt.trigger) {
              addEmailCapture(evt.trigger);
            }
            else if (evt.type === 'error' && evt.text) {
              if (!assistantDiv) {
                assistantDiv = addMessage('assistant', '');
              }
              assistantDiv.innerHTML = renderMarkdown(esc(evt.text));
              track('chat_error', { error_type: 'api_timeout' });
            }
          } catch(e) {}
        }

        return processChunk();
      });
    }

    return processChunk();
  })
  .catch(function(err) {
    hideLoading();
    addMessage('assistant', "I'm having trouble right now. Try our <a href=\\"/search\\">search</a> or browse <a href=\\"/guides\\">Guides</a>.");
    isStreaming = false;
    inputField.disabled = false;
    sendBtn.disabled = !inputField.value;
    track('chat_error', { error_type: 'api_timeout' });
  });
}

// === Open / Close ===
function openPanel() {
  isOpen = true;
  panel.classList.add('sw-open');
  fab.style.display = 'none';
  openTime = Date.now();
  track('chat_open', { page_context: window.location.pathname });

  // Show initial suggestions or restore history
  if (history.length === 0) {
    addSuggestions(getSuggestions());
  } else {
    // Restore previous messages
    for (var i = 0; i < history.length; i++) {
      addMessage(history[i].role, history[i].role === 'user' ? esc(history[i].content) : renderMarkdown(esc(history[i].content)));
    }
    if (turnNumber < MAX_TURNS) {
      addSuggestions(getSuggestions());
    } else {
      showTurnLimit();
    }
  }

  inputField.focus();
}

function closePanel() {
  var msgCount = history.length;
  var duration = openTime ? Math.round((Date.now() - openTime) / 1000) : 0;
  track('chat_close', { messages_count: msgCount, duration_seconds: duration });

  isOpen = false;
  panel.classList.remove('sw-open');
  fab.style.display = 'flex';
  messagesArea.innerHTML = '';
  fab.focus();
}

// === Event listeners ===
fab.addEventListener('click', openPanel);
closeBtn.addEventListener('click', closePanel);

inputField.addEventListener('input', function() {
  sendBtn.disabled = !inputField.value.trim() || isStreaming;
});

inputField.addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (inputField.value.trim() && !isStreaming) {
      sendMessage(inputField.value);
    }
  }
});

sendBtn.addEventListener('click', function() {
  if (inputField.value.trim() && !isStreaming) {
    sendMessage(inputField.value);
  }
});

// Escape to close
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && isOpen) {
    closePanel();
  }
});

// Mobile: handle virtual keyboard resize
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', function() {
    if (isOpen) {
      var vh = window.visualViewport.height;
      panel.style.height = Math.min(vh - 16, 520) + 'px';
    }
  });
}

})();`;

// ---------------------------------------------------------------------------
// Build the minified widget bundle
// ---------------------------------------------------------------------------
export function buildChatWidgetJs(): string {
  return CHAT_WIDGET_JS.replace("'__CHAT_CSS__'", JSON.stringify(CHAT_WIDGET_CSS));
}

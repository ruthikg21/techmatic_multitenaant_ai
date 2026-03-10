/*!
 * Techmatic AI Chatbot — Embeddable Widget v2.0
 *
 * USAGE: Add this to the client's website before </body>:
 *
 *   <script>
 *     window.TM_WIDGET_CONFIG = {
 *       apiKey: "tm_xxxxxxxxxxxx",
 *       serverUrl: "https://your-server.com"
 *     };
 *   </script>
 *   <script src="https://your-server.com/static/widget/tm-chatbot.js" defer></script>
 *
 * That's it. The chatbot will appear in the bottom-right corner.
 */
(function () {
  'use strict';

  var CFG = window.TM_WIDGET_CONFIG || {};
  var API_KEY = CFG.apiKey || '';
  var SERVER = (CFG.serverUrl || '').replace(/\/$/, '');
  var SK = 'tm_sid';   // sessionStorage key

  if (!API_KEY || !SERVER) {
    console.error('[Techmatic AI] Missing apiKey or serverUrl in TM_WIDGET_CONFIG');
    return;
  }

  /* ─── helpers ─────────────────────────────────────────────── */
  function sid() {
    var s = sessionStorage.getItem(SK);
    if (!s) {
      s = 'web_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
      sessionStorage.setItem(SK, s);
    }
    return s;
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function hhmm() {
    var d = new Date(), h = d.getHours(), m = d.getMinutes();
    var a = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return h + ':' + (m < 10 ? '0' : '') + m + ' ' + a;
  }

  function post(path, body) {
    return fetch(SERVER + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); });
  }

  /* ─── inject CSS ────────────────────────────────────────────── */
  var css = [
    '/* Techmatic AI Widget — scoped under #tm-widget */',
    '#tm-widget, #tm-widget * {',
    '  box-sizing: border-box;',
    "  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;",
    '  margin: 0; padding: 0; line-height: 1.5;',
    '}',
    '#tm-fab {',
    '  position: fixed; bottom: 20px; right: 20px;',
    '  height: 58px; border-radius: 29px;',
    '  background: linear-gradient(135deg, #f59e0b 0%, #ea580c 100%);',
    '  border: none; cursor: pointer; z-index: 99990;',
    '  display: flex !important; align-items: center; justify-content: space-between;',
    '  padding: 0 8px 0 20px; gap: 12px;',
    '  box-shadow: 0 6px 20px rgba(234,88,12,0.40), 0 2px 8px rgba(0,0,0,0.15);',
    '  transition: all .25s cubic-bezier(.34,1.56,.64,1);',
    '  outline: none; overflow: hidden;',
    '}',
    '#tm-fab-text { color: #fff; font-size: 15px; font-weight: 600; white-space: nowrap; }',
    '#tm-fab-icon { width: 42px; height: 42px; border-radius: 50%; background: rgba(255,255,255,0.2); display: flex !important; align-items: center; justify-content: center; position: relative; flex-shrink: 0; }',
    '#tm-fab:hover { transform: translateY(-3px) scale(1.03); box-shadow: 0 10px 25px rgba(234,88,12,0.50), 0 4px 12px rgba(0,0,0,0.20); }',
    '#tm-fab svg { width: 24px; height: 24px; fill: #fff; position: absolute; transition: transform .3s ease, opacity .25s ease; }',
    '#tm-fab .ic-chat  { opacity:1; transform:scale(1) rotate(0deg); }',
    '#tm-fab .ic-close { opacity:0; transform:scale(.6) rotate(-90deg); }',
    '#tm-fab.open { width: 58px; padding: 0; justify-content: center; gap: 0; background: linear-gradient(135deg, #dc3545 0%, #212529 100%); box-shadow: 0 6px 20px rgba(220,53,69,0.50), 0 2px 8px rgba(0,0,0,0.20); }',
    '#tm-fab.open #tm-fab-text { display: none; }',
    '#tm-fab.open #tm-fab-icon { width: 58px; height: 58px; background: transparent; }',
    '#tm-fab.open .ic-chat  { opacity:0; transform:scale(.6) rotate(90deg); }',
    '#tm-fab.open .ic-close { opacity:1; transform:scale(1) rotate(0deg); }',
    '#tm-badge {',
    '  position: absolute; top: -3px; right: -3px;',
    '  width: 20px; height: 20px; background: #fff; color: #dc3545;',
    '  border: 2px solid #dc3545; border-radius: 50%; font-size: 10px; font-weight: 700;',
    '  display: none; align-items: center; justify-content: center; z-index: 1;',
    '}',
    '#tm-badge.show { display: flex; }',
    '#tm-win {',
    '  position: fixed; bottom: 90px; right: 20px;',
    '  width: 370px; height: 620px; max-height: calc(100vh - 120px); background: #fff;',
    '  border-radius: 18px; box-shadow: 0 24px 64px rgba(0,0,0,0.22), 0 0 0 1px rgba(0,0,0,0.06);',
    '  z-index: 99989; display: flex !important; flex-direction: column; overflow: hidden;',
    '  opacity: 0; pointer-events: none; transform: scale(.88) translateY(18px);',
    '  transform-origin: bottom right;',
    '  transition: opacity .28s ease, transform .3s cubic-bezier(.34,1.56,.64,1);',
    '}',
    '#tm-win.open { opacity: 1; pointer-events: all; transform: scale(1) translateY(0); }',
    '#tm-head {',
    '  background: linear-gradient(135deg, #dc3545 0%, #212529 100%);',
    '  padding: 13px 14px !important; display: flex !important; align-items: center; gap: 11px; flex-shrink: 0;',
    '}',
    '.tm-hav { width: 40px; height: 40px; border-radius: 50%; background: rgba(255,255,255,.18);',
    '  display: flex !important; align-items: center; justify-content: center; flex-shrink: 0; position: relative; }',
    '.tm-hav svg { width: 20px; height: 20px; fill: #fff; }',
    '.tm-online { position: absolute; bottom: 1px; right: 1px; width: 10px; height: 10px;',
    '  background: #28a745; border-radius: 50%; border: 2px solid #dc3545; animation: tm-pulse 2.4s infinite; }',
    '@keyframes tm-pulse { 0%,100%{box-shadow:0 0 0 0 rgba(40,167,69,.45)} 60%{box-shadow:0 0 0 5px rgba(40,167,69,0)} }',
    '.tm-hinfo { flex:1; min-width:0; }',
    '.tm-hinfo h4 { color: #fff; font-size: 14.5px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 !important; margin: 0 !important; }',
    '.tm-hinfo p { color:rgba(255,255,255,.78); font-size:11.5px; margin-top:2px !important; padding: 0 !important; }',
    '#tm-xbtn { background: rgba(255,255,255,.15); border: none; width: 28px; height: 28px;',
    '  border-radius: 50%; cursor: pointer; color: #fff; font-size: 18px; line-height: 1;',
    '  display: flex !important; align-items: center; justify-content: center; transition: background .2s; flex-shrink: 0; }',
    '#tm-xbtn:hover { background: rgba(255,255,255,.30); }',
    '#tm-msgs { flex: 1; overflow-y: auto; padding: 14px 12px !important; background: #f8f9fa;',
    '  display: flex !important; flex-direction: column; gap: 6px; scroll-behavior: smooth; }',
    '#tm-msgs::-webkit-scrollbar { width: 4px; }',
    '#tm-msgs::-webkit-scrollbar-track { background: transparent; }',
    '#tm-msgs::-webkit-scrollbar-thumb { background: #ced4da; border-radius: 2px; }',
    '.tm-row { display: flex !important; align-items: flex-end; gap: 7px; animation: tm-rise .22s ease-out; }',
    '.tm-row.u { justify-content: flex-end; }',
    '@keyframes tm-rise { from{opacity:0;transform:translateY(7px)} to{opacity:1;transform:translateY(0)} }',
    '.tm-av { width: 28px; height: 28px; border-radius: 50%;',
    '  background: linear-gradient(135deg, #dc3545, #212529);',
    '  display: flex !important; align-items: center; justify-content: center; flex-shrink: 0; align-self: flex-end; }',
    '.tm-av svg { width: 13px; height: 13px; fill: #fff; }',
    '.tm-bw { max-width: 78%; display: flex !important; flex-direction: column; }',
    '.tm-row.u .tm-bw { align-items: flex-end; }',
    '#tm-widget .tm-bbl { padding: 9px 13px !important; font-size: 13.5px; line-height: 1.55; word-break: break-word; white-space: pre-wrap; display: block !important; width: fit-content; text-align: left; }',
    '#tm-widget .tm-row.b .tm-bbl { background: #fff; color: #212529; border-radius: 4px 14px 14px 14px;',
    '  box-shadow: 0 1px 4px rgba(0,0,0,.09); }',
    '#tm-widget .tm-row.u .tm-bbl { background: linear-gradient(135deg, #dc3545, #c82333) !important;',
    '  color: #fff !important; border-radius: 14px 14px 4px 14px; }',
    '.tm-t { font-size: 10px; color: #adb5bd; margin-top: 3px !important; display: block; }',
    '.tm-row.u .tm-t { text-align: right; }',
    '.tm-typing { display: flex !important; align-items: flex-end; gap: 7px; }',
    '.tm-tbbl { background: #fff; border-radius: 4px 14px 14px 14px; padding: 10px 14px !important;',
    '  display: flex !important; gap: 5px; align-items: center; box-shadow: 0 1px 4px rgba(0,0,0,.09); }',
    '.tm-d { width: 7px; height: 7px; background: #dc3545; border-radius: 50%; animation: tm-dot 1.1s infinite; }',
    '.tm-d:nth-child(2){ animation-delay:.16s; }',
    '.tm-d:nth-child(3){ animation-delay:.32s; }',
    '@keyframes tm-dot { 0%,60%,100%{transform:translateY(0);opacity:.4} 30%{transform:translateY(-5px);opacity:1} }',
    '#tm-qr { padding: 8px 12px 6px !important; display: flex !important; gap: 7px; flex-wrap: wrap;',
    '  background: #f8f9fa; border-top: 1px solid #e9ecef; }',
    '#tm-qr.hidden { display: none !important; }',
    ".tm-qb { background: #fff; border: 1.5px solid #dc3545 !important; color: #dc3545 !important;",
    "  font-size: 12px; font-weight: 500; padding: 5px 12px !important; border-radius: 50px;",
    "  cursor: pointer; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;",
    '  transition: all .2s; white-space: nowrap; }',
    '.tm-qb:hover { background: #dc3545 !important; color: #fff !important; }',
    '#tm-bar { padding: 10px 12px !important; background: #fff; border-top: 1px solid #e9ecef;',
    '  display: flex !important; gap: 9px; align-items: flex-end; flex-shrink: 0; }',
    "#tm-inp { flex: 1; border: 1.5px solid #dee2e6 !important; border-radius: 22px;",
    "  padding: 9px 14px !important; font-size: 13.5px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;",
    '  color: #212529 !important; resize: none; outline: none; line-height: 1.4; max-height: 90px;',
    '  overflow-y: auto; background: #f8f9fa; transition: border-color .2s, background .2s; }',
    '#tm-inp:focus { border-color: #dc3545 !important; background: #fff !important; }',
    '#tm-inp::placeholder { color: #adb5bd !important; }',
    '#tm-send { width: 38px; height: 38px; border-radius: 50%;',
    '  background: linear-gradient(135deg, #dc3545, #212529);',
    '  border: none; cursor: pointer; display: flex !important; align-items: center; justify-content: center;',
    '  flex-shrink: 0; box-shadow: 0 3px 10px rgba(220,53,69,.35);',
    '  transition: transform .2s, opacity .2s; outline: none; }',
    '#tm-send:hover { transform: scale(1.1); }',
    '#tm-send:disabled { opacity:.35 !important; cursor:not-allowed; transform:none; }',
    '#tm-send svg { width:16px; height:16px; fill:#fff; }',
    '#tm-pow { text-align: center; font-size: 10.5px; color: #adb5bd !important;',
    '  padding: 5px 0 9px !important; background: #fff; flex-shrink: 0; }',
    '#tm-pow a { color: #adb5bd !important; text-decoration: none; }',
    '#tm-pow a:hover { text-decoration: underline; }',
    '#tm-pow b { color: #dc3545 !important; }',
    '@media (max-width: 480px) {',
    '  #tm-win { bottom: 0; right: 0; width: 100vw; height: 92vh; border-radius: 18px 18px 0 0; }',
    '  #tm-fab { bottom: 80px; right: 16px; }',
    '}'
  ].join('\n');

  var styleEl = document.createElement('style');
  styleEl.id = 'tm-widget-css';
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  /* ─── build DOM ────────────────────────────────────────────── */
  function buildDOM() {
    var el = document.createElement('div');
    el.id = 'tm-widget';
    el.innerHTML =
      '<button id="tm-fab" title="Chat with us">' +
      '<span id="tm-fab-text">Hi there! Need help?</span>' +
      '<div id="tm-fab-icon">' +
      '<svg class="ic-chat" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>' +
      '<svg class="ic-close" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>' +
      '<span id="tm-badge">1</span>' +
      '</div>' +
      '</button>' +
      '<div id="tm-win">' +
      '<div id="tm-head">' +
      '<div class="tm-hav">' +
      '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>' +
      '<span class="tm-online"></span>' +
      '</div>' +
      '<div class="tm-hinfo">' +
      '<h4 id="tm-title">AI Assistant</h4>' +
      '<p>Online &bull; replies instantly</p>' +
      '</div>' +
      '<button id="tm-xbtn">&times;</button>' +
      '</div>' +
      '<div id="tm-msgs"></div>' +
      '<div id="tm-qr" class="hidden"></div>' +
      '<div id="tm-bar">' +
      '<textarea id="tm-inp" rows="1" placeholder="Type a message…"></textarea>' +
      '<button id="tm-send" disabled>' +
      '<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>' +
      '</button>' +
      '</div>' +
      '<div id="tm-pow"><a href="https://techmaticsys.com" target="_blank" rel="noopener noreferrer">Powered by <b>Matic AI</b></a></div>' +
      '</div>';
    document.body.appendChild(el);
  }

  /* ─── state ────────────────────────────────────────────────── */
  var open = false;
  var typing = false;
  var booted = false;
  var unread = 0;
  var session = '';

  /* ─── UI helpers ───────────────────────────────────────────── */
  function addMsg(role, text, animate) {
    var msgs = document.getElementById('tm-msgs');
    var isU = (role === 'user');
    var row = document.createElement('div');
    row.className = 'tm-row ' + (isU ? 'u' : 'b');
    if (!animate) row.style.animation = 'none';

    var av = isU ? '' :
      '<div class="tm-av"><svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg></div>';

    row.innerHTML = av +
      '<div class="tm-bw">' +
      '<div class="tm-bbl">' + esc(text).replace(/\n/g, '<br>') + '</div>' +
      '<span class="tm-t">' + hhmm() + '</span>' +
      '</div>';

    msgs.appendChild(row);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function showTyping() {
    var msgs = document.getElementById('tm-msgs');
    var row = document.createElement('div');
    row.id = 'tm-trow'; row.className = 'tm-typing';
    row.innerHTML =
      '<div class="tm-av"><svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg></div>' +
      '<div class="tm-tbbl"><div class="tm-d"></div><div class="tm-d"></div><div class="tm-d"></div></div>';
    msgs.appendChild(row);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function hideTyping() {
    var t = document.getElementById('tm-trow');
    if (t) t.remove();
  }

  function setQR(items) {
    var qr = document.getElementById('tm-qr');
    if (!items || !items.length) { qr.className = 'hidden'; return; }
    qr.className = '';
    qr.innerHTML = '';
    items.forEach(function (txt) {
      var b = document.createElement('button');
      b.className = 'tm-qb';
      b.textContent = txt;
      b.onclick = function () { send(txt); };
      qr.appendChild(b);
    });
  }

  function clearQR() { setQR([]); }

  /* ─── send message ─────────────────────────────────────────── */
  function send(text) {
    text = (text || document.getElementById('tm-inp').value).trim();
    if (!text || typing) return;

    clearQR();
    document.getElementById('tm-inp').value = '';
    document.getElementById('tm-inp').style.height = 'auto';
    document.getElementById('tm-send').disabled = true;

    addMsg('user', text, true);
    typing = true;
    showTyping();

    post('/widget/chat', { message: text, session_id: session, api_key: API_KEY, source: 'web' })
      .then(function (d) {
        hideTyping();
        var reply = (d && d.reply) ? d.reply : 'Sorry, something went wrong. Please try again.';
        addMsg('bot', reply, true);
        if (!open) { unread++; var b = document.getElementById('tm-badge'); b.textContent = unread; b.classList.add('show'); }
      })
      .catch(function () {
        hideTyping();
        addMsg('bot', "I'm having trouble connecting right now. Please try again shortly.", true);
      })
      .finally(function () {
        typing = false;
        document.getElementById('tm-send').disabled = false;
        document.getElementById('tm-msgs').scrollTop = 9999;
      });
  }

  /* ─── open / close ─────────────────────────────────────────── */
  function openChat() {
    open = true;
    document.getElementById('tm-fab').classList.add('open');
    document.getElementById('tm-win').classList.add('open');
    unread = 0;
    document.getElementById('tm-badge').classList.remove('show');

    if (!booted) {
      booted = true;
      session = sid();

      /* try loading existing history first */
      fetch(SERVER + '/widget/messages?api_key=' + encodeURIComponent(API_KEY) + '&session_id=' + encodeURIComponent(session))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var ms = d.messages || [];
          if (ms.length) {
            ms.forEach(function (m) { addMsg(m.role === 'user' ? 'user' : 'bot', m.content, false); });
          } else {
            greet();
          }
        })
        .catch(greet);
    }

    setTimeout(function () {
      document.getElementById('tm-msgs').scrollTop = 9999;
      document.getElementById('tm-inp').focus();
    }, 320);
  }

  function greet() {
    fetch(SERVER + '/widget/config?api_key=' + encodeURIComponent(API_KEY))
      .then(function (r) { return r.json(); })
      .then(function (c) {
        var g = c.greeting || "Hello! 👋 How can I help you today?";
        var name = c.assistant_name || 'AI Assistant';
        document.getElementById('tm-title').textContent = name;
        addMsg('bot', g, true);
        setQR(['Tell me about your services', 'I need help', 'Book a consultation', 'Contact the team']);
      })
      .catch(function () {
        addMsg('bot', "Hello! 👋 How can I help you today?", true);
        setQR(['Tell me about your services', 'I need help', 'Contact the team']);
      });
  }

  function closeChat() {
    open = false;
    document.getElementById('tm-fab').classList.remove('open');
    document.getElementById('tm-win').classList.remove('open');
  }

  /* ─── init ─────────────────────────────────────────────────── */
  function init() {
    buildDOM();
    session = sid();

    document.getElementById('tm-fab').addEventListener('click', function () { open ? closeChat() : openChat(); });
    document.getElementById('tm-xbtn').addEventListener('click', closeChat);

    var inp = document.getElementById('tm-inp');
    var btn = document.getElementById('tm-send');

    btn.addEventListener('click', function () { send(); });
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    inp.addEventListener('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 90) + 'px';
      btn.disabled = !this.value.trim();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && open) closeChat();
    });

    /* Pre-fetch config to set title */
    fetch(SERVER + '/widget/config?api_key=' + encodeURIComponent(API_KEY))
      .then(function (r) { return r.json(); })
      .then(function (c) {
        if (c.assistant_name) {
          document.getElementById('tm-title').textContent = c.assistant_name;
          document.getElementById('tm-fab').title = 'Chat with ' + c.assistant_name;
        }
      })
      .catch(function () { });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

}());

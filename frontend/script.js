const state = {
  collections: [],
  selected_collection_id: null,
  selected_collection_name: null,
  current_session_id: null,
  documents: [],
  is_streaming: false,
};

function get_or_create_user_id() {
  let user_id = localStorage.getItem('guest_user_id');
  if (!user_id) {
    user_id = crypto.randomUUID();
    localStorage.setItem('guest_user_id', user_id);
  }
  return user_id;
}
const guest_user_id = get_or_create_user_id();

const API = {
  base: window.location.origin,
  headers: {
    'X-User-ID': guest_user_id
  },

  async get(path) {
    const resp = await fetch(this.base + path, { headers: this.headers });
    if (!resp.ok) throw new Error(await resp.text());
    return resp.json();
  },

  async post(path, body) {
    const resp = await fetch(this.base + path, {
      method: 'POST',
      headers: { ...this.headers, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(await resp.text());
    return resp.json();
  },

  async upload(path, form_data) {
    const resp = await fetch(this.base + path, { 
      method: 'POST', 
      headers: this.headers,
      body: form_data 
    });
    if (!resp.ok) throw new Error(await resp.text());
    return resp.json();
  },

  async delete(path) {
    const resp = await fetch(this.base + path, { method: 'DELETE', headers: this.headers });
    if (!resp.ok && resp.status !== 204) throw new Error(await resp.text());
  },
};

async function load_collections() {
  try {
    const data = await API.get('/api/v1/collections');
    state.collections = data.collections;
    render_collection_select();
  } catch (e) {
    console.error('Failed to load collections:', e);
  }
}

function render_collection_select() {
  const select = document.getElementById('collection-select');
  const current = select.value;
  select.innerHTML = '<option value="">Select a collection…</option>';
  state.collections.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.name;
    select.appendChild(opt);
  });
  if (current) select.value = current;
}

document.getElementById('create-collection-btn').addEventListener('click', async () => {
  const name_input = document.getElementById('new-collection-name');
  const name = name_input.value.trim();
  if (!name) return alert('Enter a collection name first.');
  try {
    const col = await API.post('/api/v1/collections', { name });
    state.collections.push(col);
    render_collection_select();
    document.getElementById('collection-select').value = col.id;
    name_input.value = '';
    on_collection_change(col.id, col.name);
  } catch (e) {
    alert('Failed to create collection: ' + e.message);
  }
});

document.getElementById('collection-select').addEventListener('change', function () {
  const col = state.collections.find(c => c.id === this.value);
  const del_btn = document.getElementById('delete-collection-btn');
  del_btn.disabled = !this.value;
  if (col) on_collection_change(col.id, col.name);
});

document.getElementById('delete-collection-btn').addEventListener('click', async () => {
  const col_id = state.selected_collection_id;
  const col_name = state.selected_collection_name;
  if (!col_id) return;
  if (!confirm(`Delete collection "${col_name}" and ALL its documents and chat history?\n\nThis cannot be undone.`)) return;
  try {
    await API.delete(`/api/v1/collections/${col_id}`);
    state.collections = state.collections.filter(c => c.id !== col_id);
    state.selected_collection_id = null;
    state.selected_collection_name = null;
    state.current_session_id = null;
    state.documents = [];
    render_collection_select();
    render_doc_list();
    document.getElementById('delete-collection-btn').disabled = true;
    document.getElementById('chat-collection-label').textContent = 'No collection selected';
    document.getElementById('chat-session-label').textContent = 'Start a conversation on the left';
    document.getElementById('send-btn').disabled = true;
    document.getElementById('messages-area').innerHTML = `
      <div class="empty-state" id="empty-state">

        <div class="empty-state-title">Ask anything about your documents</div>
        <div class="empty-state-hint">Upload a PDF on the left, select a collection, then type your question below.</div>
      </div>`;
  } catch (e) {
    alert('Failed to delete collection: ' + e.message);
  }
});

async function delete_document(doc_id, filename) {
  if (!confirm(`Remove "${filename}" from this collection?\n\nThis will delete all its indexed chunks. This cannot be undone.`)) return;
  try {
    await API.delete(`/api/v1/documents/${doc_id}`);
    state.documents = state.documents.filter(d => d.id !== doc_id);
    render_doc_list();
  } catch (e) {
    alert('Failed to delete document: ' + e.message);
  }
}

function on_collection_change(collection_id, collection_name) {
  state.selected_collection_id = collection_id;
  state.selected_collection_name = collection_name;
  state.current_session_id = null;
  state.documents = [];
  document.getElementById('chat-collection-label').textContent = collection_name;
  document.getElementById('chat-session-label').textContent = 'New session';
  document.getElementById('send-btn').disabled = false;
  const area = document.getElementById('messages-area');
  area.innerHTML = `
    <div class="empty-state" id="empty-state">

      <div class="empty-state-title">Ask anything about your documents</div>
      <div class="empty-state-hint">
        Upload a PDF on the left, select a collection, then ask a question.
        The system will search the documents and write a response citing the sources.
      </div>
    </div>`;
  load_documents(collection_id);
  load_latest_session_history(collection_id);
}

async function load_documents(collection_id) {
  try {
    const data = await API.get(`/api/v1/collections/${collection_id}/documents`);
    state.documents = data.documents.map(d => ({
      id: d.id,
      filename: d.filename,
      status: d.status,
      chunk_count: d.chunk_count,
    }));
    render_doc_list();
    state.documents.filter(d => d.status === 'processing').forEach(d => {
      poll_document_status(d.id);
    });
  } catch (e) {
    console.error('Failed to load documents:', e);
    state.documents = [];
    render_doc_list();
  }
}

function render_doc_list() {
  const list = document.getElementById('doc-list');
  if (!state.documents.length) {
    list.innerHTML = '<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:16px;">No documents yet. Upload a PDF above.</div>';
    return;
  }
  list.innerHTML = '';
  state.documents.forEach(doc => {
    const item = document.createElement('div');
    item.className = 'doc-item';
    item.dataset.docId = doc.id;
    item.innerHTML = `
      <span class="doc-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg></span>
      <span class="doc-name" title="${doc.filename}">${doc.filename}</span>
      <span class="status-badge status-${doc.status}" id="status-${doc.id}">${doc.status}</span>
      <button class="doc-delete-btn" title="Remove document"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"></path><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></button>
    `;
    item.querySelector('.doc-delete-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      delete_document(doc.id, doc.filename);
    });
    list.appendChild(item);
  });
}

const dropzone = document.getElementById('dropzone');
const file_input = document.getElementById('file-input');

dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) handle_upload(file);
});

file_input.addEventListener('change', e => {
  if (e.target.files[0]) handle_upload(e.target.files[0]);
});

async function handle_upload(file) {
  if (!state.selected_collection_id) {
    return alert('Please select or create a collection first.');
  }
  if (!file.name.endsWith('.pdf')) {
    return alert('Only PDF files are supported.');
  }

  const status_el = document.getElementById('upload-status');
  const progress_wrap = document.getElementById('progress-wrap');
  const progress_fill = document.getElementById('progress-fill');

  progress_wrap.style.display = 'block';
  progress_fill.style.width = '30%';
  status_el.textContent = `Uploading ${file.name}…`;

  try {
    const form = new FormData();
    form.append('file', file);
    const doc = await API.upload(`/api/v1/collections/${state.selected_collection_id}/documents`, form);

    progress_fill.style.width = '60%';
    status_el.textContent = 'Processing…';

    state.documents.push({ id: doc.document_id, filename: doc.filename, status: 'processing' });
    render_doc_list();

    poll_document_status(doc.document_id);
  } catch (e) {
    status_el.textContent = 'Upload failed: ' + e.message;
    progress_fill.style.width = '0%';
  }
}

async function poll_document_status(doc_id) {
  const poll_interval = setInterval(async () => {
    try {
      const data = await API.get(`/api/v1/documents/${doc_id}/status`);
      const doc = state.documents.find(d => d.id === doc_id);
      if (doc) doc.status = data.status;

      const badge = document.getElementById(`status-${doc_id}`);
      if (badge) {
        badge.textContent = data.status;
        badge.className = `status-badge status-${data.status}`;
      }

      if (data.status === 'done') {
        clearInterval(poll_interval);
        document.getElementById('upload-status').textContent = `Done: ${data.chunk_count} chunks ready`;
        document.getElementById('progress-fill').style.width = '100%';
        setTimeout(() => {
          document.getElementById('progress-wrap').style.display = 'none';
          document.getElementById('upload-status').textContent = '';
        }, 2000);
      } else if (data.status === 'failed') {
        clearInterval(poll_interval);
        document.getElementById('upload-status').textContent = `Error: ${data.error_message}`;
      }
    } catch (e) {
      clearInterval(poll_interval);
    }
  }, 2000);
}

document.getElementById('new-session-btn').addEventListener('click', () => {
  state.current_session_id = null;
  document.getElementById('chat-session-label').textContent = 'New session';
  document.getElementById('messages-area').innerHTML = '';
  document.getElementById('empty-state') && document.getElementById('messages-area').appendChild(
    Object.assign(document.createElement('div'), { className: 'empty-state', innerHTML: `

      <div class="empty-state-title">New conversation started</div>
      <div class="empty-state-hint">Ask a question about your documents.</div>
    `})
  );
});

const chat_input = document.getElementById('chat-input');
const send_btn = document.getElementById('send-btn');

chat_input.addEventListener('input', function () {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
  send_btn.disabled = !this.value.trim() || !state.selected_collection_id || state.is_streaming;
});

chat_input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!send_btn.disabled) send_message();
  }
});

send_btn.addEventListener('click', send_message);

async function send_message() {
  const question = chat_input.value.trim();
  if (!question || !state.selected_collection_id || state.is_streaming) return;

  chat_input.value = '';
  chat_input.style.height = '44px';
  send_btn.disabled = true;
  state.is_streaming = true;

  document.getElementById('empty-state')?.remove();

  add_user_message(question);

  const assistant_el = add_assistant_placeholder();

  try {
    const response = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'X-User-ID': guest_user_id
      },
      body: JSON.stringify({
        question,
        collection_id: state.selected_collection_id,
        session_id: state.current_session_id || null,
      }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const event = JSON.parse(line.slice(6));
            handle_sse_event(event, assistant_el);
          } catch (e) { }
        }
      }
    }
  } catch (e) {
    assistant_el.querySelector('.message-bubble').textContent = 'Error: ' + e.message;
  } finally {
    state.is_streaming = false;
    send_btn.disabled = !chat_input.value.trim() || !state.selected_collection_id;
    assistant_el.querySelector('.typing-indicator')?.remove();
  }
}

function handle_sse_event(event, el) {
  const bubble = el.querySelector('.message-bubble');
  const meta = el.querySelector('.message-meta');

  switch (event.type) {
    case 'retrieval': {
      let indicator = el.querySelector('.retrieval-indicator');
      if (!indicator) {
        indicator = document.createElement('div');
        indicator.className = 'retrieval-indicator';
        el.insertBefore(indicator, bubble);
      }
      indicator.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle;"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg> Searching documents…`;
      break;
    }
    case 'token': {
      el.querySelector('.retrieval-indicator')?.remove();

      bubble.querySelector('.typing-indicator')?.remove();
      bubble.insertAdjacentText('beforeend', event.content);
      el.scrollIntoView({ block: 'end', behavior: 'smooth' });
      break;
    }
    case 'sources': {
      const sources_row = document.createElement('div');
      sources_row.className = 'sources-row';
      event.data.forEach(src => {
        const chip = document.createElement('div');
        chip.className = 'source-chip';
        chip.innerHTML = `<span class="source-chip-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg></span> ${src.source} — Page ${src.page}`;
        chip.addEventListener('click', () => show_source_modal(src));
        sources_row.appendChild(chip);
      });
      bubble.appendChild(sources_row);
      break;
    }
    case 'eval': {
      // Scores are calculated and logged in the backend, but hidden from the UI.
      break;
    }
    case 'generation_done': {
      state.is_streaming = false;
      const chat_input = document.getElementById('chat-input');
      const send_btn = document.getElementById('send-btn');
      send_btn.disabled = !chat_input.value.trim() || !state.selected_collection_id;
      break;
    }
    case 'done': {
      if (event.session_id) {
        state.current_session_id = event.session_id;
        document.getElementById('chat-session-label').textContent = `Session: ${event.session_id.slice(0, 8)}…`;
      }
      break;
    }
  }
}

function add_user_message(text) {
  const area = document.getElementById('messages-area');
  const el = document.createElement('div');
  el.className = 'message message-user';
  el.innerHTML = `<div class="message-bubble">${escape_html(text)}</div>`;
  area.appendChild(el);
  el.scrollIntoView({ block: 'end', behavior: 'smooth' });
}

function add_assistant_placeholder() {
  const area = document.getElementById('messages-area');
  const el = document.createElement('div');
  el.className = 'message message-assistant';
  el.innerHTML = `
    <div class="message-bubble">
      <div class="typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>
    <div class="message-meta"></div>
  `;
  area.appendChild(el);
  el.scrollIntoView({ block: 'end', behavior: 'smooth' });
  return el;
}

async function load_latest_session_history(collection_id) {
  try {
    const data = await API.get(`/api/v1/chat/collections/${collection_id}/sessions`);
    if (data.sessions && data.sessions.length > 0) {
      const latest_session = data.sessions[0];
      state.current_session_id = latest_session.id;
      document.getElementById('chat-session-label').textContent = `Session: ${latest_session.id.slice(0, 8)}…`;
      await load_session_messages(latest_session.id);
    }
  } catch (e) {
    console.error('Failed to load session history:', e);
  }
}

async function load_session_messages(session_id) {
  try {
    const data = await API.get(`/api/v1/chat/sessions/${session_id}/messages`);
    const area = document.getElementById('messages-area');
    if (data.messages && data.messages.length > 0) {
      document.getElementById('empty-state')?.remove();
      area.innerHTML = '';
      data.messages.forEach(msg => {
        render_message_into_area(msg, area);
      });
      const last_msg = area.lastElementChild;
      if (last_msg) last_msg.scrollIntoView({ block: 'end' });
    }
  } catch (e) {
    console.error('Failed to load messages:', e);
  }
}

function render_message_into_area(msg, area) {
  const el = document.createElement('div');
  el.className = `message message-${msg.role}`;
  
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = msg.content;
  el.appendChild(bubble);
  
  if (msg.role === 'assistant' && msg.sources && msg.sources.length > 0) {
    const sources_row = document.createElement('div');
    sources_row.className = 'sources-row';
    msg.sources.forEach(src => {
      const chip = document.createElement('div');
      chip.className = 'source-chip';
      chip.innerHTML = `<span class="source-chip-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg></span> ${src.source} — Page ${src.page}`;
      chip.addEventListener('click', () => show_source_modal(src));
      sources_row.appendChild(chip);
    });
    bubble.appendChild(sources_row);
  }
  
  area.appendChild(el);
}

function show_source_modal(src) {
  document.getElementById('modal-title').textContent = `${src.source} — Page ${src.page}`;
  document.getElementById('modal-text').textContent = src.text_preview;
  document.getElementById('modal-overlay').classList.add('open');
}
document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('modal-overlay').classList.remove('open');
});
document.getElementById('modal-overlay').addEventListener('click', e => {
  if (e.target === e.currentTarget) e.currentTarget.classList.remove('open');
});

function escape_html(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

load_collections();

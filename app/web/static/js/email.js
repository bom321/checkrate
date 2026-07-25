// email.js — ผู้รับอีเมลแจ้งเตือน (chip) + ช่องทางส่ง (SMTP provider) + ทดสอบส่งอีเมล
// เลย์เอาต์ตาม mockup 9b: แผงสรุปขวามือผูกกับ "ค่าที่บันทึกแล้ว" เท่านั้น
// (ไม่ใช่ค่าที่กำลังพิมพ์) จึงรีโหลดจาก /api/settings ใหม่ทุกครั้งหลังบันทึกสำเร็จ

(function () {
  const msgEl = document.getElementById('msg');
  const outputEl = document.getElementById('email-output');
  const chipsEl = document.getElementById('email-chips');
  const addEl = document.getElementById('email-add');
  const sumProviderEl = document.getElementById('sum-provider');
  const sumCountEl = document.getElementById('sum-count');
  const sumTestEl = document.getElementById('sum-test');

  const PROVIDER_LABEL = { gmail: 'Gmail', mailplus: 'MailPlus (Synology)' };
  const EMAIL_RE = /^[^@\s]+@[^@\s.]+\.[^@\s]+$/;

  // รายชื่อที่กำลังแก้อยู่ในหน้า — ยังไม่บันทึกจนกว่าจะกดปุ่ม
  let recipients = [];

  function notice(kind, text) {
    msgEl.innerHTML = `<div class="notice ${kind}">${text}</div>`;
    setTimeout(() => { msgEl.innerHTML = ''; }, 5000);
  }

  function showOutput(text) {
    outputEl.classList.remove('empty');   // มีผลจริงแล้ว — กลับไปใช้ฟอนต์ mono
    outputEl.textContent = text || '(ไม่มี output)';
    outputEl.scrollTop = outputEl.scrollHeight;
  }

  // ── chip ผู้รับ ──
  function renderChips() {
    // ลบ chip เดิมทิ้งแล้ววาดใหม่ — ปล่อย <input> ที่ท้ายกล่องไว้เสมอ
    chipsEl.querySelectorAll('.em-chip').forEach(el => el.remove());
    recipients.forEach((email) => {
      const chip = document.createElement('span');
      chip.className = 'em-chip';

      const av = document.createElement('span');
      av.className = 'em-chip-av';
      av.textContent = (email[0] || '?').toUpperCase();

      const name = document.createElement('span');
      name.textContent = email;

      const x = document.createElement('button');
      x.type = 'button';
      x.className = 'em-chip-x';
      x.textContent = '×';
      x.title = 'ลบ ' + email;
      // อ้างด้วยค่าอีเมล ไม่ใช่ index — blur ของช่องพิมพ์อาจ re-render ก่อน click จะมาถึง
      x.addEventListener('click', () => {
        recipients = recipients.filter(e => e !== email);
        renderChips();
      });

      chip.append(av, name, x);
      chipsEl.insertBefore(chip, addEl);
    });
  }

  // รับข้อความดิบ (พิมพ์เอง/วางมาทั้งก้อน) แยกด้วยคอมมา แล้วเติมเข้ารายการ
  function addFromInput() {
    const raw = addEl.value;
    if (!raw.trim()) { addEl.value = ''; return; }
    const bad = [];
    raw.split(',').map(s => s.trim()).filter(Boolean).forEach(email => {
      if (!EMAIL_RE.test(email)) { bad.push(email); return; }
      if (!recipients.includes(email)) recipients.push(email);
    });
    addEl.value = '';
    renderChips();
    if (bad.length) notice('err', 'รูปแบบอีเมลไม่ถูกต้อง: ' + bad.join(', '));
  }

  // ── provider ──
  function syncProviderUI() {
    document.querySelectorAll('.em-prov').forEach(label => {
      const input = label.querySelector('input[name="email-provider"]');
      label.classList.toggle('on', !!input && input.checked);
    });
  }

  // ── แผงสรุป (ค่าที่บันทึกแล้ว) ──
  function renderSummary(provider, savedRecipients) {
    sumProviderEl.textContent = PROVIDER_LABEL[provider] || provider;
    sumCountEl.textContent = savedRecipients.length + ' คน';
  }

  function setTestResult(ok) {
    const t = new Date().toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
    sumTestEl.className = 'em-sum-v ' + (ok ? 'ok' : 'err');
    sumTestEl.textContent = (ok ? 'สำเร็จ ' : 'ไม่สำเร็จ ') + t;
  }

  async function loadSettings() {
    const res = await fetch('/api/settings');
    const data = await res.json();
    const settings = data.settings || {};

    const raw = settings.email_to;
    recipients = Array.isArray(raw)
      ? raw.slice()
      : String(raw || '').split(',').map(s => s.trim()).filter(Boolean);
    renderChips();

    const provider = settings.email_provider || 'gmail';
    const providerInput = document.querySelector(`input[name="email-provider"][value="${provider}"]`);
    if (providerInput) providerInput.checked = true;
    syncProviderUI();

    const eff = data.recipients || [];
    document.getElementById('recipients-eff').textContent = eff.length
      ? 'ผู้รับที่ระบบใช้จริงตอนนี้: ' + eff.join(', ')
      : 'ยังไม่มีผู้รับ — ระบบจะไม่ส่งอีเมลแจ้งเตือน';
    renderSummary(provider, eff);
  }

  async function saveRecipients() {
    addFromInput();   // ที่ยังค้างในช่องพิมพ์ นับเป็นผู้รับด้วย
    const res = await fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email_to: recipients }),
    });
    const data = await res.json();
    if (data.ok) {
      notice('ok', '✓ บันทึกผู้รับอีเมลเรียบร้อย (' + (data.recipients || []).join(', ') + ')');
      await loadSettings();
    } else {
      notice('err', 'บันทึกไม่สำเร็จ: ' + (data.error || ''));
    }
  }

  async function saveProvider() {
    const providerInput = document.querySelector('input[name="email-provider"]:checked');
    const email_provider = providerInput ? providerInput.value : 'gmail';
    const res = await fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email_provider }),
    });
    const data = await res.json();
    if (data.ok) {
      notice('ok', '✓ บันทึกช่องทางส่งอีเมลเรียบร้อย');
      await loadSettings();
    } else {
      notice('err', 'บันทึกไม่สำเร็จ: ' + (data.error || ''));
    }
  }

  async function testEmail() {
    const btn = document.getElementById('test-email');
    btn.disabled = true;
    sumTestEl.className = 'em-sum-v running';
    sumTestEl.textContent = 'กำลังส่ง…';
    try {
      const res = await fetch('/api/test-email', { method: 'POST' });
      const data = await res.json();
      setTestResult(!!data.ok);
      showOutput((data.output || '') + '\n\nผู้รับ: ' + (data.recipients || []).join(', '));
    } catch (e) {
      setTestResult(false);
      showOutput('เชื่อมต่อไม่ได้: ' + e);
    }
    btn.disabled = false;
  }

  addEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addFromInput(); }
    // backspace ในช่องว่าง = ลบ chip ตัวท้าย (พฤติกรรมมาตรฐานของช่อง chip)
    else if (e.key === 'Backspace' && !addEl.value && recipients.length) {
      recipients.pop(); renderChips();
    }
  });
  addEl.addEventListener('blur', addFromInput);
  addEl.addEventListener('paste', () => setTimeout(addFromInput, 0));
  // คลิกที่ว่างในกล่อง chip = โฟกัสช่องพิมพ์
  chipsEl.addEventListener('click', (e) => { if (e.target === chipsEl) addEl.focus(); });

  document.querySelectorAll('input[name="email-provider"]')
    .forEach(el => el.addEventListener('change', syncProviderUI));

  document.getElementById('save-recipients').addEventListener('click', saveRecipients);
  document.getElementById('save-provider').addEventListener('click', saveProvider);
  document.getElementById('test-email').addEventListener('click', testEmail);

  loadSettings();
})();

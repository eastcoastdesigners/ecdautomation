require('dotenv').config();
const express = require('express');
const path = require('path');
const { DatabaseSync } = require('node:sqlite');

const app = express();
const PORT = process.env.PORT || 3000;

// Database setup
const db = new DatabaseSync('leads.db');
db.exec(`
  CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    message TEXT NOT NULL,
    source TEXT DEFAULT 'website',
    status TEXT DEFAULT 'new',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )
`);

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Basic auth middleware for admin routes
function requireAdmin(req, res, next) {
  const auth = req.headers['authorization'];
  if (!auth) return res.status(401).json({ error: 'Unauthorized' });

  const [type, credentials] = auth.split(' ');
  if (type !== 'Basic') return res.status(401).json({ error: 'Unauthorized' });

  const [user, pass] = Buffer.from(credentials, 'base64').toString().split(':');
  const adminPass = process.env.ADMIN_PASSWORD || 'admin';

  if (user !== 'admin' || pass !== adminPass) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
}

// POST /api/leads — submit lead form
app.post('/api/leads', (req, res) => {
  const { name, email, phone, message, source } = req.body;

  if (!name || !email || !phone || !message) {
    return res.status(400).json({ success: false, error: 'All fields are required.' });
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return res.status(400).json({ success: false, error: 'Invalid email address.' });
  }

  try {
    const stmt = db.prepare(
      'INSERT INTO leads (name, email, phone, message, source) VALUES (?, ?, ?, ?, ?)'
    );
    stmt.run(name.trim(), email.trim(), phone.trim(), message.trim(), source || 'website');
    res.json({ success: true });
  } catch (err) {
    console.error('Lead insert error:', err);
    res.status(500).json({ success: false, error: 'Failed to save lead.' });
  }
});

// GET /api/leads — admin: get all leads
app.get('/api/leads', requireAdmin, (req, res) => {
  const leads = db.prepare('SELECT * FROM leads ORDER BY created_at DESC').all();
  res.json(leads);
});

// PATCH /api/leads/:id — admin: update status
app.patch('/api/leads/:id', requireAdmin, (req, res) => {
  const { status } = req.body;
  const validStatuses = ['new', 'contacted', 'demo_booked', 'closed_won', 'closed_lost'];

  if (!validStatuses.includes(status)) {
    return res.status(400).json({ success: false, error: 'Invalid status.' });
  }

  try {
    db.prepare('UPDATE leads SET status = ? WHERE id = ?').run(status, req.params.id);
    res.json({ success: true });
  } catch (err) {
    console.error('Status update error:', err);
    res.status(500).json({ success: false, error: 'Failed to update status.' });
  }
});

// POST /api/chat — OpenRouter proxy
app.post('/api/chat', async (req, res) => {
  const { message, history } = req.body;

  if (!message) {
    return res.status(400).json({ error: 'Message is required.' });
  }

  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'Chatbot not configured.' });
  }

  const systemPrompt = `You are the East Coast Designers AI assistant. You help small business owners understand our services: custom websites ($2,000), websites + CRM ($3,500), or all-in-one AI systems ($5,000). The first 10 clients get Spring Special pricing — after that prices go up.

Our differentiator: clients OWN the code. No platform lock-in. No forever subscriptions. They host for $5/month on Railway.

Be warm, direct, and short. Use 3rd-grade English. Short sentences. Active voice. No fluff.

If asked something off-topic, redirect to booking a call.
If asked for a discount, say prices are fixed for the Spring Special — and that's already a discount.
If asked about timeline, say 14 days from signed agreement.
If asked who built this, say "East Coast Designers" — never give a personal name.

Respond in the same language the user wrote in (English, Spanish, or Portuguese).

End every conversation with: "Want to book a 15-minute call? Scroll down to our calendar to pick a time."`;

  const messages = [
    { role: 'system', content: systemPrompt },
    ...(history || []),
    { role: 'user', content: message }
  ];

  try {
    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://ecdautomation.com',
        'X-Title': 'ECD Automation'
      },
      body: JSON.stringify({
        model: 'openai/gpt-4o-mini',
        messages,
        max_tokens: 300
      })
    });

    const data = await response.json();
    const reply = data.choices?.[0]?.message?.content || 'Something went wrong. Please try again.';
    res.json({ reply });
  } catch (err) {
    console.error('Chat error:', err);
    res.status(500).json({ error: 'Chat service unavailable.' });
  }
});

app.listen(PORT, () => {
  console.log(`ECD Automation server running on port ${PORT}`);
});

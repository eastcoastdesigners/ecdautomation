require('dotenv').config();
const express = require('express');
const path = require('path');
const { DatabaseSync } = require('node:sqlite');
const { Resend } = require('resend');
const twilio = require('twilio');

const resend = process.env.RESEND_API_KEY ? new Resend(process.env.RESEND_API_KEY) : null;

const twilioClient = (
  process.env.TWILIO_ACCOUNT_SID &&
  process.env.TWILIO_AUTH_TOKEN &&
  process.env.TWILIO_PHONE_NUMBER
) ? twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN) : null;

function normalizePhone(input) {
  const digits = String(input || '').replace(/\D/g, '');
  if (digits.length === 10) return '+1' + digits;
  if (digits.length === 11 && digits.startsWith('1')) return '+' + digits;
  return null;
}

const app = express();
const PORT = process.env.PORT || 3000;
const SPOT_COUNT = parseInt(process.env.SPOT_COUNT_REMAINING || '10', 10);

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
    email_status TEXT DEFAULT 'pending',
    sms_status TEXT DEFAULT 'pending',
    sms_message_sid TEXT,
    sms_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )
`);

for (const stmt of [
  `ALTER TABLE leads ADD COLUMN email_status TEXT DEFAULT 'pending'`,
  `ALTER TABLE leads ADD COLUMN sms_status TEXT DEFAULT 'pending'`,
  `ALTER TABLE leads ADD COLUMN sms_message_sid TEXT`,
  `ALTER TABLE leads ADD COLUMN sms_error TEXT`,
]) {
  try { db.exec(stmt); } catch (err) {
    if (!/duplicate column name/i.test(err.message)) throw err;
  }
}

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

app.get('/api/config', (req, res) => {
  res.json({ spotCount: SPOT_COUNT });
});

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
    const insertResult = stmt.run(name.trim(), email.trim(), phone.trim(), message.trim(), source || 'website');
    const leadId = Number(insertResult.lastInsertRowid);
    const firstName = name.trim().split(' ')[0];

    function safeUpdate(sql, params) {
      try { db.prepare(sql).run(...params); }
      catch (e) { console.error('Lead status update failed:', e); }
    }

    // Owner notification — fire and forget, not tracked in DB
    if (resend) {
      const notifyEmail = process.env.NOTIFY_EMAIL || 'eastcoastdesigners@gmail.com';
      resend.emails.send({
        from: 'ECD Automation <hello@ecdautomation.com>',
        to: notifyEmail,
        subject: `New Lead: ${name.trim()}`,
        html: `
          <h2>New lead from ecdautomation.com</h2>
          <p><strong>Name:</strong> ${name.trim()}</p>
          <p><strong>Email:</strong> ${email.trim()}</p>
          <p><strong>Phone:</strong> ${phone.trim()}</p>
          <p><strong>Message:</strong><br>${message.trim()}</p>
          <p><a href="https://ecdautomation.com/admin.html">View in CRM →</a></p>
        `
      }).then(({ error }) => {
        if (error) console.error('Owner notify error:', error);
      });
    }

    // Lead follow-up email — tracked via email_status
    if (!resend) {
      safeUpdate(`UPDATE leads SET email_status = 'skipped' WHERE id = ?`, [leadId]);
    } else {
      resend.emails.send({
        from: 'Cristina at East Coast Designers <hello@ecdautomation.com>',
        to: email.trim(),
        subject: `Got your info, ${firstName} — here's what's next`,
        html: `
          <p>Hey ${firstName},</p>
          <p>Got your message. I'll reach out within 24 hours to set up your free 30-minute consultation.</p>
          <p>In the meantime, if you want to skip the wait — grab a time directly on my calendar:</p>
          <p><a href="https://cal.com/east-coast-designers/30-min-ai-automation-consultation">Book your 30-minute call →</a></p>
          <p>Here's what we'll cover:</p>
          <ul>
            <li>What you actually need (website, CRM, AI, or all three)</li>
            <li>What it costs and what you'll own</li>
            <li>How fast we can get it done</li>
          </ul>
          <p>No sales pitch. No pressure. Just answers.</p>
          <p>— Cristina<br>East Coast Designers | AI Automation<br>ecdautomation.com</p>
        `
      }).then(({ error }) => {
        if (error) {
          console.error(`Lead follow-up error (lead ${leadId}):`, error);
          safeUpdate(`UPDATE leads SET email_status = 'failed' WHERE id = ?`, [leadId]);
        } else {
          safeUpdate(`UPDATE leads SET email_status = 'sent' WHERE id = ?`, [leadId]);
        }
      });
    }

    // SMS — tracked via sms_status / sms_message_sid / sms_error
    const normalizedPhone = normalizePhone(phone);
    if (!twilioClient) {
      safeUpdate(`UPDATE leads SET sms_status = 'skipped' WHERE id = ?`, [leadId]);
    } else if (!normalizedPhone) {
      console.warn(`SMS skipped — invalid phone format for lead ${leadId}`);
      safeUpdate(
        `UPDATE leads SET sms_status = 'skipped', sms_error = ? WHERE id = ?`,
        ['invalid phone format', leadId]
      );
    } else {
      twilioClient.messages.create({
        body: `Hey ${firstName} — thanks for reaching out to East Coast Designers. We got your message and someone will be in touch within 24 hours. Reply STOP to opt out. — Cristina`,
        from: process.env.TWILIO_PHONE_NUMBER,
        to: normalizedPhone
      }).then(msg => {
        safeUpdate(
          `UPDATE leads SET sms_status = 'sent', sms_message_sid = ? WHERE id = ?`,
          [msg.sid, leadId]
        );
      }).catch(err => {
        console.error(`SMS send error (lead ${leadId}):`, err);
        safeUpdate(
          `UPDATE leads SET sms_status = 'failed', sms_error = ? WHERE id = ?`,
          [String(err && err.message ? err.message : err), leadId]
        );
      });
    }

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

  const systemPrompt = `You are the East Coast Designers AI assistant. You help small business owners understand our services: custom websites starting at $5,000, websites + CRM at $7,500, or all-in-one AI systems at $10,000. We're currently offering Spring Special pricing — once the ${SPOT_COUNT} spots fill, prices go up to $7,500 / $10,000 / $15,000.

After launch, we offer three Care Package tiers:
- Essential Care at $300/month — hosting, security, minor edits
- Active Care at $500/month — everything plus 2 hours of changes monthly + priority support
- Full Care at $750/month — everything plus 5 hours monthly, analytics reports, quarterly strategy calls

If a customer indicates they're ready to purchase or asks how to pay, share the appropriate payment link:

For one-time package deposits (50% to start, 50% on delivery):
- Website Only ($5,000 total, $2,500 deposit): https://buy.stripe.com/3cI5kC41l0HJbEgc2UeEo00
- Website + CRM ($7,500 total, $3,750 deposit): https://buy.stripe.com/cNi9AS8hB0HJ23GgjaeEo01
- All-in-One ($10,000 total, $5,000 deposit): https://buy.stripe.com/bJe14m0P9cqr6jWgjaeEo02

For Care Package subscriptions (after their site launches):
- Essential Care ($300/month): https://buy.stripe.com/eVqfZg1Td6237o01ogeEo03
- Active Care ($500/month): https://buy.stripe.com/8x2bJ07dxfCD7o0d6YeEo04
- Full Care ($750/month): https://buy.stripe.com/bJeaEW8hB7674b0gjaeEo05

Important: NEVER recommend a Care Package before the customer has discussed which website package they want. Care Packages are for after their site is built.

If a customer seems unsure or wants to talk first, encourage them to book a 30-minute consultation via the calendar on the site (do not send a payment link to someone who hasn't decided).

Our differentiator: clients OWN the code. No platform lock-in. No forever subscriptions. They host on a secure managed server for $5/month. We're a small studio that takes on a few clients at a time — we actually care about results, not volume.

Be warm, direct, and personal. Use 3rd-grade English. Short sentences. Active voice. No fluff. Sound like a real person who cares, not a sales bot.

If asked something off-topic, redirect to booking a consultation.
If asked for a discount, say the Spring Special pricing is already the lowest available — once the ${SPOT_COUNT} spots fill, prices go back up to standard rates. No further reductions.
If asked about timeline, say 14 days from signed agreement.
If asked who built this, say "East Coast Designers — a small studio that builds custom websites and AI automation. We're selective about who we work with." Never give a personal name.
If asked what hosting we use, say "a secure managed server" — do not name specific vendors.
If asked about ongoing support, walk them through the three Care tiers and recommend Active Care as the most popular choice.

Respond in the same language the user wrote in (English, Spanish, or Portuguese).

End every conversation with: "Want to book a 30-min consultation? Here's the link: [scroll to calendar]"`;

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

// Builds FT_Outreach_Assist.pptx - run: node build.js
const path = require("path");
const pptxgen = require("pptxgenjs");
const sharp = require("sharp");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const fa = require("react-icons/fa");
const { applyTheme } = require(
  "/Users/muppuri/.claude/skills/synced/ea9e560d-f2f4-4e22-b6cc-5de7d5f98a44_8e872574-e239-481b-86bd-fb0b0ddee1b1/pptx/scripts/apply_theme.js");

const OUT = path.join(__dirname, "FT_Outreach_Assist.pptx");
const SHOTS = path.join(__dirname, "shots");
const ARCH_SVG = path.join(__dirname, "..", "outreach-poc", "docs", "architecture.svg");

const THEME = {
  name: "Outreach Assist",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "14213D", lt1: "FFFFFF", dk2: "3A4A66", lt2: "EEF1F6",
    accent1: "C8963E", // brass - motif (icon circles, highlights)
    accent2: "2E7D6B", // green - used / allowed
    accent3: "6B4FA0", // violet - AI agents
    accent4: "B3261E", // red - excluded / blocked
    accent5: "3D6FB6", // steel - rules
    accent6: "8A94A6",
    hlink: "3D6FB6", folHlink: "6B4FA0",
  },
};
const HEX = THEME.colors;
const W = 13.333, H = 7.5, M = 0.6;

// ------------------------------------------------------------------ helpers
async function iconData(Comp, color = "FFFFFF") {
  const svg = renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: 256 }));
  const buf = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

async function raw(file) {
  const { data, info } = await sharp(file).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const px = (x, y) => { const i = (y * info.width + x) * 3; return [data[i], data[i + 1], data[i + 2]]; };
  const lum = (x, y) => { const [r, g, b] = px(x, y); return (r + g + b) / 3; };
  return { info, px, lum };
}

// Locate the white dialog over the grey overlay, the summary column, and the admin divider.
async function dialogGeometry(file) {
  const { info, lum, px } = await raw(file);
  const { width: w, height: h } = info;
  const probeX = Math.round(w * 0.06);
  let top = 0; for (let y = 0; y < h; y++) if (lum(probeX, y) > 248) { top = y; break; }
  let bottom = h - 1; for (let y = h - 1; y > top; y--) if (lum(probeX, y) > 248) { bottom = y; break; }
  const midY = top + 60;
  let left = 0; for (let x = 0; x < w; x++) if (lum(x, midY) > 248) { left = x; break; }
  let right = w - 1; for (let x = w - 1; x > left; x--) if (lum(x, midY) > 248) { right = x; break; }
  // summary column: its tinted background (~242) starts right of the compose column
  const sy = top + Math.round((bottom - top) * 0.5);
  let split = right - 740;
  for (let x = left + Math.round((right - left) * 0.55); x < right; x++) {
    const l = lum(x, sy);
    if (l >= 236 && l <= 246 && lum(x + 6, sy) >= 236 && lum(x + 6, sy) <= 246) { split = x - 4; break; }
  }
  // admin divider: last thin light-grey line (~225) crossing the whole compose column
  const xs = [left + 120, Math.round((left + split) / 2), split - 120];
  let divider = bottom;
  for (let y = bottom - 40; y > top + 300; y--) {
    if (xs.every((x) => { const l = lum(x, y); return l > 205 && l < 236; })) { divider = y; break; }
  }
  return { w, h, top, bottom, left, right, split, divider };
}

async function crop(file, box, maxW = 2000) {
  const buf = await sharp(file).extract(box).resize({ width: Math.min(maxW, box.width) }).png().toBuffer();
  const meta = await sharp(buf).metadata();
  return { data: "image/png;base64," + buf.toString("base64"), ar: meta.width / meta.height };
}

// fit an image of aspect ar inside (x,y,w,h); align top-left by default
function fit(ar, x, y, w, h, align = "center") {
  let iw = w, ih = w / ar;
  if (ih > h) { ih = h; iw = h * ar; }
  const ix = align === "left" ? x : x + (w - iw) / 2;
  return { x: ix, y, w: iw, h: ih };
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = "AI-assisted advisor outreach in SalesAssist";
  pres.subject = "Case study proof of concept";
  pres.author = "Case study candidate";
  pres.company = "Case study";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  // ---------------------------------------------------------------- layouts
  pres.defineSlideMaster({
    title: "Title Dark",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 2.0, w: 6.4, h: 2.1, fontSize: 40, bold: true,
        color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: M, y: 4.3, w: 6.2, h: 1.5, fontSize: 18,
        color: C.accent1, valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "Content",
    background: { color: C.background1 },
    margin: [0.5, M, 0.6, M],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 0.35, w: W - 2 * M, h: 0.95, fontSize: 34,
        bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { text: { text: "SalesAssist · AI-assisted advisor outreach · Proof of concept",
        options: { x: M, y: H - 0.45, w: 7, h: 0.3, fontSize: 10, color: C.accent6, margin: 0 } } },
    ],
    slideNumber: { x: W - M - 0.6, y: H - 0.45, w: 0.6, h: 0.3, fontSize: 10, color: C.accent6, align: "right" },
  });
  pres.defineSlideMaster({
    title: "Closing Dark",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 0.5, w: W - 2 * M, h: 1.0, fontSize: 36,
        bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
    ],
    slideNumber: { x: W - M - 0.6, y: H - 0.45, w: 0.6, h: 0.3, fontSize: 10, color: C.accent6, align: "right" },
  });

  // ---------------------------------------------------------------- assets
  const I = {};
  const iconSet = {
    mail: fa.FaEnvelopeOpenText, crm: fa.FaComments, sales: fa.FaChartLine, holdings: fa.FaWallet,
    fund: fa.FaStar, docs: fa.FaFileAlt, x: fa.FaTimes, check: fa.FaCheck, eye: fa.FaEye, tasks: fa.FaTasks,
    send: fa.FaPaperPlane, click: fa.FaMousePointer, clock: fa.FaClock, link: fa.FaLink, hands: fa.FaHandshake,
    user: fa.FaUserCheck, lock: fa.FaLock, search: fa.FaSearch, pen: fa.FaPenNib, clip: fa.FaClipboardList,
    shield: fa.FaShieldAlt, route: fa.FaRoute, bolt: fa.FaBolt, cal: fa.FaCalendarCheck, flag: fa.FaFlagCheckered,
    layers: fa.FaLayerGroup, db: fa.FaDatabase, robot: fa.FaRobot, balance: fa.FaBalanceScale, gavel: fa.FaListOl,
  };
  for (const [k, Comp] of Object.entries(iconSet)) I[k] = await iconData(Comp);

  const shot = (n) => path.join(SHOTS, n + ".png");
  const G = {};
  for (const n of ["riley", "jordan", "casey"]) G[n] = await dialogGeometry(shot(n));
  const dialog = async (n) => { const g = G[n]; return crop(shot(n), { left: g.left, top: g.top, width: g.right - g.left, height: g.bottom - g.top }); };
  const compose = async (n, toDivider = true) => { const g = G[n];
    return crop(shot(n), { left: g.left, top: g.top, width: g.split - g.left, height: (toDivider ? g.divider : g.bottom) - g.top }); };
  const admin = async (n) => { const g = G[n];
    return crop(shot(n), { left: g.left, top: g.divider, width: g.split - g.left, height: g.bottom - g.divider }); };
  const summary = async (n) => { const g = G[n];
    return crop(shot(n), { left: g.split, top: g.top + 120, width: g.right - g.split, height: g.bottom - g.top - 120 }, 900); };

  const archBuf = await sharp(ARCH_SVG, { density: 220 }).png().toBuffer();
  const archMeta = await sharp(archBuf).metadata();
  const ARCH = { data: "image/png;base64," + archBuf.toString("base64"), ar: archMeta.width / archMeta.height };

  // ---------------------------------------------------------------- drawing helpers
  const shadow = () => ({ type: "outer", color: "1B2A44", opacity: 0.18, blur: 8, offset: 2, angle: 90 });
  function card(s, x, y, w, h, name, fill = C.background2) {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill },
      line: { color: fill, width: 0 }, objectName: name });
  }
  function iconCircle(s, key, x, y, d, fill = C.accent1, name = "icon") {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill, width: 0 }, objectName: name + " circle" });
    const p = d * 0.27;
    s.addImage({ data: I[key], x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p, objectName: name + " icon", altText: key });
  }
  function txt(s, text, o) { s.addText(text, { isTextBox: true, margin: 0, valign: "top", color: C.text1, fontSize: 15, ...o }); }
  function framedImage(s, img, box, name) {
    const r = fit(img.ar, box.x, box.y, box.w, box.h, box.align || "center");
    s.addShape(pres.shapes.RECTANGLE, { x: r.x, y: r.y, w: r.w, h: r.h, fill: { color: C.background1 },
      line: { color: "D5DBE5", width: 0.75 }, shadow: shadow(), objectName: name + " frame" });
    s.addImage({ data: img.data, x: r.x, y: r.y, w: r.w, h: r.h, objectName: name, altText: name });
    return r;
  }
  const content = (section, title) => {
    const s = pres.addSlide({ masterName: "Content", sectionTitle: section });
    s.addText(title, { placeholder: "title" });
    return s;
  };

  // ================================================================= 1. Title
  pres.addSection({ title: "Introduction" });
  {
    const s = pres.addSlide({ masterName: "Title Dark", sectionTitle: "Introduction" });
    s.addText("From one click to a ready-to-send advisor email", { placeholder: "title" });
    s.addText("AI-assisted outreach in SalesAssist\nCase study and working proof of concept · November 2026", { placeholder: "body" });
    iconCircle(s, "mail", M, 1.0, 0.75, C.accent1, "title mark");
    const img = await dialog("riley");
    framedImage(s, img, { x: 7.35, y: 0.75, w: 5.4, h: 6.0 }, "Outreach dialog screenshot");
    s.addNotes("This is a proposal and working prototype for a new SalesAssist capability: when a salesperson clicks the email icon next to a Financial Advisor, a useful, accurate email is already drafted, with the reasons behind it and the follow-up tasks ready to go. The screenshot is the real prototype, running on the case-study data.");
  }

  // ================================================================= 2. Problem
  pres.addSection({ title: "The problem" });
  {
    const s = content("The problem", "Six places to check before one email");
    const items = [
      ["crm", "CRM notes", "Meetings, calls, promises made"],
      ["sales", "Recent sales", "What the advisor just bought"],
      ["holdings", "Holdings", "A dated view of their book"],
      ["fund", "Fund data", "Ratings and returns, with dates"],
      ["docs", "Product documents", "Which files may be shared"],
      ["user", "Advisor profile", "Firm, region, preferences"],
    ];
    const cw = 3.55, ch = 1.45, gx = 0.3, gy = 0.3, x0 = M, y0 = 1.65;
    items.forEach(([ic, t, d], i) => {
      const x = x0 + (i % 2) * (cw + gx), y = y0 + Math.floor(i / 2) * (ch + gy);
      card(s, x, y, cw, ch, `source ${t}`);
      iconCircle(s, ic, x + 0.25, y + 0.35, 0.75, C.text2, `source ${t}`);
      txt(s, t, { x: x + 1.2, y: y + 0.33, w: cw - 1.35, h: 0.4, fontSize: 17, bold: true });
      txt(s, d, { x: x + 1.2, y: y + 0.75, w: cw - 1.35, h: 0.5, fontSize: 14, color: C.text2 });
    });
    const rx = 8.45;
    txt(s, "6", { x: rx, y: 1.55, w: 4.2, h: 1.6, fontSize: 96, bold: true, color: C.accent1, fontFace: undefined });
    txt(s, "separate sources a salesperson reviews by hand before writing to one advisor", { x: rx, y: 3.15, w: 4.2, h: 0.9, fontSize: 18, bold: true });
    txt(s, "The useful detail is scattered, and some of it looks relevant but would mislead the advisor if it went into an email.",
      { x: rx, y: 4.25, w: 4.2, h: 1.4, fontSize: 15, color: C.text2 });
    s.addNotes("Before contacting an advisor, the salesperson pieces together CRM history, recent business, holdings, fund information and approved material. That takes time, so outreach is either slow or generic. The case-study data shows a second problem: some details that look useful must not be used.");
  }
  {
    const s = content("The problem", "The hard part is knowing what not to say");
    const traps = [
      ["The newest factsheet is the wrong one", "Riley asked about Class I. The latest Riverstone factsheet is for Class A."],
      ["The only deck is internal", "Casey wants an Oakbridge factsheet. The only Oakbridge document is internal-only."],
      ["An invite is not interest", "Jordan was sent a webinar invite and never replied. That says nothing about interest."],
      ["A smaller holding is not a sale", "Riley's Oakbridge holding fell by $5,000, but no sale was recorded. It may just be the market."],
    ];
    const cw = 5.9, ch = 1.85, gx = 0.33, gy = 0.3;
    traps.forEach(([t, d], i) => {
      const x = M + (i % 2) * (cw + gx), y = 1.6 + Math.floor(i / 2) * (ch + gy);
      card(s, x, y, cw, ch, `trap ${i + 1}`);
      iconCircle(s, "x", x + 0.3, y + 0.35, 0.7, C.accent4, `trap ${i + 1}`);
      txt(s, t, { x: x + 1.2, y: y + 0.3, w: cw - 1.45, h: 0.45, fontSize: 18, bold: true });
      txt(s, d, { x: x + 1.2, y: y + 0.8, w: cw - 1.45, h: 0.9, fontSize: 15, color: C.text2 });
    });
    txt(s, "Four traps in data for just three advisors. A writer without these rules could easily repeat them.",
      { x: M, y: 5.95, w: W - 2 * M, h: 0.5, fontSize: 16, italic: true, color: C.accent3 });
    s.addNotes("All four examples come straight from the case-study files. Each one would make an email wrong or non-compliant: the wrong share class, an internal document, implying interest that was never shown, or implying a sale. The prototype handles every one of them, and each is covered by an automated test.");
  }

  // ================================================================= 3. Solution
  pres.addSection({ title: "The solution" });
  {
    const s = content("The solution", "One click: draft, reasons and next steps");
    const steps = [
      ["click", "Click ✉", "Next to any advisor in your region"],
      ["mail", "Draft appears", "Subject, body and links to approved files"],
      ["eye", "See why", "Facts used, and what was left out and why"],
      ["tasks", "Pick follow-ups", "CRM log, meeting holds, reminders"],
      ["send", "You send", "Edit freely; nothing goes out without you"],
    ];
    const n = steps.length, gap = 0.28, cw = (W - 2 * M - gap * (n - 1)) / n, y = 1.75;
    steps.forEach(([ic, t, d], i) => {
      const x = M + i * (cw + gap);
      card(s, x, y, cw, 2.75, `step ${i + 1}`);
      iconCircle(s, ic, x + (cw - 0.95) / 2, y + 0.35, 0.95, i === n - 1 ? C.accent2 : C.accent1, `step ${i + 1}`);
      txt(s, t, { x: x + 0.15, y: y + 1.45, w: cw - 0.3, h: 0.45, fontSize: 18, bold: true, align: "center" });
      txt(s, d, { x: x + 0.2, y: y + 1.95, w: cw - 0.4, h: 0.7, fontSize: 14, color: C.text2, align: "center" });
    });
    card(s, M, 4.85, W - 2 * M, 1.25, "instant note", "F6F1E7");
    iconCircle(s, "bolt", M + 0.3, 5.1, 0.75, C.accent1, "instant");
    txt(s, "Ready the moment you click", { x: M + 1.3, y: 5.05, w: 10.5, h: 0.4, fontSize: 18, bold: true });
    txt(s, "Drafts are prepared in advance, overnight and whenever an advisor's data changes, so opening the email is instant rather than a wait.",
      { x: M + 1.3, y: 5.45, w: 10.6, h: 0.55, fontSize: 15, color: C.text2 });
    s.addNotes("The experience follows the brief: the click on the email icon opens everything at once. The user stays in control. They can switch between suggested reasons to write, untick facts, change the tone and edit the text. SalesAssist never sends the email itself.");
  }
  {
    const s = content("The solution", "Riley: a promise kept, with the right file");
    const img = await compose("riley");
    const rr = framedImage(s, img, { x: M, y: 1.5, w: 6.9, h: 5.35, align: "left" }, "Riley email draft screenshot");
    const px0 = rr.x + rr.w + 0.6, pw = W - M - px0 - 0.85;
    const pts = [
      ["check", C.accent2, "Answers the request", "Sends the Class I factsheet and commentary Riley asked for, as promised on the 6 November call."],
      ["x", C.accent4, "Skips the wrong file", "The newer Class A factsheet is left out, with the reason shown to the salesperson."],
      ["pen", C.accent1, "Fits the relationship", "Short and to the point, because Riley's notes say they prefer concise emails."],
      ["shield", C.accent3, "Every claim checked", "Each link and figure is matched against the source data before it is shown."],
    ];
    pts.forEach(([ic, col, t, d], i) => {
      const y = 1.55 + i * 1.3, x = px0;
      iconCircle(s, ic, x, y, 0.65, col, `riley point ${i + 1}`);
      txt(s, t, { x: x + 0.85, y: y - 0.02, w: pw, h: 0.4, fontSize: 17, bold: true });
      txt(s, d, { x: x + 0.85, y: y + 0.38, w: pw, h: 0.85, fontSize: 15, color: C.text2 });
    });
    s.addNotes("Real output from the prototype. Riley asked for information on Riverstone Income Fund Class I and the salesperson promised to send approved material. The draft links exactly the two approved Class I documents. A recent $25,000 purchase is available as an extra fact. Fund ratings are off by default and, if added, come with their date and disclosure.");
  }
  {
    const s = content("The solution", "Jordan and Casey: timely and honest");
    const jw = (W - 2 * M - 0.4) / 2;
    const j = await compose("jordan"), c = await compose("casey");
    const rj = framedImage(s, j, { x: M, y: 1.5, w: jw, h: 3.75 }, "Jordan email draft screenshot");
    const rc = framedImage(s, c, { x: M + jw + 0.4, y: 1.5, w: jw, h: 3.75 }, "Casey email draft screenshot");
    txt(s, "Jordan · moved firms", { x: M, y: 5.45, w: jw, h: 0.4, fontSize: 17, bold: true });
    txt(s, "Congratulates Jordan on joining Maple Advisory and offers three times to reconnect later this month, as Jordan asked. It flags that the email address may still belong to the old firm.",
      { x: M, y: 5.85, w: jw, h: 1.0, fontSize: 14, color: C.text2 });
    txt(s, "Casey · material not ready", { x: M + jw + 0.4, y: 5.45, w: jw, h: 0.4, fontSize: 17, bold: true });
    txt(s, "No approved Oakbridge factsheet exists yet, so the email says it will follow instead of attaching the internal deck. A request to marketing is suggested.",
      { x: M + jw + 0.4, y: 5.85, w: jw, h: 1.0, fontSize: 14, color: C.text2 });
    s.addNotes("Two more real outputs. For Jordan, the reason to write is the firm move and the request to reconnect, not the unanswered webinar invite. For Casey, the honest answer is that the factsheet is not ready. The system raises that gap rather than sending the internal presentation.");
  }
  {
    const s = content("The solution", "Follow-ups happen in the same click");
    const img = await admin("casey");
    framedImage(s, img, { x: M, y: 1.55, w: 7.2, h: 3.3, align: "left" }, "Administrative actions screenshot");
    const acts = [
      ["clip", "Log the email in CRM", "and close the promised follow-up"],
      ["cal", "Hold meeting times", "and draft the invite"],
      ["docs", "Request material", "from marketing when it is missing"],
      ["clock", "Set reminders", "so nothing slips"],
      ["user", "Check contact details", "after a firm move"],
    ];
    acts.forEach(([ic, t, d], i) => {
      const y = 1.6 + i * 0.68, x = 8.3;
      iconCircle(s, ic, x, y, 0.5, C.text2, `action ${i + 1}`);
      txt(s, [{ text: t, options: { bold: true } }, { text: " " + d }], { x: x + 0.7, y: y + 0.06, w: 4.0, h: 0.45, fontSize: 15 });
    });
    card(s, M, 5.2, W - 2 * M, 1.05, "confirm note", "F6F1E7");
    iconCircle(s, "lock", M + 0.3, 5.35, 0.7, C.accent1, "confirm");
    txt(s, [{ text: "Nothing runs until you confirm. ", options: { bold: true } },
      { text: "Select one or several actions, review them in a confirmation step, then run. The AI recommends; the salesperson decides." }],
      { x: M + 1.25, y: 5.42, w: 10.7, h: 0.7, fontSize: 15 });
    s.addNotes("This is the administrative-support capability from the brief. Requests in the advisor's history become suggested tasks next to the draft. The admin agent pre-selects the ones that matter and says why, as in Casey's case. Nothing runs without an explicit confirmation, and the server refuses unconfirmed requests.");
  }
  {
    const s = content("The solution", "What sales teams get");
    const vals = [
      ["clock", "Minutes, not a morning", "Context from six sources arrives assembled. Preparation becomes reviewing a draft rather than searching."],
      ["link", "The right material, every time", "Only approved, external documents for the exact share class are linked."],
      ["hands", "Promises don't slip", "Open requests and commitments in the CRM come first, with follow-ups ready to log."],
      ["user", "You stay in control", "Every fact can be switched off, the text edited, and nothing is sent or run without you."],
    ];
    const cw = 5.9, ch = 2.05, gx = 0.33, gy = 0.3;
    vals.forEach(([ic, t, d], i) => {
      const x = M + (i % 2) * (cw + gx), y = 1.6 + Math.floor(i / 2) * (ch + gy);
      card(s, x, y, cw, ch, `value ${i + 1}`);
      iconCircle(s, ic, x + 0.35, y + 0.4, 0.85, C.accent1, `value ${i + 1}`);
      txt(s, t, { x: x + 1.5, y: y + 0.38, w: cw - 1.8, h: 0.45, fontSize: 19, bold: true });
      txt(s, d, { x: x + 1.5, y: y + 0.88, w: cw - 1.8, h: 1.0, fontSize: 15, color: C.text2 });
    });
    s.addNotes("The value for a salesperson: less time preparing, more relevant emails, fewer dropped commitments, and full control. The time saving is not measured yet; the pilot on the closing slide is designed to measure it.");
  }

  // ================================================================= 4. How it works
  pres.addSection({ title: "How it works" });
  {
    const s = content("How it works", "Rules decide what's true; AI says it well");
    const steps = [
      ["lock", "Check access", "rules"], ["db", "Gather data", "rules"], ["search", "Spot reasons", "rules"],
      ["robot", "Choose intent", "ai"], ["balance", "Approve facts", "rules"], ["pen", "Write & review", "ai"],
      ["shield", "Check claims", "rules"],
    ];
    const n = steps.length, gap = 0.18, cw = (W - 2 * M - gap * (n - 1)) / n, y = 1.75;
    steps.forEach(([ic, t, kind], i) => {
      const x = M + i * (cw + gap);
      const col = kind === "ai" ? C.accent3 : C.accent5;
      card(s, x, y, cw, 1.95, `pipeline ${i + 1}`);
      iconCircle(s, ic, x + (cw - 0.75) / 2, y + 0.3, 0.75, col, `pipeline ${i + 1}`);
      txt(s, `${i + 1}. ${t}`, { x: x + 0.08, y: y + 1.2, w: cw - 0.16, h: 0.6, fontSize: 15, bold: true, align: "center" });
    });
    // legend
    s.addShape(pres.shapes.OVAL, { x: M, y: 3.98, w: 0.22, h: 0.22, fill: { color: C.accent5 }, line: { color: C.accent5, width: 0 }, objectName: "legend rules" });
    txt(s, "Rules: fixed, tested, auditable", { x: M + 0.32, y: 3.95, w: 3.6, h: 0.3, fontSize: 14, color: C.text2 });
    s.addShape(pres.shapes.OVAL, { x: M + 4.0, y: 3.98, w: 0.22, h: 0.22, fill: { color: C.accent3 }, line: { color: C.accent3, width: 0 }, objectName: "legend ai" });
    txt(s, "AI: judgement and wording", { x: M + 4.32, y: 3.95, w: 3.6, h: 0.3, fontSize: 14, color: C.text2 });
    const cols = [
      ["What the rules guarantee", "Region access, approved material only, the right share class, no implied holdings or sales, disclosures with any performance figure."],
      ["What the AI adds", "Weighs several signals to pick the best reason to write, and writes a natural, relationship-aware email from approved facts."],
      ["If the AI is unavailable", "A backup model takes over, then a template. The email panel always opens, and the same checks still apply."],
    ];
    const ccw = (W - 2 * M - 0.6) / 3;
    cols.forEach(([t, d], i) => {
      const x = M + i * (ccw + 0.3);
      txt(s, t, { x, y: 4.6, w: ccw, h: 0.4, fontSize: 17, bold: true });
      txt(s, d, { x, y: 5.05, w: ccw, h: 1.3, fontSize: 14, color: C.text2 });
    });
    s.addNotes("The design principle: anything that is a policy, such as access, share class, audience and approval, is enforced by code and tested. The AI is used where judgement and language matter. That keeps every statement in the email traceable to a source record.");
  }
  {
    const s = content("How it works", "A small AI team, one job each");
    const agents = [
      ["search", "Intent Analyst", "Reads CRM and sales through SalesAssist's own tools and decides why to write now, citing the records it used."],
      ["pen", "Writer", "Drafts the email using only the approved facts. It has no access to anything else."],
      ["tasks", "Admin Operations", "Recommends the follow-up tasks this email creates, and says why for each one."],
      ["shield", "Compliance Reviewer", "Reviews the Writer's draft against the facts and the rules before you see it."],
    ];
    const cw = (W - 2 * M - 0.9) / 4;
    agents.forEach(([ic, t, d], i) => {
      const x = M + i * (cw + 0.3), y = 1.6;
      card(s, x, y, cw, 3.4, `agent ${t}`);
      iconCircle(s, ic, x + 0.3, y + 0.35, 0.85, C.accent3, `agent ${t}`);
      txt(s, t, { x: x + 0.3, y: y + 1.35, w: cw - 0.6, h: 0.75, fontSize: 18, bold: true, valign: "top" });
      txt(s, d, { x: x + 0.3, y: y + 2.05, w: cw - 0.6, h: 1.3, fontSize: 14, color: C.text2 });
    });
    card(s, M, 5.3, W - 2 * M, 1.0, "guardrail band", "EFEAF7");
    txt(s, [{ text: "Built on SalesAssist's existing capabilities. ", options: { bold: true } },
      { text: "Agents reach data only through SalesAssist tools that enforce region access and approval rules themselves. Every agent answer is checked by code before it reaches you." }],
      { x: M + 0.35, y: 5.45, w: W - 2 * M - 0.7, h: 0.75, fontSize: 15 });
    s.addNotes("Splitting the work across focused agents keeps each one simple and reviewable, and lets the writing and admin planning run in parallel. Technically: CrewAI orchestrates the agents; SalesAssist capabilities are exposed as MCP servers; the model is Claude, with Gemini supported as an alternative.");
  }
  {
    const s = content("How it works", "Safeguards built in, not bolted on");
    const g = [
      ["lock", "Region lock", "Advisors outside your region are blocked before any data is read or any AI is used."],
      ["docs", "Approved material only", "External, approved and the exact share class discussed. Internal decks never leave."],
      ["gavel", "Every claim traced", "Amounts, percentages, links and fund names must match a source record, or the draft is replaced."],
      ["fund", "Performance with care", "Ratings and returns are off by default, always dated, and always carry the disclosure."],
      ["route", "Always opens", "If the AI is slow or unavailable, a backup model or a template takes over, with the same checks."],
      ["user", "Human in charge", "Nothing is sent by the system. Admin tasks run only after an explicit confirmation."],
    ];
    const cw = (W - 2 * M - 0.6) / 3, ch = 2.0;
    g.forEach(([ic, t, d], i) => {
      const x = M + (i % 3) * (cw + 0.3), y = 1.6 + Math.floor(i / 3) * (ch + 0.3);
      card(s, x, y, cw, ch, `safeguard ${t}`);
      iconCircle(s, ic, x + 0.3, y + 0.32, 0.7, C.text2, `safeguard ${t}`);
      txt(s, t, { x: x + 1.2, y: y + 0.38, w: cw - 1.4, h: 0.45, fontSize: 17, bold: true });
      txt(s, d, { x: x + 0.3, y: y + 1.12, w: cw - 0.6, h: 0.8, fontSize: 14, color: C.text2 });
    });
    s.addNotes("These safeguards are implemented in the prototype and covered by 27 automated tests that encode each data trap from the case study.");
  }

  // ================================================================= 5. Next steps
  pres.addSection({ title: "Next steps" });
  {
    const s = content("Next steps", "Built, assumed and next");
    const cols = [
      [C.accent2, "check", "Built in the prototype", [
        "Click-to-draft flow in a SalesAssist-style screen",
        "Three outreach needs: requested info, firm move, thank-you for a trade",
        "Four AI agents over SalesAssist tools",
        "Evidence rules, claim checks and fallbacks",
        "Admin actions with confirmation",
      ]],
      [C.accent1, "balance", "Assumed for now", [
        "Sample data stands in for CRM, sales and documents",
        "A significant trade is $10,000 or more in 14 days",
        "Requests stay open until a later record closes them",
        "Meeting times are suggested, not checked against a calendar",
      ]],
      [C.accent5, "flag", "Next", [
        "Connect real CRM, sales and document systems",
        "Add request status and advisor contact preferences",
        "Meeting follow-up and service check-in emails",
        "Learn from how salespeople edit the drafts",
      ]],
    ];
    const cw = (W - 2 * M - 0.6) / 3;
    cols.forEach(([col, ic, t, items], i) => {
      const x = M + i * (cw + 0.3), y = 1.6;
      card(s, x, y, cw, 4.7, `column ${t}`);
      iconCircle(s, ic, x + 0.3, y + 0.3, 0.6, col, `column ${t}`);
      txt(s, t, { x: x + 1.05, y: y + 0.38, w: cw - 1.3, h: 0.45, fontSize: 18, bold: true });
      s.addText(items.map((it, k) => ({ text: it, options: { bullet: true, breakLine: k < items.length - 1 } })),
        { isTextBox: true, x: x + 0.3, y: y + 1.15, w: cw - 0.55, h: 3.4, fontSize: 14, color: C.text1, valign: "top",
          paraSpaceAfter: 8, margin: 0 });
    });
    s.addNotes("Being explicit about scope: the prototype is a foundation, not a production system. Assumptions are documented in the project's ASSUMPTIONS_AND_LIMITATIONS file, and the thresholds are configurable.");
  }
  {
    const s = pres.addSlide({ masterName: "Closing Dark", sectionTitle: "Next steps" });
    s.addText("Proposed next step: a four-week pilot", { placeholder: "title" });
    const blocks = [
      ["users", "Who", "One region, five to ten salespeople, using their real advisor list."],
      ["chart", "What we measure", "Time from click to send · drafts sent with light edits · follow-ups completed on time · advisor replies."],
      ["need", "What we need", "Read access to CRM, sales and the document library, and a compliance review of the rules."],
    ];
    const cw = (W - 2 * M - 0.6) / 3;
    const icons = { users: "user", chart: "flag", need: "clip" };
    blocks.forEach(([k, t, d], i) => {
      const x = M + i * (cw + 0.3), y = 1.9;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: 3.3, rectRadius: 0.08, fill: { color: "22325A" },
        line: { color: "22325A", width: 0 }, objectName: `pilot ${t}` });
      iconCircle(s, icons[k], x + 0.35, y + 0.35, 0.85, C.accent1, `pilot ${t}`);
      txt(s, t, { x: x + 0.35, y: y + 1.45, w: cw - 0.7, h: 0.45, fontSize: 20, bold: true, color: C.background1 });
      txt(s, d, { x: x + 0.35, y: y + 1.95, w: cw - 0.7, h: 1.25, fontSize: 15, color: "CBD3E1" });
    });
    txt(s, "The goal: salespeople spend their time on the conversation, not the preparation.",
      { x: M, y: 5.7, w: W - 2 * M, h: 0.6, fontSize: 20, italic: true, color: C.accent1 });
    s.addNotes("The ask is a small, measurable pilot. The metrics are chosen so the business can see whether preparation time drops, whether drafts are good enough to send with light edits, and whether commitments to advisors are kept.");
  }

  // ================================================================= Appendix
  pres.addSection({ title: "Appendix" });
  {
    const s = content("Appendix", "Appendix: architecture overview");
    framedImage(s, ARCH, { x: M, y: 1.4, w: W - 2 * M, h: 5.45 }, "Architecture diagram");
    s.addNotes("Components and data flows. Blue boxes are deterministic rules, violet are LLM agents (CrewAI), dashed boxes are SalesAssist capabilities exposed as MCP servers, grey boxes are source data. Full detail in docs/ARCHITECTURE.md in the project ZIP.");
  }
  {
    const s = content("Appendix", "Appendix: access control in action");
    const gb = await dialogGeometry(shot("blocked"));
    const bl = await crop(shot("blocked"), { left: 0, top: 0, width: gb.w, height: Math.min(gb.h, gb.bottom + 60) });
    framedImage(s, bl, { x: M, y: 1.5, w: 7.4, h: 5.2, align: "left" }, "Region block screenshot");
    txt(s, "Alex Chen works region T1. Casey Brooks is in region T2.", { x: 8.4, y: 1.7, w: 4.3, h: 0.9, fontSize: 17, bold: true });
    txt(s, "The click is refused before any data is fetched or any AI model is called. The same check runs again on cached drafts and when actions are executed.",
      { x: 8.4, y: 2.65, w: 4.3, h: 2.0, fontSize: 15, color: C.text2 });
    s.addNotes("Each internal user is assigned exactly one region. The prototype enforces that at the API and inside every SalesAssist tool the agents can call.");
  }

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch((e) => { console.error(e); process.exit(1); });

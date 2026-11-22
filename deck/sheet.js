const sharp = require("sharp");
const [dir, from, to, out] = process.argv.slice(2);
(async () => {
  const W = 900, Hh = 506, cols = 2, gap = 12;
  const files = []; for (let i = +from; i <= +to; i++) files.push(`${dir}/slide-${String(i).padStart(2, "0")}.jpg`);
  const rows = Math.ceil(files.length / cols);
  const comps = await Promise.all(files.map(async (f, k) => ({
    input: await sharp(f).resize(W, Hh).toBuffer(), left: (k % cols) * (W + gap), top: Math.floor(k / cols) * (Hh + gap) })));
  await sharp({ create: { width: cols * W + gap, height: rows * (Hh + gap), channels: 3, background: "#777" } })
    .composite(comps).jpeg({ quality: 80 }).toFile(out);
  console.log(out);
})();
